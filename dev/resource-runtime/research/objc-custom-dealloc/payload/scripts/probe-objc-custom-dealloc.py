#!/usr/bin/env python3
"""Exercise custom deallocation in the actual source-built objc4 runtime."""
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
parser.add_argument('--configuration', required=True)
parser.add_argument('--baseline-probe', required=True)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
read = lambda n: json.loads((root/n).read_text())
sha = lambda n: hashlib.sha256((root/n).read_bytes()).hexdigest()
folder = Path(tempfile.mkdtemp(prefix='objc-custom-dealloc-native-', dir=root/'runtime'))
config = read(args.configuration)
build = read(config['objc_source_build'])
provider = build['library']
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = 'fixtures/hello/objc-custom-dealloc.m'
obj, program = folder/'test.o', folder/'test'
commands = [
    ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
     '-I'+str((root/provider).parent/'include'), '-O2',
     '-c', str(root/source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
     '-syslibroot', str(sdk), '-lobjc', '-lSystem', '-no_fixup_chains',
     '-no_adhoc_codesign', str(obj), '-o', str(program)]]
compile_log = folder/'compile.log'
with compile_log.open('w') as out:
    for command in commands:
        subprocess.run(command, cwd=root, check=True, stdout=out, stderr=subprocess.STDOUT)
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p = module['profile'](stage=args.stage, configuration=args.configuration)
env = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(key, None)
scope = p['direct_resource_environment']['tool_environment']
oldscope = read(args.baseline_probe)['scope']['tool_environment']
guest = lambda n: '/Volumes/SystemRoot/workspace/'+str(n)
cases = []
for mode, raw, action in [('missing', False, 'normal'), ('nonpointer', False, 'normal'),
                          ('raw', True, 'normal'), ('wrong-count', False, 'wrong-count'),
                          ('weak-fatal', False, 'weak-fatal'),
                          ('raw-weak-fatal', True, 'weak-fatal')]:
    command = list(p['command'][:-2])
    selected = oldscope if mode == 'missing' else scope
    for key in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']:
        at = next(i for i, value in enumerate(command) if value.startswith(key+'='))
        command[at] = key+'='+selected[key]
    option = 'OBJC_DISABLE_NONPOINTER_ISA='+('YES' if raw else 'NO')
    existing = [i for i, value in enumerate(command) if value.startswith('OBJC_DISABLE_NONPOINTER_ISA=')]
    if existing:
        command[existing[0]] = option
    else:
        command.append(option)
    script = folder/(mode+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
                      shlex.join([guest(program.relative_to(root)), '/'+provider,
                                  str(int(raw)), action])+ '\nstatus=$?\n'+
                      'printf "CUSTOM_DEALLOC_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command += ['/bin/bash', guest(script.relative_to(root))]
    command[3] = '120'
    log = folder/(mode+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^CUSTOM_DEALLOC_NATIVE_STATUS (\d+)$', text, re.M)
    counts = re.findall(r'CUSTOM_DEALLOC_REAL_INHERITANCE_THREADS_WEAK_AUTORELEASE_OK (\d+) raw=(\d)', text)
    if mode == 'missing':
        verified = result.returncode == 12 and statuses == ['12'] and 'CUSTOM_DEALLOC_API_MISSING' in text
    elif 'weak-fatal' in mode:
        verified = (result.returncode != 0 and result.returncode != 16 and
                    'CUSTOM_DEALLOC_WEAK_FATAL_EXPECTED' in text and
                    'Cannot form weak reference' in text)
    elif mode == 'wrong-count':
        verified = result.returncode == 15 and statuses == ['15'] and 'destroyed == 12' in text
    else:
        verified = (result.returncode == 0 and statuses == ['0'] and len(counts) == 1 and
                    int(counts[0][0]) > 1400 and counts[0][1] == str(int(raw)))
    cases.append(dict(mode=mode, raw_isa=raw, verified=verified, outer_status=result.returncode,
                      native_status=statuses, checks=int(counts[0][0]) if counts else None,
                      log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)), command=command))
    print(mode, result.returncode, text[-1800:], flush=True)
    if not verified:
        break
report = dict(verified=len(cases) == 6 and all(c['verified'] for c in cases), cases=cases,
              build=config['objc_source_build'], build_sha256=sha(config['objc_source_build']),
              provider=provider, provider_sha256=sha(provider), compile_commands=commands,
              compile_log=str(compile_log.relative_to(root)),
              sources={n: sha(n) for n in [source, 'scripts/probe-objc-custom-dealloc.py',
                                         args.configuration, args.baseline_probe]},
              complete_Unity_App_verified=False, full_ObjC_API_compatibility_verified=False)
(folder/'result.json').write_text(json.dumps(report, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if report['verified'] else 1)
