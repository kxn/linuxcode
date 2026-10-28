#!/usr/bin/env python3
"""Prepare, but never run, a stage regression using isolated copies of a proven Unity export/cache."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import shlex
import stat
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
GUEST = '/Volumes/SystemRoot/workspace/'


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    # These are immutable reference products. Avoid changing file access time.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOATIME', 0))
    with os.fdopen(fd, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(path):
    rows = {}
    for item in sorted(path.rglob('*')):
        info = item.lstat()
        check(not stat.S_ISLNK(info.st_mode), 'Reference tree contains a symlink: ' + str(item))
        check(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Unexpected reference file type')
        row = dict(mode=stat.S_IMODE(info.st_mode), mtime_ns=info.st_mtime_ns,
                   kind='file' if item.is_file() else 'directory')
        if item.is_file():
            row.update(sha256=sha(item), size=info.st_size,
                       xattr_sha256={name: hashlib.sha256(os.getxattr(item, name)).hexdigest()
                                     for name in sorted(os.listxattr(item))})
        rows[str(item.relative_to(path))] = row
    return rows


def verify_originals(report):
    manifest = root / report['original_tree_manifest']
    check(sha(manifest) == report['original_tree_manifest_sha256'], 'Original-tree guard manifest changed')
    before = json.loads(manifest.read_text())
    for relative, expected in before.items():
        check(snapshot(root / relative) == expected, 'Original Unity tree changed: ' + relative)
    for name, expected in report['original_metadata_guards'].items():
        check(sha(root / name) == expected, 'Frozen original metadata changed: ' + name)
    return dict(verified=True, original_project_App_DerivedData_bytes_modes_mtimes_xattrs_preserved=True,
                native_execution_verified=False, session_lock_acquired=False)


def bee_write_audit(source, original_ios, original_dd, copies, configuration):
    pbx = original_ios / 'Unity-iPhone.xcodeproj/project.pbxproj'
    text = pbx.read_text()
    required = ['ln -sF', '$CONFIGURATION_TEMP_DIR/artifacts', '$PROJECT_DIR/Il2CppTempDirArtifacts/',
                '--cachedirectory=', '--outputpath=', 'rm -rf']
    check(all(value in text for value in required), 'Unexpected exported Unity IL2CPP phase')
    dags = list(original_dd.rglob('bee.dag.json'))
    check(len(dags) == 1, 'Expected exactly one verified Bee graph')
    dag = json.loads(dags[0].read_text())
    check(not dag.get('SharedResources'), 'Bee graph declares shared resources requiring separate isolation review')
    artifact_root = dags[0].parent.parent.parent
    expected = original_dd / 'Build/Intermediates.noindex/Unity-iPhone.build' / (configuration + '-iphoneos/artifacts')
    check(artifact_root == expected, 'Unexpected IL2CPP artifact output root')
    link = original_ios / 'Il2CppTempDirArtifacts' / configuration / 'artifacts'

    def resolve_write(name):
        if name.startswith(GUEST):
            path = root / name[len(GUEST):]
        else:
            raw = Path(name)
            path = raw if raw.is_absolute() else original_ios / raw
        path = Path(os.path.normpath(path))
        effective = artifact_root / path.relative_to(link) if path.is_relative_to(link) else path
        for old, private in copies:
            if effective.is_relative_to(old):
                return dict(declared=name, effective_virtual_path=str(effective.relative_to(root)),
                            private_destination=str((private / effective.relative_to(old)).relative_to(root)))
        raise RuntimeError('Bee/IL2CPP output escapes both isolated trees: ' + name)

    nodes = [value for node in dag['Nodes'] for value in node.get('Outputs', [])]
    state_keys = ['StructuredLogFileName', 'StateFileName', 'StateFileNameTmp', 'StateFileNameMapped',
                  'ScanCacheFileName', 'ScanCacheFileNameTmp', 'DigestCacheFileName', 'DigestCacheFileNameTmp',
                  'CachedNodeOutputDirectoryName', 'PayloadsFile']
    states = [dag[key] for key in state_keys if dag.get(key)]
    input_data = json.loads(dags[0].with_name('bee-inputdata.json').read_text())
    requests = next(iter(input_data.values()))
    extra = [requests['CompilationRequest']['Outputpath'],
             requests['ConversionRequest']['Generatedcppdir'], requests['ConversionRequest']['SymbolsFolder']]
    rows = [resolve_write(value) for value in sorted(set(nodes + states + extra))]
    return dict(verified=True, graph=str(dags[0].relative_to(root)), graph_sha256=sha(dags[0]),
                graph_nodes=len(dag['Nodes']), graph_declared_outputs=len(nodes),
                graph_state_and_cache_paths=len(states), audited_paths=rows,
                working_directory=str(original_ios.relative_to(root)),
                generated_runtime_symlink=dict(link=str(link.relative_to(root)), target=str(artifact_root.relative_to(root)),
                    both_ends_isolated_by_workspace_bindings=True, original_phase_cleans_link_on_success=True),
                incidental_OS_temporary_storage='Existing launcher mounts /tmp as private tmpfs; no claim of observing future syscalls',
                dynamic_write_observation_verified=False)


def write_runner(folder, command):
    verifier = [sys.executable, str(Path(__file__).resolve()), '--verify-originals', str((folder / 'prepared.json').relative_to(root))]
    runner = ('#!/usr/bin/env bash\nset -euo pipefail\ncd ' + shlex.quote(str(root)) + '\n' +
              shlex.join(verifier) + ' > ' + shlex.quote(str(folder / 'originals-before-native.json')) + '\n' +
              'set +e\n' + shlex.join(command) + ' > ' + shlex.quote(str(folder / 'native-driver.log')) + ' 2>&1\nstatus=$?\n' +
              shlex.join(verifier) + ' > ' + shlex.quote(str(folder / 'originals-after-native.json')) + '\nguards=$?\n' +
              'if [ "$guards" -ne 0 ]; then exit "$guards"; fi\nexit "$status"\n')
    (folder / 'run-native.sh').write_text(runner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', default='runtime/unity-editor-e2e-qkpyu3u9')
    parser.add_argument('--baseline-candidate', default='config/native-certificate-candidate-v12.json')
    parser.add_argument('--stage', default='artifacts/private-procfs-auditsession107-stage.json')
    parser.add_argument('--reuse-private-copy', help='Resume an incomplete host preparation after validating its immutable copy manifest')
    parser.add_argument('--verify-originals', help='Only recheck guards in this existing prepared.json')
    args = parser.parse_args()
    if args.verify_originals:
        report = json.loads((root / args.verify_originals).read_text())
        print(json.dumps(verify_originals(report), indent=2))
        return
    source = (root / args.source_run).resolve()
    check(source.is_relative_to(root / 'runtime'), 'Reference run must be under runtime/')
    end = json.loads((source / 'end-to-end-result.json').read_text())
    check(end['verified'] and end['Unity_export_verified'] and end['CocoaPods_verified'] and end['original_xcodebuild_verified'],
          'Require the actual successful original Unity end-to-end reference')
    argv = list(end['xcodebuild_command'])
    check(argv.pop(0) == 'xcodebuild' and argv[-1] == 'build', 'Expected original xcodebuild build arguments')
    original_ios = Path(argv[argv.index('-workspace') + 1]).parent
    original_dd = Path(argv[argv.index('-derivedDataPath') + 1])
    check(original_ios == source / 'ios' and original_dd == source / 'DerivedData', 'Unexpected reference roots')
    check((original_ios / 'Podfile.lock').read_bytes() == (original_ios / 'Pods/Manifest.lock').read_bytes(), 'Original Pod manifests differ')
    check(sha(original_ios / 'Podfile.lock') == end['pod_lock_sha256'], 'Original Pod input changed')
    baseline_path = root / args.baseline_candidate
    baseline = json.loads(baseline_path.read_text())
    for row in baseline['inputs'].values():
        check(sha(root / row['path']) == row['sha256'], 'Frozen candidate input changed: ' + row['path'])
    stage = json.loads((root / args.stage).read_text())
    selected = baseline['inputs']['configuration']['path']
    if args.reuse_private_copy:
        folder = (root / args.reuse_private_copy).resolve()
        check(folder.parent == root / 'runtime' and folder.name.startswith('unity-stage-regression-'), 'Unexpected private copy directory')
        check(not (folder / 'prepared.json').exists(), 'Prepared runs are immutable; choose a new run')
    else:
        folder = Path(tempfile.mkdtemp(prefix='unity-stage-regression-', dir=root / 'runtime'))
    folder.chmod(0o700)
    metadata_guards = {str(path.relative_to(root)): sha(path) for path in
                       (baseline_path, source / 'end-to-end-result.json', source / 'prepared.json',
                        source / 'xcodebuild-command.json')}
    copies = [(original_ios, folder / 'ios'), (original_dd, folder / 'DerivedData')]
    print('GUARDING reference trees', flush=True)
    manifest = folder / 'original-tree-manifest.json'
    before = {str(old.relative_to(root)): snapshot(old) for old, _ in copies}
    if args.reuse_private_copy:
        check(before == json.loads(manifest.read_text()), 'Original trees changed since this private copy was prepared')
    else:
        manifest.write_text(json.dumps(before, indent=2) + '\n')
    copy_rows = []
    for old, private in copies:
        print('COPYING', old.name, flush=True)
        command = ['cp', '-a', '--reflink=auto', '--no-preserve=links', str(old), str(private)]
        if not args.reuse_private_copy:
            subprocess.run(command, check=True)
        check(snapshot(private) == before[str(old.relative_to(root))], 'Copy contents or metadata differ')
        files = 0
        for relative, row in before[str(old.relative_to(root))].items():
            if row['kind'] != 'file':
                continue
            one, two = (old / relative).stat(), (private / relative).stat()
            check((one.st_dev, one.st_ino) != (two.st_dev, two.st_ino) and two.st_nlink == 1,
                  'Copy retains a hardlink or original inode: ' + relative)
            files += 1
        copy_rows.append(dict(source=str(old.relative_to(root)), private=str(private.relative_to(root)),
                              regular_files=files, logical_bytes=sum(row.get('size', 0) for row in before[str(old.relative_to(root))].values()),
                              command=command, distinct_inodes_and_nlink_one_verified=True, symlinks=0))
    bindings = folder / 'workspace-bindings.json'
    binding_rows = [dict(source=str(private.relative_to(root)), target=str(old.relative_to(root))) for old, private in copies]
    bindings.write_text(json.dumps(binding_rows, indent=2) + '\n')
    bind_stage_path = baseline['workspace_bind_stage']['path']
    bind_stage = json.loads((root / bind_stage_path).read_text())
    for name, digest in bind_stage['files'].items():
        check(sha(root / name) == digest, 'Existing binding launcher changed: ' + name)
    # Exercise the existing validator with path aliases only; no mount is run.
    validate = runpy.run_path(str(root / 'scripts/workspace-bindings.py'))['validate']
    validation_root = folder / 'binding-validation-rootfs'
    for row in binding_rows:
        (validation_root / 'workspace' / row['target']).mkdir(parents=True, exist_ok=True)
    mapped = validate(root, validation_root, bindings)
    check(len(mapped) == len(copies), 'Existing binding validator rejected the isolation plan')
    audit = bee_write_audit(source, original_ios, original_dd, copies, argv[argv.index('-configuration') + 1])
    (folder / 'bee-write-isolation.json').write_text(json.dumps(audit, indent=2) + '\n')
    candidate = {key: value for key, value in baseline.items() if key not in ('verified_build', 'scope')}
    candidate['inputs'] = {key: dict(value) for key, value in baseline['inputs'].items()}
    candidate['inputs']['stage'] = dict(path=args.stage, sha256=sha(root / args.stage))
    candidate.update(scope='Experimental isolated Unity regression with changed stage; no stage107 build/signing success is inherited',
                     experimental_only=True, runtime_build_verified=False,
                     baseline_candidate=dict(path=args.baseline_candidate, sha256=sha(baseline_path)),
                     historical_baseline_verified_build=baseline['verified_build'])
    candidate_path = folder / 'experimental-candidate.json'
    candidate_path.write_text(json.dumps(candidate, indent=2) + '\n')
    arguments = [value.replace(str(root) + '/', GUEST) for value in argv]
    argument_file = folder / 'xcode-arguments.json'
    argument_file.write_text(json.dumps(arguments, indent=2) + '\n')
    prior_plan = json.loads((root / end['native_run'] / 'plan.json').read_text())
    identity_store = prior_plan['certificate_runtime']['identity_store']
    profile_module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
    profile = profile_module['profile'](stage=args.stage, configuration=selected)
    signer = runpy.run_path(str(root / 'scripts/native-certificate-runtime.py'))
    profile = signer['select'](profile, str(candidate_path.relative_to(root)), identity_store, prepare=False)
    check(profile['source_runtime'] == stage['source_runtime'], 'Prepared profile selected different source runtime')
    check(profile['command'].count(bind_stage['parent_launcher']) == 1, 'Binding launcher parent is absent')
    command = json.loads((root / 'config/unity-main-stack-clean-dd83-v2-command.json').read_text())
    for key, value in {'--private-procfs-stage': args.stage, '--direct-resource-environment': selected,
                       '--identity-store': identity_store, '--xcode-arguments-file': str(argument_file.relative_to(root)),
                       '--timeout-seconds': '7200'}.items():
        command[command.index(key) + 1] = value
    command += ['--certificate-candidate', str(candidate_path.relative_to(root)), '--workspace-bind-stage', bind_stage_path,
                '--workspace-bindings', str(bindings.relative_to(root)), '--skip-uti-diagnostic']
    (folder / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    report = dict(prepared=True, source_run=str(source.relative_to(root)), stage=args.stage,
                  original_tree_manifest=str(manifest.relative_to(root)), original_tree_manifest_sha256=sha(manifest),
                  original_metadata_guards=metadata_guards, copies=copy_rows,
                  bindings=str(bindings.relative_to(root)), bindings_validated_by_existing_helper=True,
                  candidate=str(candidate_path.relative_to(root)), candidate_sha256=sha(candidate_path),
                  source_runtime=profile['source_runtime'], original_Xcode_argv_preserved=True,
                  original_host_arguments=argv, native_arguments=arguments, command=command,
                  application=str((folder / 'DerivedData' / Path(end['application']).relative_to(Path(args.source_run) / 'DerivedData')).relative_to(root)),
                  Bee_graph_declared_writes_isolated=True, Bee_dynamic_writes_observed=False,
                  no_original_Editor_or_activation_step=True, compilation_cache_copied=True, fresh_DerivedData=False,
                  frozen_candidate_promoted=False, old_stage101_success_inherited=False,
                  private_identity_contents_read_or_copied=False, native_execution_verified=False,
                  reused_only_this_preparations_existing_private_copies=bool(args.reuse_private_copy),
                  full_build_verified=False, codesign_verified=False, session_lock_acquired=False)
    verify_originals(report)
    (folder / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
    write_runner(folder, command)
    print('PREPARED', folder / 'prepared.json', flush=True)


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
