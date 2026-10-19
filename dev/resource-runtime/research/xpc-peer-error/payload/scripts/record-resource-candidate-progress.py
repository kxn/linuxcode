#!/usr/bin/env python3
"""Verify candidate bytes and actual original-tool failures for a checkpoint.

This checks reconstruction evidence, not framework semantics. A successful
version query would still require a separate real resource compilation check.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import runpy

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', action='append', required=True)
parser.add_argument('--probe', action='append', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--build-report', required=True)
parser.add_argument('--product-report', required=True)
parser.add_argument('--peer-error-probe')
parser.add_argument('--source-publication')
parser.add_argument('--export-contract')
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = root/args.output
assert not output.exists()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
read = lambda path: json.loads((root/path).read_text())
resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
evidence = {}


def checked(path):
    result = read(path)
    evidence[path] = sha(path)
    if 'log' in result:
        assert sha(result['log']) == result['log_sha256']
        evidence[result['log']] = sha(result['log'])
    return result


pins = read('config/coregraphics-image-pins.json')
images = []
for target in args.target:
    pin = pins[target]
    preparation = checked('artifacts/'+target+'-input.json')
    assert preparation['pin'] == pin and preparation['build_returncode'] == 0
    assert not preparation['image_runtime_verified']
    old_manifest = resolve('config/coregraphics-image-pins.json', preparation['previous_manifest_sha256'])
    assert target not in read(old_manifest)
    helper = resolve('scripts/prepare-resource-image-candidate.py', preparation['preparation_source_sha256'])
    evidence[helper] = sha(helper)
    data = checked('runtime/rebuilt-'+target+'/reconstruction.json')
    assert not data['installed'] and not data['execution_verified'] and not data['backend_call_overrides']
    assert sha('runtime/fullsystem-libraries'+pin['path']) == pin['sha256'] == data['original_image_sha256']
    assert sha('runtime/rebuilt-'+target+'/'+Path(pin['path']).name) == data['staged_image_sha256']
    classes = len(data.get('objc_metadata', {}).get('classes', []))
    assert classes == pin['objc_classes']
    images.append(dict(target=target, exports=data['exports'], objc_classes=classes,
        imports=len(data['cache_imports']), describe_lazy_helpers=data['describe_lazy_helpers'],
        algorithm_execution_verified=False))
    if 'exact_import_audit' in preparation:
        audit = checked(preparation['exact_import_audit'])
        assert sha(preparation['exact_import_audit']) == preparation['exact_import_audit_sha256']
        assert audit['unresolved'] == 0
probes = []
for path in args.probe:
    report = checked(path)
    assert not report['verified'] and not report['full_resource_compilation_verified']
    assert len(report['cases']) == 2
    cases = []
    for case in report['cases']:
        assert not case['verified'] and sha(case['log']) == case['log_sha256']
        assert case['original_sha256'] == sha('runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin/'+case['tool'])
        missing = re.findall(r'^Library not loaded: (.+)$', (root/case['log']).read_text(), re.M)
        symbols = re.findall(r'^(?:dyld: )?Symbol not found: (.+)$', (root/case['log']).read_text(), re.M)
        expected = re.findall(r'^  Expected in: (.+)$', (root/case['log']).read_text(), re.M)
        assert missing or symbols
        evidence[case['log']] = sha(case['log'])
        cases.append(dict(tool=case['tool'], outer_status=case['outer_status'],
            missing_library=missing[0] if missing else None,
            missing_symbol=symbols[0] if symbols else None,
            expected_provider=expected[0] if expected else None))
    probes.append(dict(report=path, cases=cases))
build = checked(args.build_report)
assert build['native_xcode_status'] == ['65'] and build['exit_status'] == 65 and build['xcode_process_returned']
text = (root/build['log']).read_text()
assert 'Target dependency graph (5 targets)' in text
assert all('/Applications/Xcode.app/Contents/Developer/usr/bin/'+tool in text for tool in ['actool', 'ibtool'])
assert build['original_xcodebuild_sha256'] == sha('runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin/xcodebuild')
assert build['direct_resource_environment']['configuration'] == args.configuration
assert build['direct_resource_environment']['configuration_sha256'] == sha(args.configuration)
products = checked(args.product_report)
assert not products['verified'] and not any(row['exists'] for row in products['expected_product_binaries'])
configuration = checked(args.configuration)
assert sha(configuration['graphics_stage']) == configuration['graphics_stage_sha256']
peer_evidence = None
assert bool(args.peer_error_probe) == bool(args.source_publication) == bool(args.export_contract)
if args.peer_error_probe:
    peer = checked(args.peer_error_probe)
    assert peer['verified'] and peer['real_rich_error_cases'] == 160 and not peer['peer_signing_enforcement_added']
    for case in peer['cases']:
        assert case['verified'] and case['outer_status'] == 0 and case['native_status'] == ['0']
        assert sha(case['log']) == case['log_sha256']
        evidence[case['log']] = sha(case['log'])
    control = next(case for case in peer['cases'] if case['mode'] == 'missing')
    positive = next(case for case in peer['cases'] if case['mode'] == 'present')
    assert control['mode'] == 'missing' and positive['mode'] == 'present'
    assert 'RESOURCE_SYSTEM_PEER_ERROR_ABSENT_CONTROL_OK' in (root/control['log']).read_text()
    assert 'XPC_RICH_ERROR_ACTUAL_OBJECTS_COPY_RETRY_RETAIN_AND_PEER_ERROR_OK' in (root/positive['log']).read_text()
    assert 'RESOURCE_SYSTEM_PEER_ERROR_REEXPORT_IDENTITY_AND_REAL_OBJECTS_OK' in (root/positive['log']).read_text()
    publication = checked(args.source_publication)
    assert publication['published'] and publication['remote_commit_verified']
    contract = checked(args.export_contract)
    assert contract['verified'] and contract['added_exports'] == ['__xpc_error_peer_code_signing_requirement']
    assert contract['previous_exports_preserved'] == 641 and contract['launch_reexports_preserved'] == 112
    peer_evidence = dict(probe=args.peer_error_probe, source_publication=args.source_publication,
        actual_object_cases=160, previous_exports_preserved=641, launch_reexports_preserved=112,
        one_backend_singleton_verified=True, peer_signing_enforcement_added=False)
    peer_evidence['normal_runtime_verified'] = peer.get('normal_runtime_verified', False)
sources = ['scripts/prepare-resource-image-candidate.py', 'scripts/audit-resource-image-imports.py',
    'scripts/test-resource-image-preparation.py', 'scripts/record-resource-candidate-progress.py',
    'config/coregraphics-image-pins.json', args.configuration]
result = dict(checked_at=datetime.now(timezone.utc).isoformat(), classification='progress',
    full_goal_complete=False, evidence=evidence, sources={path: sha(path) for path in sources},
    new_resource_candidates=images, original_resource_probes=probes,
    original_Unity_full_build_report=args.build_report, original_Unity_full_build_native_status=65,
    actual_resource_queries_observed=True, five_target_dependency_graph_verified=True,
    full_Unity_App_verified=False, AFNetworking_source_compilation_verified=any(
        line.startswith('CompileC ') and 'AFNetworking' in line for line in text.splitlines()),
    runtime_stage=build['private_procfs_stage'], direct_environment=args.configuration,
    graphics_stage=configuration['graphics_stage'], current_resource_blocker=(
        probes[-1]['cases'][0]['missing_library'] or 'Symbol '+probes[-1]['cases'][0]['missing_symbol']+
        ' in '+str(probes[-1]['cases'][0]['expected_provider'])),
    peer_error_evidence=peer_evidence,
    resource_compilation_verified=False, default_candidate_promoted=False, cold_installation_verified=False)
output.write_text(json.dumps(result, indent=2)+'\n')
print(output.relative_to(root))
