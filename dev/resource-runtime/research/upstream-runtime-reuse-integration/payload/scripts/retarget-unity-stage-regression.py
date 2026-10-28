#!/usr/bin/env python3
"""Retarget an unexecuted Unity regression plan to a new stage without copying its isolated cache."""
from pathlib import Path
import argparse
import copy
import json
import runpy
import tempfile

root = Path(__file__).resolve().parent.parent
helper = runpy.run_path(str(root / 'scripts/prepare-unity-stage-regression.py'))
check, sha = helper['check'], helper['sha']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', required=True)
    parser.add_argument('--stage', required=True)
    parser.add_argument('--configuration',help='Select an explicitly pinned resource configuration for the new preparation')
    args = parser.parse_args()
    source_report = (root / args.prepared).resolve()
    check(source_report.is_relative_to(root / 'runtime'), 'Preparation must be inside runtime/')
    prior = json.loads(source_report.read_text())
    check(prior['prepared'] and not prior['native_execution_verified'], 'Require an unexecuted private regression preparation')
    check(not (source_report.parent / 'native-driver.log').exists(), 'Prior native driver has already been invoked')
    metadata_guards = {str(path.relative_to(root)): sha(path) for path in source_report.parent.iterdir() if path.is_file()}
    helper['verify_originals'](prior)
    original_manifest = json.loads((root / prior['original_tree_manifest']).read_text())
    for row in prior['copies']:
        source = root / row['source']
        private = root / row['private']
        expected = original_manifest[row['source']]
        check(helper['snapshot'](private) == expected, 'Private cache no longer matches original preparation')
        for name, entry in expected.items():
            if entry['kind'] != 'file':
                continue
            old, new = (source / name).stat(), (private / name).stat()
            check((old.st_dev, old.st_ino) != (new.st_dev, new.st_ino) and new.st_nlink == 1,
                  'Private cache has a hardlink/shared inode')
    folder = Path(tempfile.mkdtemp(prefix='unity-stage-regression-', dir=root / 'runtime'))
    folder.chmod(0o700)
    candidate = json.loads((root / prior['candidate']).read_text())
    check(candidate['experimental_only'] and 'verified_build' not in candidate, 'Experimental runtime cannot inherit a verified build')
    candidate['inputs']['stage'] = dict(path=args.stage, sha256=sha(root / args.stage))
    if args.configuration:
        candidate['inputs']['configuration'] = dict(path=args.configuration,sha256=sha(root/args.configuration))
    candidate.update(scope='Experimental isolated Unity regression with new stage; historical stage101 success is reference only',
                     runtime_build_verified=False,
                     unexecuted_parent_preparation=dict(path=args.prepared, sha256=sha(source_report)))
    candidate_path = folder / 'experimental-candidate.json'
    candidate_path.write_text(json.dumps(candidate, indent=2) + '\n')
    arguments = folder / 'xcode-arguments.json'
    arguments.write_text(json.dumps(prior['native_arguments'], indent=2) + '\n')
    bindings = folder / 'workspace-bindings.json'
    binding_rows = json.loads((root / prior['bindings']).read_text())
    bindings.write_text(json.dumps(binding_rows, indent=2) + '\n')
    validation_root = folder / 'binding-validation-rootfs'
    for row in binding_rows:
        (validation_root / 'workspace' / row['target']).mkdir(parents=True, exist_ok=True)
    validate = runpy.run_path(str(root / 'scripts/workspace-bindings.py'))['validate']
    check(len(validate(root, validation_root, bindings)) == 2, 'Existing binding validator rejected reused copies')
    stage = json.loads((root / args.stage).read_text())
    profile_module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
    profile = profile_module['profile'](stage=args.stage, configuration=candidate['inputs']['configuration']['path'])
    command = list(prior['command'])
    identity_store = command[command.index('--identity-store') + 1]
    signer = runpy.run_path(str(root / 'scripts/native-certificate-runtime.py'))
    profile = signer['select'](profile, str(candidate_path.relative_to(root)), identity_store, prepare=False)
    check(profile['source_runtime'] == stage['source_runtime'], 'New runtime profile did not select requested stage')
    for key, value in {'--private-procfs-stage': args.stage,
                       '--direct-resource-environment': candidate['inputs']['configuration']['path'],
                       '--certificate-candidate': str(candidate_path.relative_to(root)),
                       '--workspace-bindings': str(bindings.relative_to(root)),
                       '--xcode-arguments-file': str(arguments.relative_to(root))}.items():
        check(command.count(key) == 1, 'Ambiguous driver option: ' + key)
        command[command.index(key) + 1] = value
    report = copy.deepcopy(prior)
    report.update(stage=args.stage, candidate=str(candidate_path.relative_to(root)), candidate_sha256=sha(candidate_path),
                  bindings=str(bindings.relative_to(root)), command=command, source_runtime=profile['source_runtime'],
                  preparation_parent=args.prepared, preparation_parent_sha256=sha(source_report),
                  parent_preparation_metadata_guards=metadata_guards,
                  new_project_or_DerivedData_copy_operations=0,
                  mutable_private_cache_reused_from_unexecuted_parent=True,
                  source_stage107_metadata_preserved=True,
                  parallel_execution_with_parent_plan_allowed=False,
                  native_execution_verified=False, full_build_verified=False, codesign_verified=False,
                  new_stage_runtime_success_inherited=False, session_lock_acquired=False)
    for row in report['copies']:
        row['copy_operation_performed_in_this_preparation'] = False
    (folder / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    (folder / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
    helper['write_runner'](folder, command)
    guarded = helper['verify_originals'](report)
    check(all(sha(root / path) == digest for path, digest in metadata_guards.items()), 'Parent stage107 preparation metadata changed')
    guarded.update(preparation_only=True, source_stage107_metadata_preserved=True,
                   project_and_DerivedData_copy_operations=0,
                   private_cache_symlinks=0, private_cache_independent_inodes_verified=True,
                   profile_and_certificate_scope_validated_without_services=True,
                   source_stage=args.stage, runtime_execution_verified=False)
    (folder / 'host-preparation-verification.json').write_text(json.dumps(guarded, indent=2) + '\n')
    print('PREPARED', folder / 'prepared.json', flush=True)
    print('RUN_LATER bash', folder / 'run-native.sh', flush=True)


if __name__ == '__main__':
    main()
