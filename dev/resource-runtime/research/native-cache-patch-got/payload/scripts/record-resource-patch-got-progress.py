#!/usr/bin/env python3
"""Record checked recovery progress without equating loading with compilation."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import runpy
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--xcode-report', required=True)
parser.add_argument('--direct-probe', required=True)
parser.add_argument('--image-probe', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = root / args.output
assert not output.exists()
sha = lambda path: hashlib.sha256((root / path).read_bytes()).hexdigest()
read = lambda path: json.loads((root / path).read_text())
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
inspection_path = 'artifacts/appleidsso-preserved-code-v4-inspection.json'
inspection = read(inspection_path)
for name, digest in inspection['files'].items():
    if name.startswith(('config/', 'scripts/')): resolve(name, digest)
    else: assert sha(name) == digest, name
assert inspection['verified'] and inspection['original_code_bytes_equal']
assert inspection['got_cells_verified'] == 144 and inspection['nonzero_addends_verified'] == 17
assert inspection['llvm_bind_and_lazy_bind_tables_parsed']
metadata_path = 'artifacts/appleidsso-original-patch-metadata-v1.json'
metadata = read(metadata_path)
assert len(metadata['records']) == 141 and len(metadata['missing_target_matches']) == 17
assert all(r['target_matches_patch'] and r['export_matches_patch'] for r in metadata['records'])
resolve('scripts/cache-patch-metadata.py', metadata['source_sha256'])
format_pin = read('config/cache-patch-metadata-format.json')
for f in format_pin['files'].values(): assert sha(f['path']) == f['sha256']
evidence = {name: sha(name) for name in [inspection_path, metadata_path,
    'artifacts/appleidsso-original-got-pools-v1.json',
    'artifacts/biomelibrary-original-import-audit-v1.json',
    'artifacts/duet-remaining-original-dependencies-v1.json']}
probes = []
for name in ['runtime/direct-resource-tools-mm_guq43/result.json',
             'runtime/direct-resource-tools-hb78ygku/result.json',
             'runtime/direct-resource-tools-3ishj3sw/result.json',
             'runtime/direct-resource-tools-w3cfi0jw/result.json',
             'runtime/direct-resource-tools-n_zk2hk0/result.json', args.direct_probe]:
    p = read(name)
    assert not p['verified'] and len(p['cases']) == 2
    cases = []
    for case in p['cases']:
        assert case['outer_status'] != 0 and not case['verified']
        assert sha(case['log']) == case['log_sha256']
        text = (root / case['log']).read_text()
        missing = re.findall(r'^Library not loaded: (.+)$', text, re.M)
        assert missing
        tool = case['tool']
        native = 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/usr/bin/' + tool
        extracted = 'runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin/' + tool
        assert sha(native) == sha(extracted) == case['original_sha256']
        evidence[case['log']] = sha(case['log'])
        cases.append(dict(tool=tool, outer_status=case['outer_status'],
            native_status=case['native_status'], missing_library=missing[0],
            original_tool_bytes_equal=True, resource_compilation_verified=False))
    evidence[name] = sha(name)
    probes.append(dict(report=name, cases=cases))
images = []
for target in ['appleidsso-patch-got-v4', 'applepushservice-resource-v1',
               'backgroundsystemtasks-resource-v1', 'duetactivityscheduler-resource-v1',
               'coreduetcontext-resource-v1', 'biomelibrary-resource-v2', 'coreduet-resource-v1']:
    path = 'runtime/rebuilt-' + target + '/reconstruction.json'
    r = read(path)
    pin = read('config/coregraphics-image-pins.json')[target]
    assert sha('runtime/fullsystem-libraries' + pin['path']) == pin['sha256'] == r['original_image_sha256']
    assert sha('runtime/rebuilt-' + target + '/' + Path(pin['path']).name) == r['staged_image_sha256']
    assert not r['execution_verified']
    evidence[path] = sha(path)
    images.append(dict(target=target, exports=r['exports'], bindings=r['bindings'],
        lazy_bindings=r['lazy_bindings'], instructions_patched=r['rip_instructions_patched'],
        original_sha256=r['original_image_sha256'], staged_sha256=r['staged_image_sha256'],
        function_behavior_verified=False))
xcode = read(args.xcode_report)
assert sha(xcode['log']) == xcode['log_sha256']
assert xcode['original_xcodebuild_sha256'] == sha('runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin/xcodebuild')
assert xcode['native_xcode_status'] == [] and xcode['exit_status'] == -9
assert not xcode['xcode_process_returned'] and xcode['xcode_process_started']
text = (root / xcode['log']).read_text()
assert xcode['command'][3] == '600'
assert not xcode['full_xcode_build_ready']
evidence[args.xcode_report] = sha(args.xcode_report)
evidence[xcode['log']] = sha(xcode['log'])
for stem in ['unity-resource-patch-got-v4-live', 'unity-resource-patch-got-v4-live-later']:
    path = 'artifacts/' + stem + '-symbolication.json'
    saved = read(path)
    for key in ['raw', 'maps', 'output']: assert sha(saved[key]) == saved[key+'_sha256']
    for name, digest in saved['images'].items(): assert sha(name) == digest
    stack = (root/saved['output']).read_text()
    assert '___loadValidCoreSimulatorService_block_invoke_2' in stack
    assert '_resolveInputOptionsWithTimingSection:' in stack
    evidence[path] = sha(path)
    for key in ['raw', 'maps', 'output']: evidence[saved[key]] = sha(saved[key])
image_probe = read(args.image_probe)
assert not image_probe['dlopen_completed'] and image_probe['outer_status'] != 0
assert sha(image_probe['log']) == image_probe['log_sha256']
image_text = (root/image_probe['log']).read_text()
assert 'NATIVE_FOUNDATION_PROBE_MAIN_ENTERED' in image_text
assert 'BiomeStreams.framework/Versions/A/BiomeStreams' in image_text
for name, digest in image_probe['files'].items():
    if name.startswith(('scripts/', 'config/')): resolve(name, digest)
    else: assert sha(name) == digest, name
evidence[args.image_probe] = sha(args.image_probe)
evidence[image_probe['log']] = sha(image_probe['log'])
tests = []
for script, count in [('scripts/test-cache-patch-metadata.py', 11),
                      ('scripts/test-preserved-patch-got-inspector.py', 4)]:
    log = 'logs/' + output.stem + '-' + Path(script).stem + '.log'
    assert not (root/log).exists()
    with (root/log).open('w') as stream:
        result = subprocess.run(['python3', script], cwd=root, stdout=stream, stderr=subprocess.STDOUT)
    assert result.returncode == 0
    assert re.search(r'Ran '+str(count)+r' tests\b', (root/log).read_text())
    evidence[log] = sha(log)
    tests.append(dict(script=script, cases=count, exit_status=result.returncode, log=log))
sources = ['scripts/rebuild-c-cache-image.py', 'scripts/cache-patch-metadata.py',
    'scripts/test-cache-patch-metadata.py', 'scripts/inspect-preserved-patch-got.py',
    'scripts/test-preserved-patch-got-inspector.py', 'scripts/extend-coregraphics-stage.py',
    'scripts/probe-original-image-runtime.py', 'fixtures/hello/native-foundation-load.c',
    'scripts/record-resource-patch-got-progress.py', 'config/cache-patch-metadata-format.json',
    'config/coregraphics-image-pins.json', 'config/direct-resource-tool-environment-v8.json',
    'config/direct-resource-tool-environment-v9.json',
    'config/unity-ios-cocoapods-v4-build-arguments.json',
    'config/unity-ios-cocoapods-v5-probe-arguments.json']
output.write_text(json.dumps(dict(checked_at=datetime.now(timezone.utc).isoformat(),
    classification='progress', previous_goal_turn_classification='progress',
    full_goal_complete=False, evidence=evidence, sources={p: sha(p) for p in sources},
    original_patch_records_verified=141, original_nonzero_addends_verified=17,
    original_pooled_got_cells_verified=144, original_instruction_bytes_preserved=True,
    original_tool_probes=probes, reconstructed_images=images,
    tests=tests, standalone_image_probe=args.image_probe,
    standalone_image_dlopen_completed=False,
    graphics_stage='artifacts/coregraphics-native-v50-stage.json',
    direct_environment='config/direct-resource-tool-environment-v9.json',
    xcode_report=args.xcode_report, native_xcode_status=xcode['native_xcode_status'],
    xcode_outer_status=xcode['exit_status'],
    current_blocker='Original BiomeStreams.framework is missing, required by DuetActivityScheduler',
    latest_full_workspace_result='600-second timeout; kill returned -9, no native status. Two live stacks show CoreSimulator service loading and main input-option wait; causality remains unproven.',
    actual_resource_compilation_verified=False, full_Unity_App_verified=False,
    AFNetworking_source_compilation_verified=False, cold_installation_verified=False,
    caveats=['The byte-preserving mode recovers only metadata-proven imported GOT cells.',
        'Unselected bytes in the new private pool are zero padding; arbitrary external relative references remain unproven.',
        'Successful dependency loading does not prove that framework methods or initializers execute correctly.',
        'Original algorithms still rely on incomplete Darling APIs; output content must be independently verified.',
        'Full Unity/UE App, resources, signing, certificate/provisioning, archive/export and installation remain incomplete.']),
    indent=2)+'\n')
print(output.relative_to(root))
