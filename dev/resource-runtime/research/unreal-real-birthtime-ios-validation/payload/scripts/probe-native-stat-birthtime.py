#!/usr/bin/env python3
"""Compare poisoned Darwin stat outputs with genuine Linux statx birth times."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shlex, struct, subprocess, tempfile, ctypes, os, time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--expect-mismatch', action='store_true')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='native-stat-birthtime-', dir=root / 'runtime'))
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = root / 'fixtures/hello/native-stat-birthtime.c'
commands = [['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-std=gnu11', '-O1', '-c', str(source), '-o', str(folder / 'test.o')],
            ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(sdk), '-lSystem', str(folder / 'test.o'), '-o', str(folder / 'test')]]
for command in commands: subprocess.run(command, check=True)
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
command = list(profile['command']); scope = profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']:
    index = next(i for i, value in enumerate(command) if value.startswith(key + '=')); command[index] = key + '=' + scope[key]
guest = lambda p: '/Volumes/SystemRoot/workspace/' + str(p.relative_to(root))
script = folder / 'run.sh'
(folder/'regular').write_text('real birth time input\n');(folder/'directory').mkdir();time.sleep(0.02);(folder/'link').symlink_to('regular');(folder/'unlinked').write_text('open then unlink\n')
libc=ctypes.CDLL(None,use_errno=True)
def birth(path,flags=0):
    buffer=ctypes.create_string_buffer(256);result=libc.statx(-100,os.fsencode(path),flags,0x800,buffer);assert result==0,ctypes.get_errno();mask=struct.unpack_from('<I',buffer.raw)[0];assert mask&0x800,'This probe requires real STATX_BTIME support';return struct.unpack_from('<qI',buffer.raw,80)
expected={name:birth(folder/path,flags) for name,path,flags in [('stat-regular','regular',0),('fstat-regular','regular',0),('stat-directory','directory',0),('lstat-link','link',0x100),('stat-link-follow','link',0),('fstatat-regular','regular',0),('fstat-unlinked','unlinked',0)]}
assert expected['lstat-link'] != expected['stat-link-follow'], 'Link and target must have distinguishable genuine birth times'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(folder/'test'),guest(folder)])+'\ns=$?\nprintf "BIRTHTIME_STATUS %s\\n" "$s"\nexit "$s"\n')
command = command[:-2] + ['/bin/bash', guest(script)]; command[3] = '65'
log = folder / 'run.log'; print('RUNNING', folder.relative_to(root), flush=True)
with log.open('w') as stream: result = subprocess.run(command, cwd=root, env=module['environment'](profile), stdout=stream, stderr=subprocess.STDOUT)
output = log.read_text()
actual={name:(int(sec),int(nsec)) for name,sec,nsec in re.findall(r'^BIRTHTIME_CASE (\S+) (-?\d+) (-?\d+)$',output,re.M)}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
executed=result.returncode==0 and set(actual)==set(expected) and 'BIRTHTIME_STATUS 0' in output
matched=actual==expected
record=dict(verified=executed and (not matched if args.expect_mismatch else matched),all_real_birth_times_match=matched,expected_mismatch=args.expect_mismatch,expected=expected,actual=actual,poisoned_output_buffer='0xa5 before every stat family call',stage=args.stage,configuration=args.configuration,command=command,commands=commands,outer_status=result.returncode,log=str(log.relative_to(root)),log_sha256=sha(log),source_sha256=sha(source),driver_sha256=sha(Path(__file__)),full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(output[-2600:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if record['verified'] else 1)
