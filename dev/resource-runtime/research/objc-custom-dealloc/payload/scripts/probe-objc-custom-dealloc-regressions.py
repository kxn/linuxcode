#!/usr/bin/env python3
"""Run the existing objc4 regression checks in the selected resource-tool scope."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
args = parser.parse_args()
sha = lambda name: hashlib.sha256((root/name).read_bytes()).hexdigest()
reference = json.loads((root/'artifacts/objc-selector-source-test.json').read_text())
assert reference['runtime_execution_verified']
for name, digest in reference['sources'].items():
    assert sha(name) == digest
folder = Path(tempfile.mkdtemp(prefix='objc-custom-dealloc-regressions-', dir=root/'runtime'))
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p = module['profile'](stage=args.stage, configuration=args.configuration)
configuration = json.loads((root/args.configuration).read_text())
build = json.loads((root/configuration['objc_source_build']).read_text())
derived = {}
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
# Two old tests pin their implementation owner by exact filename. Preserve that
# assertion while adapting its single literal to the new immutable candidate.
for name, original in [('selector', 'fixtures/hello/objc-selector-native.c'),
                       ('signatures', 'fixtures/hello/objc-selector-signatures.m')]:
    text = (root/original).read_text()
    old = '"/runtime/objc-selector-source/libobjc.A.dylib"'
    assert text.count(old) == 1
    source = folder/(name+Path(original).suffix)
    source.write_text(text.replace(old, json.dumps('/'+build['library'])))
    obj = folder/(name+'.o')
    subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
        '-O2', '-fblocks', '-c', str(source), '-o', str(obj)], check=True)
    executable = folder/name
    subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
        '-syslibroot', str(sdk), '-L', str(guest/'usr/lib'), '-L', str(guest/'usr/lib/system'),
        '-lobjc', '-lSystem', *(['-framework', 'Foundation', '-framework', 'CoreFoundation']
                              if name == 'signatures' else []), str(obj), '-o', str(executable)], check=True)
    derived[name] = dict(source=str(source.relative_to(root)), source_sha256=sha(source.relative_to(root)),
        original=original, original_sha256=sha(original), binary=str(executable.relative_to(root)),
        binary_sha256=sha(executable.relative_to(root)), expected_owner=build['library'])
prefix = '/Volumes/SystemRoot/workspace/'
helper = prefix+'runtime/objc-selector-source/libraries/libDarlingObjCEnumeration.dylib'
binary = lambda name: 'runtime/objc-selector-source/tests/'+name
entries = [
    ('direct', 'selector', [prefix+build['library']], 'OBJC_SELECTOR_EXISTING_IDENTITY_UNKNOWN_NO_REGISTRATION_UTF8_AND_CONCURRENT_GROWTH_OK'),
    ('helper', 'selector', [helper], 'OBJC_SELECTOR_EXISTING_IDENTITY_UNKNOWN_NO_REGISTRATION_UTF8_AND_CONCURRENT_GROWTH_OK'),
    ('enumeration', 'enumeration', [helper, prefix+binary('plugin.dylib')], 'OBJC_ENUMERATION_CALLER_HEADER_HANDLES_FILTERS_DYNAMIC_STOP_AND_LAZY_METADATA_OK'),
    ('signatures', 'signatures', [], 'SOURCE_OBJC_NATIVE_INVOCATION_INTEGER_DOUBLE_AND_STRUCT_RETURN_OK'),
    ('tagged', 'tagged', [], 'SOURCE_OBJC_TAGGED_19_BASIC_EXTENDED_BOUNDARIES_CLASS_DISPATCH_RR_WEAK_AND_HEAP_OK')]
cases = []
for mode, name, tail, marker in entries:
    assert sha(binary(name)) == reference['binaries'][binary(name)]
    if mode == 'enumeration':
        assert sha(binary('plugin.dylib')) == reference['binaries'][binary('plugin.dylib')]
    command = list(p['command'][:-2])
    scope = p['direct_resource_environment']['tool_environment']
    for key in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']:
        at = next(i for i, value in enumerate(command) if value.startswith(key+'='))
        command[at] = key+'='+scope[key]
    command += [prefix+(derived[name]['binary'] if name in derived else binary(name)), *tail]
    log = folder/(mode+'.log')
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=root, env=module['environment'](p), stdout=stream, stderr=subprocess.STDOUT)
    text = log.read_text()
    verified = result.returncode == 0 and marker in text
    cases.append(dict(mode=mode, verified=verified, exit_status=result.returncode,
        log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)), command=command))
    print(mode, verified, text[-1000:], flush=True)
    if not verified: break
record = dict(verified=len(cases) == 5 and all(case['verified'] for case in cases),
    cases=cases, adapted_exact_owner_checks=derived, source='scripts/probe-objc-custom-dealloc-regressions.py',
    original_regression_driver='scripts/probe-objc-data-const-regressions.py',
    original_regression_driver_sha256=sha('scripts/probe-objc-data-const-regressions.py'),
    source_sha256=sha('scripts/probe-objc-custom-dealloc-regressions.py'),
    reference='artifacts/objc-selector-source-test.json', reference_sha256=sha('artifacts/objc-selector-source-test.json'),
    configuration=args.configuration, configuration_sha256=sha(args.configuration), stage=args.stage,
    full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
