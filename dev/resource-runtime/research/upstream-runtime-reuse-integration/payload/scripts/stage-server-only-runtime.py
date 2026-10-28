#!/usr/bin/env python3
"""Clone a coherent private runtime and replace only its source server."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shutil, subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-stage', required=True)
parser.add_argument('--server-build', required=True)
parser.add_argument('--tag', required=True)
parser.add_argument('--verified-source-delta', action='store_true', help='Require parent-matching baseline relink and sealed delta inputs instead of a full source build')
parser.add_argument('--baseline-relinked-server', help='Actual baseline relink ELF required for a verified source delta')
args = parser.parse_args(); assert re.fullmatch('[a-z0-9]+', args.tag)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
data = json.loads((root / args.parent_stage).read_text())
build = json.loads((root / args.server_build).read_text())
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
delta_validation = None
if args.verified_source_delta:
    assert not build['full_server_source_build'] and args.baseline_relinked_server
    assert build['parent_private_stage'] == args.parent_stage
    baseline = data['source_runtime']['LINUXCODE_DARLING_SERVER']['sha256']
    assert build['baseline_server_sha256'] == baseline and build['baseline_relink_identical']
    proof_path = root / build['baseline_relink_proof']; proof = json.loads(proof_path.read_text())
    assert proof['link_status'] == 0 and proof['identical_to_stage112']
    assert proof['expected_stage112_server_sha256'] == proof['actual_relinked_sha256'] == baseline
    assert sha(root / args.baseline_relinked_server) == baseline
    assert proof['protected_output_untouched'] and build['baseline_build_output_restored_and_untouched']
    assert build['kernel_change_required'] is False and build['public_RPC_layout_changed'] is False
    assert build['hook_ABI_append_only'] and build['source_delta_units'] == len(build['objects']) > 0
    assert build['source_files'] and all(build['compiler_dependencies'].get(name) == digest
                                      for name,digest in build['source_files'].items())
    inputs = {}
    for group in [proof['original_link_inputs'], build['source_files'], build['compiler_dependencies'], build['objects']]:
        for name,digest in group.items():
            if name in inputs: assert inputs[name] == digest,name
            resolved = resolve(name,digest)
            inputs[resolved] = digest
    archive = build['private_updated_archive']
    originals = [name for name,digest in proof['original_link_inputs'].items()
                 if name.endswith('.a') and digest == archive['old_archive_sha256']]
    assert len(originals) == 1 and sha(root/archive['path']) == archive['sha256']
    inputs[archive['path']] = archive['sha256']
    # Every newly compiled object must be consumed directly or as the exact
    # replacement member of the private copy of the baseline archive.
    linked_objects = 0
    for name,digest in build['objects'].items():
        obj = root/name
        command_path = obj.with_suffix('.command.json')
        command = json.loads(command_path.read_text())
        assert Path(command[command.index('-o')+1]).resolve() == obj.resolve()
        sources = [str(Path(value).resolve().relative_to(root)) for value in command
                   if Path(value).is_absolute() and Path(value).is_file()
                   and Path(value).suffix in ('.c','.cc','.cpp','.cxx')
                   and Path(value).resolve().is_relative_to(root)]
        assert len(sources) == 1 and sources[0] in build['source_files']
        inputs[str(command_path.relative_to(root))] = sha(command_path)
        if str(obj) not in build['link_command']:
            member = subprocess.check_output(['llvm-ar-19','p',str(root/archive['path']),obj.name])
            assert hashlib.sha256(member).hexdigest() == digest,name
        linked_objects += 1
    allowed = set(proof['original_link_inputs']) | set(build['objects']) | {archive['path']}
    for value in build['link_command'][1:]:
        path = Path(value)
        if path.is_absolute() and path.suffix in ('.o','.a','.so'):
            name = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            assert name in allowed,name
    inputs[build['baseline_relink_proof']] = sha(proof_path)
    inputs[args.baseline_relinked_server] = baseline
    data['files'].update(inputs)
    delta_validation = dict(full_server_source_build=False,source_delta_units=build['source_delta_units'],
        parent_private_stage=args.parent_stage,baseline_server_sha256=baseline,
        baseline_relinked_server=args.baseline_relinked_server,baseline_relink_proof=build['baseline_relink_proof'],
        baseline_relink_proof_sha256=sha(proof_path),source_files=len(build['source_files']),
        compiler_dependencies=len(build['compiler_dependencies']),verified_objects=linked_objects,
        original_link_inputs=len(proof['original_link_inputs']),sealed_input_files=len(inputs),
        kernel_changed=False,public_RPC_layout_changed=False,hook_ABI_append_only=True)
else:
    assert not args.baseline_relinked_server and build['full_server_source_build']
assert sha(root / build['server']) == build['server_sha256']
for name, digest in data['files'].items(): resolve(name, digest)
for row in data['source_runtime'].values(): assert sha(root / row['path']) == row['sha256']
folder = root / ('runtime/audit-session-runtime-' + args.tag)
report = root / ('artifacts/private-procfs-auditsession' + args.tag + '-stage.json')
assert not folder.exists() and not report.exists(); folder.mkdir()
old_root = (root / data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent / 'darling-root'
guest = folder / 'darling-root'
subprocess.run(['cp', '-a', '--reflink=auto', str(old_root), str(guest)], check=True)
selected = {}
for key, row in data['source_runtime'].items():
    source = root / (build['server'] if key == 'LINUXCODE_DARLING_SERVER' else row['path'])
    target = folder / Path(row['path']).name; shutil.copy2(source, target)
    name = str(target.relative_to(root)); selected[key] = dict(path=name, sha256=sha(target)); data['files'][name] = sha(target)
data['source_runtime'] = selected; data['source_builds']['server'] = args.server_build
for name in [args.parent_stage, args.server_build, str(Path(__file__).relative_to(root))]: data['files'][name] = sha(root / name)
data['system_version_binding'] = str((guest / 'System/Library/CoreServices/SystemVersion.plist').relative_to(root))
data['files'][data['system_version_binding']] = sha(root / data['system_version_binding'])
data['mtab'] = str((guest / 'private/etc/mtab').relative_to(root))
assert (root / data['mtab']).readlink() == Path(data['mtab_target'])
data.update(runtime_execution_verified=False, full_goal_complete=False, server_only_parent_stage=args.parent_stage)
if delta_validation: data['verified_server_source_delta'] = delta_validation
report.write_text(json.dumps(data, indent=2) + '\n'); print(report.relative_to(root))
