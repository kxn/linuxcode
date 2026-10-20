#!/usr/bin/env python3
"""Validate a complete source-built backend and existing libc++ consumers."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
sha = lambda p: hashlib.sha256((root/p).read_bytes()).hexdigest()
read = lambda p: json.loads((root/p).read_text())
build = read(args.build)
assert build['linked'] and not build['previous_backend_missing_exports']
assert sha(build['library']) == build['library_sha256']
assert build['standard'] == 'c++20'
assert build['Apple_force_weak_and_notweak_policies_applied'] and build['existing_export_flags_preserved']
for source, digest in build['sources'].items():
    assert sha(source) == digest, source
folder = Path(tempfile.mkdtemp(prefix='codecvt-char8-native-', dir=root/'runtime'))
(folder/'libraries').mkdir()
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
flags = ['clang++-19', '-target', 'x86_64-apple-macos26', '-isysroot', str(sdk),
    '-nostdinc++', '-isystem', str(sdk/'usr/include/c++/v1'), '-std=c++20', '-O2', '-fexceptions']
normalize = runpy.run_path(str(root/'scripts/normalize-macho-weak-bind.py'))['normalize']
link = ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '26', '26',
    '-no_fixup_chains', '-syslibroot', str(sdk), '-lc++', '-lSystem']
for name in ['producer', 'consumer']:
    subprocess.run([*flags, '-c', str(root/('fixtures/hello/codecvt-char8-'+name+'.cpp')),
        '-o', str(folder/(name+'.o'))], check=True, cwd=root)
fixture = folder/'libraries/libChar8Fixture.dylib'
subprocess.run([*link, '-dylib', '-install_name', '/usr/lib/libChar8Fixture.dylib',
    str(folder/'producer.o'), '-o', str(fixture)], check=True, cwd=root)
fixture.write_bytes(normalize(fixture.read_bytes())[0])
binary = folder/'char8-test'
subprocess.run([*link, '-L'+str(folder/'libraries'), '-lChar8Fixture',
    str(folder/'consumer.o'), '-o', str(binary)], check=True, cwd=root)
binary.write_bytes(normalize(binary.read_bytes())[0])
previous_pmr = read('runtime/pmr-native-m8wnompx/result.json')
assert previous_pmr['verified']
previous_format = read('artifacts/typed-new-delete-to-chars-test.json')
assert sha(previous_format['source']) == previous_format['source_sha256']
assert sha(previous_format['reference_log']) == previous_format['reference_log_sha256']
format_source = root/previous_format['source']
subprocess.run([*flags, '-DLINUXCODE_LIBCXX_EXPECTED_PROVIDER="/pmr-key-function-v1/libraries/libc++.1.dylib"',
    '-c', str(format_source), '-o', str(folder/'format.o')], check=True, cwd=root)
format_binary = folder/'format-test'
subprocess.run([*link, str(folder/'format.o'), '-o', str(format_binary)], check=True, cwd=root)
format_binary.write_bytes(normalize(format_binary.read_bytes())[0])
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p = module['profile'](stage=args.stage, configuration=args.configuration)
environment = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    environment.pop(key, None)
scope = p['direct_resource_environment']['tool_environment']
guest = lambda path: '/Volumes/SystemRoot/workspace/'+str(path)
backend_directory = str(Path(build['library']).parent)
assert {f.name for f in (root/backend_directory).iterdir()} == {'libc++0.dylib'}
cases = []
programs = [('missing', binary), ('present', binary),
    ('pmr', root/'runtime/pmr-native-m8wnompx/pmr-test'),
    ('expected', root/'runtime/pmr-native-m8wnompx/expected-test'), ('format', format_binary)]
markers = dict(present='CHAR8_CLASSIC_NAMED_GLOBAL_CROSS_DSO_ALL_UNICODE_SCALARS_ERRORS_PARTIAL_LIFETIME_THREADS_AND_STREAMS_OK',
    pmr='PMR_SDK_KEY_FUNCTION_RTTI_VTABLE_CROSS_DSO_VIRTUAL_ALLOC_ALIGNMENT_FAILURE_AND_DESTRUCTION_OK',
    expected='EXPECTED_ACCESS_SOURCE_RTTI_VTABLE_CROSS_DYLIB_THROW_CATCH_RETHROW_AND_LIFETIME_OK',
    format='REAL_LIBCXX_')
for mode, program in programs:
    command = list(p['command'][:-2])
    extra = [str(folder.relative_to(root)/'libraries'), 'runtime/pmr-native-m8wnompx/libraries',
        str(Path(previous_pmr['old_expected_fixture']).parent)]
    if mode != 'missing':
        extra.insert(0, backend_directory)
    for key in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']:
        at = next(i for i, value in enumerate(command) if value.startswith(key+'='))
        value = scope[key]
        if key == 'DYLD_LIBRARY_PATH':
            value = ':'.join(guest(path) for path in extra)+':'+value
        command[at] = key+'='+value
    script = folder/(mode+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join([guest(program.relative_to(root))])+ '\nstatus=$?\nprintf "CHAR8_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command += ['/bin/bash', guest(script.relative_to(root))]
    command[3] = '120'
    log = folder/(mode+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^CHAR8_NATIVE_STATUS (\d+)$', text, re.M)
    verified = (result.returncode != 0 and 'Symbol not found' in text and 'codecvt' in text
        if mode == 'missing' else result.returncode == 0 and statuses == ['0'] and markers[mode] in text)
    if mode == 'present' and verified:
        owner = re.search(r'^CHAR8_CANONICAL_ID_OWNER (.+)$', text, re.M)
        verified = bool(owner and owner[1].endswith(build['library']))
    variation_count = None
    if mode == 'format' and verified:
        actual = [line for line in text.splitlines() if line.startswith(('D0P','D1P','D2P','D3P','D4P','F0P','F1P','F2P','F3P','F4P','L0 ','L1 ','L2 ','REAL_LIBCXX_'))]
        expected = (root/previous_format['reference_log']).read_text().splitlines()
        verified = len(actual) == len(expected)
        variation_count = 0
        for left, right in zip(actual, expected):
            if left == right:
                continue
            a, b = left.split(), right.split()
            if a[:2] != b[:2] or a[0] not in ('D4P-1','F4P-1'):
                verified = False
            variation_count += 1
    cases.append(dict(mode=mode, verified=verified, outer_status=result.returncode, native_status=statuses,
        program=str(program.relative_to(root)), program_sha256=sha(program.relative_to(root)),
        log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)),
        hex_normalization_variations=variation_count, command=command))
    print(mode, result.returncode, text[-1800:], flush=True)
    if not verified:
        break
sources = ['scripts/probe-libcxx-char8-backend.py', 'fixtures/hello/codecvt-char8-fixture.h',
    'fixtures/hello/codecvt-char8-producer.cpp', 'fixtures/hello/codecvt-char8-consumer.cpp', previous_format['source']]
record = dict(verified=len(cases)==len(programs) and all(c['verified'] for c in cases),
    build=args.build, build_sha256=sha(args.build), library=build['library'], library_sha256=sha(build['library']),
    configuration=args.configuration, stage=args.stage, cases=cases,
    fixture=str(fixture.relative_to(root)), fixture_sha256=sha(fixture.relative_to(root)),
    sources={path: sha(path) for path in sources}, reference_format_log=previous_format['reference_log'],
    reference_format_log_sha256=sha(previous_format['reference_log']),
    previous_PMR_probe='runtime/pmr-native-m8wnompx/result.json',
    previous_PMR_probe_sha256=sha('runtime/pmr-native-m8wnompx/result.json'),
    full_resource_compilation_verified=False, installed=False)
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
