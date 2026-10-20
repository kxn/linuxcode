#!/usr/bin/env python3
"""Exercise the actual primary exception ABI and existing libc++ consumers."""
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
sha = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
read = lambda p: json.loads((root / p).read_text())
build = read(args.build)
assert build['linked'] and build['complete_source_units'] == 18
assert not build['missing_baseline_exports'] and build['added_exports'] == ['___cxa_init_primary_exception']
assert sha(build['library']) == build['library_sha256']
folder = Path(tempfile.mkdtemp(prefix='cxxabi-primary-native-', dir=root / 'runtime'))
(folder / 'libraries').mkdir()
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
abi = root / 'vendor/darling/src/external/libcxxabi'
flags = ['clang++-19', '-target', 'x86_64-apple-macos26', '-isysroot', str(sdk), '-nostdinc++',
         '-I'+str(abi.parent / 'libcxx/include'), '-I'+str(abi / 'include'), '-I'+str(abi / 'src'),
         '-I'+str(abi.parent / 'libunwind/include'), '-std=c++14', '-O2', '-fexceptions']
commands = []
for name in ['producer', 'consumer']:
    command = [*flags, '-c', str(root / ('fixtures/hello/primary-exception-'+name+'.cpp')),
               '-o', str(folder / (name+'.o'))]
    subprocess.run(command, cwd=root, check=True)
    commands.append(command)
config = read(args.configuration)
cpp = read(config['resource_cpp_build'])
link = ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '26', '26',
        '-no_fixup_chains', '-no_adhoc_codesign', '-syslibroot', str(sdk),
        '-L'+str((root / cpp['library']).parent), '-L'+str((root / build['library']).parent),
        '-lc++', '-lc++abi', '-lSystem']
fixture = folder / 'libraries/libPrimaryExceptionFixture.dylib'
program = folder / 'primary-test'
normalize = runpy.run_path(str(root / 'scripts/normalize-macho-weak-bind.py'))['normalize']
for command, output in [([*link, '-dylib', '-install_name', '/usr/lib/libPrimaryExceptionFixture.dylib',
                         str(folder / 'producer.o'), '-o', str(fixture)], fixture),
                        ([*link, '-L'+str(folder / 'libraries'), '-lPrimaryExceptionFixture',
                          str(folder / 'consumer.o'), '-o', str(program)], program)]:
    subprocess.run(command, cwd=root, check=True)
    output.write_bytes(normalize(output.read_bytes())[0])
    commands.append(command)
profile_module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
p = profile_module['profile'](stage=args.stage, configuration=args.configuration)
env = profile_module['environment'](p)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(name, None)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path)
scope = p['direct_resource_environment']['tool_environment']
cases = []
old = read('runtime/codecvt-char8-native-q6cme232/result.json')
regressions = {row['mode']: row for row in old['cases'] if row['mode'] in ['pmr', 'expected', 'format']}
for mode in ['missing', 'primary', 'pmr', 'expected', 'format']:
    if mode in regressions:
        previous = regressions[mode]
        assert sha(previous['program']) == previous['program_sha256']
        command = list(previous['command'])
        index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_LIBRARY_PATH='))
        command[index] = 'DYLD_LIBRARY_PATH=' + guest(Path(build['library']).parent) + ':' + command[index].partition('=')[2]
    else:
        command = list(p['command'][:-2])
        paths = [guest(folder.relative_to(root) / 'libraries')]
        if mode == 'primary':
            paths.insert(0, guest(Path(build['library']).parent))
        index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_LIBRARY_PATH='))
        command[index] = 'DYLD_LIBRARY_PATH=' + ':'.join(paths) + ':' + scope['DYLD_LIBRARY_PATH']
        script = folder / (mode+'.sh')
        script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
                          shlex.join([guest(program.relative_to(root)), build['library']]) +
                          '\nstatus=$?\nprintf "PRIMARY_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
        command += ['/bin/bash', guest(script.relative_to(root))]
    command[3] = '150'
    log = folder / (mode+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    marker = ('PRIMARY_NATIVE_STATUS' if mode in ['missing', 'primary'] else 'CHAR8_NATIVE_STATUS')
    statuses = re.findall(r'^'+marker+r' (\d+)$', text, re.M)
    if mode == 'missing':
        verified = result.returncode != 0 and 'Symbol not found' in text and '__cxa_init_primary_exception' in text
    else:
        verified = result.returncode == 0 and statuses == ['0']
        if mode == 'primary':
            verified &= 'PRIMARY_EXCEPTION_ABI_REFCOUNT_CROSS_DSO_RETHROW_CLEANUP_AND_4_THREADS_OK' in text
    cases.append(dict(mode=mode, verified=bool(verified), outer_status=result.returncode,
                      native_status=statuses, log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)), command=command))
    print(mode, result.returncode, text[-1700:], flush=True)
    if not verified:
        break
sources = ['scripts/probe-cxxabi-primary-exception.py', 'fixtures/hello/primary-exception-fixture.h',
           'fixtures/hello/primary-exception-producer.cpp', 'fixtures/hello/primary-exception-consumer.cpp']
report = dict(verified=len(cases) == 5 and all(row['verified'] for row in cases),
              build=args.build, build_sha256=sha(args.build), configuration=args.configuration,
              library=build['library'], library_sha256=sha(build['library']), cases=cases,
              commands=commands, fixture=str(fixture.relative_to(root)), fixture_sha256=sha(fixture.relative_to(root)),
              program=str(program.relative_to(root)), program_sha256=sha(program.relative_to(root)),
              original_regression_probe='runtime/codecvt-char8-native-q6cme232/result.json',
              original_regression_probe_sha256=sha('runtime/codecvt-char8-native-q6cme232/result.json'),
              sources={name: sha(name) for name in sources},
              complete_modern_SDK_exception_ptr_support_verified=False,
              full_resource_compilation_verified=False)
(folder / 'result.json').write_text(json.dumps(report, indent=2)+'\n')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if report['verified'] else 1)
