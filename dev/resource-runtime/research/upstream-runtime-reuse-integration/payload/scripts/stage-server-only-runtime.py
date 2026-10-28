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
parser.add_argument('--paired-kernel-build',help='Complete selected kernel using the same new append-only RPC header and wrapper')
args = parser.parse_args(); assert re.fullmatch('[a-z0-9]+', args.tag)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
data = json.loads((root / args.parent_stage).read_text())
build = json.loads((root / args.server_build).read_text())
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
delta_validation = None
if args.verified_source_delta:
    assert not build['full_server_source_build'] and args.baseline_relinked_server
    assert build['parent_private_stage'] == args.parent_stage or (args.paired_kernel_build and data.get('kernel_only_parent_stage') == build['parent_private_stage'])
    baseline = data['source_runtime']['LINUXCODE_DARLING_SERVER']['sha256']
    assert build['baseline_server_sha256'] == baseline and build['baseline_relink_identical']
    proof_path = root / build['baseline_relink_proof']; proof = json.loads(proof_path.read_text())
    assert proof['link_status'] == 0 and proof['identical_to_stage112']
    assert proof['expected_stage112_server_sha256'] == proof['actual_relinked_sha256'] == baseline
    assert sha(root / args.baseline_relinked_server) == baseline
    assert proof['protected_output_untouched'] and build['baseline_build_output_restored_and_untouched']
    assert build['public_RPC_layout_changed'] is False
    rpc_inputs={}
    if args.paired_kernel_build:
        assert build['kernel_change_required'] and build['RPC_appended']
        rpc_proof_path=root/build['append_only_rpc_proof']
        assert sha(rpc_proof_path)==build['append_only_rpc_proof_sha256']
        rpc_proof=json.loads(rpc_proof_path.read_text())
        assert rpc_proof['verified'] and rpc_proof['old_runtime_header_identical_to_regenerated_baseline']
        assert rpc_proof['old_call_numbers_identical']>0 and rpc_proof['old_struct_declarations_byte_identical']>0
        assert rpc_proof['old_wrapper_bodies_and_signatures_identical_after_removing_new_reply_union_member']>0
        assert rpc_proof['interrupt_enter_new_reply_union_member_only']
        assert rpc_proof['old_compiled_struct_sizes_alignments_and_call_numbers_identical'] and rpc_proof['old_call_reply_layouts_identical']
        for name,digest in rpc_proof['inputs'].items():rpc_inputs[resolve(name,digest)]=digest
        kernel_path=root/args.paired_kernel_build;kernel=json.loads(kernel_path.read_text())
        assert kernel['full_libsystem_kernel_source_build'] and kernel['complete_source_files']==len(kernel['sources'])
        assert data['source_builds']['kernel']==args.paired_kernel_build
        assert data['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['sha256']==kernel['binary_sha256']
        assert sha(root/build['new_rpc_header'])==build['new_rpc_header_sha256']
        assert sha(root/build['new_rpc_source'])==build['new_rpc_source_sha256']
        sources={row['source']:row for row in kernel['sources']}
        assert sources[build['new_rpc_source']]['sha256']==build['new_rpc_source_sha256']
        compiled=kernel['incremental_source_build']['compiled_consumer_dependency_sha256']
        consumers=[build['new_rpc_source']]+[name for name in compiled if name.endswith('/csops.c')]
        assert len(consumers)>=2
        for name in consumers:assert compiled[name][build['new_rpc_header']]==build['new_rpc_header_sha256']
        for name in [args.paired_kernel_build,build['append_only_rpc_proof'],build['new_rpc_header'],build['new_rpc_source']]:rpc_inputs[name]=sha(root/name)
    else:
        assert build['kernel_change_required'] is False

    assert build['hook_ABI_append_only'] and build['source_delta_units'] == len(build['objects']) > 0
    assert build['source_files'] and all(build['compiler_dependencies'].get(name) == digest
                                      for name,digest in build['source_files'].items())
    inputs = dict(rpc_inputs)
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
        kernel_changed=bool(args.paired_kernel_build),public_RPC_layout_changed=False,hook_ABI_append_only=True)
    if args.paired_kernel_build:delta_validation.update(paired_kernel_build=args.paired_kernel_build,append_only_rpc_proof=build['append_only_rpc_proof'],new_rpc_header_sha256=build['new_rpc_header_sha256'])
else:
    assert not args.baseline_relinked_server and not args.paired_kernel_build and build['full_server_source_build']
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
