#!/usr/bin/env python3
"""Exercise SDK-derived PMR classes across DSOs and preserve expected exceptions."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
build = json.loads((root/args.build).read_text())
assert sha(build['library']) == build['library_sha256']
folder = Path(tempfile.mkdtemp(prefix='pmr-native-', dir=root/'runtime'))
(folder/'libraries').mkdir()
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
flags = ['clang++-19', '-target', 'x86_64-apple-macos26', '-isysroot', str(sdk),
    '-nostdinc++', '-isystem', str(sdk/'usr/include/c++/v1'), '-std=c++23', '-O2', '-fexceptions']
normalize = runpy.run_path(str(root/'scripts/normalize-macho-weak-bind.py'))['normalize']
for name in ['producer','consumer']:
    subprocess.run([*flags, '-c', str(root/('fixtures/hello/pmr-key-'+name+'.cpp')),
                    '-o', str(folder/(name+'.o'))], check=True, cwd=root)
link = ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '26', '26',
    '-no_fixup_chains', '-syslibroot', str(sdk), '-L'+str((root/build['library']).parent), '-lc++', '-lSystem']
fixture = folder/'libraries/libPmrFixture.dylib'
subprocess.run([*link, '-dylib', '-install_name', '/usr/lib/libPmrFixture.dylib',
               str(folder/'producer.o'), '-o', str(fixture)], check=True, cwd=root)
fixture.write_bytes(normalize(fixture.read_bytes())[0])
binary = folder/'pmr-test'
subprocess.run([*link, '-L'+str(folder/'libraries'), '-lPmrFixture', str(folder/'consumer.o'),
               '-o', str(binary)], check=True, cwd=root)
binary.write_bytes(normalize(binary.read_bytes())[0])
# Keep every prior exception/lifetime assertion; only relocate its explicit
# expected owner path because the old components now live in the new wrapper.
old_expected = root/'fixtures/hello/expected-access-source.cpp'
source = old_expected.read_text()
old_owner = '/expected-access-source/libraries/libc++.1.dylib'
new_owner = '/'+build['library']
assert source.count(old_owner) == 1
adapted = folder/'expected-owner-relocated.cpp'
adapted.write_text(source.replace(old_owner,new_owner))
subprocess.run([*flags, '-I'+str(root/'fixtures/hello'), '-c', str(adapted),
               '-o', str(folder/'expected.o')], check=True, cwd=root)
prior = json.loads((root/'artifacts/expected-access-source-test.json').read_text())
assert sha(prior['fixture']) == prior['fixture_sha256']
expected = folder/'expected-test'
subprocess.run([*link, '-L'+str((root/prior['fixture']).parent), '-lExpectedFixture',
               str(folder/'expected.o'), '-o', str(expected)], check=True, cwd=root)
expected.write_bytes(normalize(expected.read_bytes())[0])
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p = module['profile'](stage=args.stage, configuration=args.configuration)
env = module['environment'](p)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:
    env.pop(key,None)
guest = lambda path: '/Volumes/SystemRoot/workspace/'+str(path)
scope = p['direct_resource_environment']['tool_environment']
cases = []
for label, program in [('missing',binary), ('present',binary), ('expected',expected)]:
    command = list(p['command'][:-2])
    for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
        at = next(i for i,arg in enumerate(command) if arg.startswith(key+'='))
        value = scope[key]
        if key == 'DYLD_LIBRARY_PATH':
            paths = [str(folder.relative_to(root)/'libraries'),str(Path(prior['fixture']).parent)]
            if label != 'missing': paths.insert(0,str(Path(build['library']).parent))
            value = ':'.join(guest(path) for path in paths)+':'+value
        command[at] = key+'='+value
    script = folder/(label+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        guest(program.relative_to(root))+'\nstatus=$?\nprintf "PMR_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command += ['/bin/bash',guest(script.relative_to(root))]
    command[3] = '120'
    log = folder/(label+'.log')
    with log.open('w') as out:
        result = subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^PMR_NATIVE_STATUS (\d+)$',text,re.M)
    marker = ('PMR_SDK_KEY_FUNCTION_RTTI_VTABLE_CROSS_DSO_VIRTUAL_ALLOC_ALIGNMENT_FAILURE_AND_DESTRUCTION_OK'
        if label == 'present' else 'EXPECTED_ACCESS_SOURCE_RTTI_VTABLE_CROSS_DYLIB_THROW_CATCH_RETHROW_AND_LIFETIME_OK')
    verified = (result.returncode != 0 and 'Symbol not found' in text and 'memory_resource' in text
        if label == 'missing' else result.returncode == 0 and statuses == ['0'] and marker in text)
    if label == 'present' and verified:
        owner = re.search(r'^PMR_CANONICAL_TYPE_OWNER (.+)$',text,re.M)
        assert owner and owner[1].endswith(build['library'])
    cases.append(dict(mode=label,verified=verified,outer_status=result.returncode,native_status=statuses,
        log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)),command=command))
    print(label,result.returncode,text[-2000:],flush=True)
    if not verified: break
verified = len(cases)==3 and all(case['verified'] for case in cases)
sources = ['scripts/probe-pmr-key-function.py','fixtures/hello/pmr-key-fixture.h',
    'fixtures/hello/pmr-key-producer.cpp','fixtures/hello/pmr-key-consumer.cpp',
    'fixtures/hello/expected-access-source.cpp']
report = dict(verified=verified,build=args.build,build_sha256=sha(args.build),
    library=build['library'],library_sha256=sha(build['library']),cases=cases,
    sources={path:sha(path) for path in sources},fixture=str(fixture.relative_to(root)),
    fixture_sha256=sha(fixture.relative_to(root)),old_expected_fixture=prior['fixture'],
    old_expected_fixture_sha256=sha(prior['fixture']),
    existing_expected_test_only_owner_path_changed=True,relocated_source=str(adapted.relative_to(root)),
    relocated_source_sha256=sha(adapted.relative_to(root)),old_owner=old_owner,new_owner=new_owner,
    full_PMR_runtime=False,full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
