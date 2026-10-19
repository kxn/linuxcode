#!/usr/bin/env python3
"""Check the clock regression, original build attempt, and resource recovery evidence."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = root/args.output
assert not output.exists()
read = lambda path: json.loads((root/path).read_text())
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
evidence = {}

def checked(path):
    data = read(path)
    evidence[path] = sha(path)
    if 'log' in data:
        assert sha(data['log']) == data['log_sha256']
        evidence[data['log']] = sha(data['log'])
    return data

old_clock = checked('runtime/boottime-clock-_4cv10k0/result.json')
new_clock = checked('runtime/boottime-clock-7otgfy9s/result.json')
old_sleep = checked('runtime/runtime-usleep-ihnwt7g3/result.json')
new_sleep = checked('runtime/runtime-usleep-8mn90mq6/result.json')
assert not old_clock['verified'] and not old_sleep['verified']
assert new_clock['verified'] and new_sleep['verified']
text = (root/new_clock['log']).read_text()
samples = re.findall(r'^BOOT_SAMPLE (\d+) epoch=(\d+) usec=(\d+) expected=(\d+)$', text, re.M)
assert len(samples) == 96
assert all(int(epoch) == int(expected) == new_clock['expected_linux_btime'] and int(usec) == 0
           for _, epoch, usec, expected in samples)
crosscheck = re.search(r'^CLOCK_CROSSCHECK monotonic_ns=(\d+) mach_ns=(\d+) difference_ns=(\d+)$', text, re.M)
assert crosscheck and int(crosscheck[3]) < 25000000
delays = re.findall(r'^USLEEP_END worker=(\d+) case=(\d+) status=(\d+) elapsed_ns=(\d+)$',
    (root/new_sleep['log']).read_text(), re.M)
assert len(delays) == 16 and all(int(status) == 0 and int(ns) < 15000000000 for _, _, status, ns in delays)
layout = checked('runtime/private-procfs-test-oyikj8tq/result.json')
signer = checked('runtime/original-codesign-native-identity-r4my84gg/result.json')
assert layout['verified'] and signer['verified'] and signer['entitlements_verified']
assert len(signer['tamper_checks']) == 4
preferences = checked('runtime/core-simulator-preferences-rcb2dg6x/result.json')
assert preferences['preference_probe_completed']
assert 'CS_PREF timeout=20 ' in (root/preferences['log']).read_text()
kernel = checked('artifacts/stable-boottime-kernel-v1-build.json')
stage = checked('artifacts/private-procfs-v7-stage.json')
source = 'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/misc/sysctl_kern.c'
entry = [row for row in kernel['sources'] if row['source'] == source]
assert len(entry) == 1 and entry[0]['sha256'] == sha(source)
assert kernel['full_libsystem_kernel_source_build'] and kernel['complete_source_files'] == 879
assert stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['sha256'] == kernel['binary_sha256']
assert sha(stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path']) == kernel['binary_sha256']
publication = checked('artifacts/stable-boottime-xnu-publication.json')
assert publication['published'] and publication['source_sha256'] == sha(source)
assert publication['remote_commit_verified']
build_path = 'artifacts/xcode-service-runtime-tool-dispatch-diagnostic-build-9f676f522557.json'
build = checked(build_path)
assert build['native_xcode_status'] == ['65'] and build['exit_status'] == 65
assert build['xcode_process_returned'] and build['private_procfs_stage'] == 'artifacts/private-procfs-v7-stage.json'
assert build['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['sha256'] == kernel['binary_sha256']
assert build['original_xcodebuild_sha256'] == sha('runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin/xcodebuild')
build_text = (root/build['log']).read_text()
assert 'ComputeTargetDependencyGraph' in build_text and 'Target dependency graph (5 targets)' in build_text
assert 'BiomePubSub.framework/Versions/A/BiomePubSub' in build_text
assert not any(line.startswith('CompileC ') for line in build_text.splitlines())
product = checked('artifacts/unity-ios-cocoapods-v5-product-inspection.json')
assert not product['verified'] and not any(row['exists'] for row in product['expected_product_binaries'])
images = []
for target in ['biomestreams-resource-v2', 'biomefoundation-resource-v1', 'biomepubsub-resource-v1',
               'proactivesupport-resource-v2', 'intents-resource-v2']:
    path = 'runtime/rebuilt-'+target+'/reconstruction.json'
    data = checked(path)
    pin = read('config/coregraphics-image-pins.json')[target]
    assert sha('runtime/fullsystem-libraries'+pin['path']) == pin['sha256'] == data['original_image_sha256']
    assert sha('runtime/rebuilt-'+target+'/'+Path(pin['path']).name) == data['staged_image_sha256']
    images.append(dict(target=target, exports=data['exports'], objc_classes=len(data['objc_metadata']['classes']),
        class_reference_cells=len(data['cache_objc_class_reference_cells']), algorithm_execution_verified=False))
probes = []
for path in ['runtime/direct-resource-tools-16hwek8p/result.json',
             'runtime/direct-resource-tools-8s2zy1sq/result.json',
             'runtime/direct-resource-tools-_o7fghsj/result.json',
             'runtime/direct-resource-tools-3v6yydza/result.json']:
    data = checked(path)
    assert not data['verified'] and len(data['cases']) == 2
    cases = []
    for case in data['cases']:
        assert sha(case['log']) == case['log_sha256'] and not case['verified']
        assert case['original_sha256'] == sha('runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin/'+case['tool'])
        missing = re.findall(r'^Library not loaded: (.+)$', (root/case['log']).read_text(), re.M)
        assert missing
        evidence[case['log']] = sha(case['log'])
        cases.append(dict(tool=case['tool'], missing_library=missing[0], outer_status=case['outer_status']))
    probes.append(dict(report=path, cases=cases))
for path in ['artifacts/biomestreams-original-indirect-cell-audit-v1.json',
             'artifacts/proactive-support-original-import-audit-v1.json',
             'artifacts/intents-original-indirect-cell-audit-v1.json',
             'artifacts/core-simulator-original-libxpc-query-audit-v1.json']:
    checked(path)
sources = [source, 'fixtures/hello/runtime-usleep.c', 'fixtures/hello/boottime-clock.c',
    'fixtures/hello/core-simulator-preferences.c', 'scripts/probe-runtime-usleep.py',
    'scripts/probe-boottime-clock.py', 'scripts/probe-core-simulator-preferences.py',
    'scripts/record-stable-boottime-progress.py', 'config/coregraphics-image-pins.json',
    'config/direct-resource-tool-environment-v11.json', 'config/direct-resource-tool-environment-v14.json',
    'config/unity-ios-cocoapods-v5-build-arguments.json', 'config/unity-ios-cocoapods-v6-probe-arguments.json']
result = dict(checked_at=datetime.now(timezone.utc).isoformat(), classification='progress',
    previous_goal_turn_classification='progress', full_goal_complete=False, evidence=evidence,
    sources={name: sha(name) for name in sources}, source_fork=publication,
    complete_kernel_source_units=879, actual_boot_epoch_samples=96, native_sleep_cases=16,
    clock_crosscheck_difference_ns=int(crosscheck[3]), old_clock_and_sleep_controls_failed=True,
    native_original_codesign_entitlements_and_four_tampers_verified=True,
    original_Unity_full_build_report=build_path, original_Unity_full_build_native_status=65,
    five_target_dependency_graph_verified=True, actual_resource_queries_observed=True,
    full_Unity_App_verified=False, AFNetworking_source_compilation_verified=False,
    new_resource_candidates=images, original_resource_probes=probes,
    graphics_stage='artifacts/coregraphics-native-v55-stage.json',
    runtime_stage='artifacts/private-procfs-v7-stage.json',
    direct_environment='config/direct-resource-tool-environment-v14.json',
    current_resource_blocker='Original InternationalTextSearch.framework required by ProactiveSupport',
    previous_initialization_timeout_not_observed_in_this_attempt=True,
    initialization_timeout_causality_verified=False, cold_installation_verified=False,
    caveats=['Linux btime supplies second precision; the microsecond field remains zero.',
        'The latest build reaches real resource version queries but still fails; no full App was produced.',
        'CoreSimulator service version queries are still unsupported; its original path-query export itself returns NULL.',
        'Resource output semantics, Unity/UE complete App signing, provisioning and archive/export remain unverified.'])
output.write_text(json.dumps(result, indent=2)+'\n')
print(output.relative_to(root))
