#!/usr/bin/env python3
"""Inspect a real constant-only candidate and run original dyld_info controls."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import struct
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target',required=True)
parser.add_argument('--stage',required=True)
args=parser.parse_args()
pin=json.loads((root/'config/coregraphics-image-pins.json').read_text())[args.target]
original_path=root/('runtime/fullsystem-libraries'+pin['path'])
candidate_path=root/('runtime/rebuilt-'+args.target)/Path(pin['path']).name
original,candidate=original_path.read_bytes(),candidate_path.read_bytes()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(original_path)==pin['sha256']
module=runpy.run_path(str(root/'scripts/original-constant-image.py'))
assert json.loads(json.dumps(module['validate_original'](original)))==pin['original_constant_only_image']
positive=module['inspect'](original,candidate)
before,after=module['layout'](original),module['layout'](candidate)
controls=[]

def reject(label,broken,original_control=False):
    try:
        if original_control:module['validate_original'](bytes(broken))
        else:module['inspect'](original,bytes(broken))
    except (AssertionError,ValueError,struct.error,UnicodeDecodeError):
        controls.append(dict(case=label,rejected=True))
    else:raise AssertionError('Accepted '+label)

bad=bytearray(candidate);bad[after['sections']['__TEXT','__const'][2]]^=1
reject('changed_constant_bytes',bad)
uuid=next(at for k,at,raw in after['commands'] if k==0x1b)
bad=bytearray(candidate);bad[uuid+8]^=1;reject('changed_uuid',bad)
sym=next(at for k,at,raw in after['commands'] if k==2)
symoff=struct.unpack_from('<I',candidate,sym+8)[0]
bad=bytearray(candidate);bad[symoff+8]^=1;reject('changed_private_symbol_address',bad)
seg=next(at for k,at,raw in before['commands'] if k==0x19 and raw[8:24].rstrip(b'\0')==b'__TEXT')
bad=bytearray(original);struct.pack_into('<Q',bad,seg+72+40,1)
reject('original_nonempty_executable_section',bad,True)
dep=next(at for k,at,raw in after['commands'] if k==0xc)
bad=bytearray(candidate);bad[dep+struct.unpack_from('<I',candidate,dep+8)[0]]^=1
reject('changed_dependency',bad)
folder=Path(tempfile.mkdtemp(prefix='original-constant-image-',dir=root/'runtime'))
bad=bytearray(candidate);struct.pack_into('<I',bad,36,4)
header=folder/'bad-header.dylib';header.write_bytes(bad)
seg=next(at for k,at,raw in after['commands'] if k==0x19 and raw[8:24].rstrip(b'\0')==b'__TEXT')
bad=bytearray(candidate);struct.pack_into('<Q',bad,seg+40,len(candidate)+4096)
segment=folder/'bad-segment.dylib';segment.write_bytes(bad)
tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/dyld_info'
installed=root/('runtime/state/prefix'+tool)
extracted=root/'runtime/xcode-extract/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/dyld_info'
assert sha(installed)==sha(extracted)
script=folder/'validate.sh';lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
for label,path in [('valid',candidate_path),('bad-header',header),('bad-segment',segment)]:
    lines += [shlex.join([tool,'-validate_only','/Volumes/SystemRoot/workspace/'+str(path.relative_to(root))]),
              'status=$?', 'printf "CONSTANT_IMAGE_CASE '+label+' %s\\n" "$status"']
script.write_text('\n'.join(lines)+'\n')
profile=runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
p=profile['profile'](stage=args.stage);env=profile['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
command=p['command'][:-2]+['/bin/bash','/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
command[3]='90';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
cases=re.findall(r'^CONSTANT_IMAGE_CASE (\S+) (\d+)$',log.read_text(),re.M)
verified=result.returncode==0 and cases==[('valid','0'),('bad-header','1'),('bad-segment','1')]
report=dict(verified=verified,target=args.target,independent_inspection=positive,
            corruption_controls=controls,format_validation_only=True,runtime_behavior_verified=False,
            cases=cases,outer_status=result.returncode,command=command,
            log=str(log.relative_to(root)),log_sha256=sha(log),
            original_tool_sha256=sha(installed),original_tool_bytes_equal_extracted=True,
            sources={str(q.relative_to(root)):sha(q) for q in [Path(__file__),root/'scripts/original-constant-image.py',
                    root/'scripts/original-reexport-facade.py',root/'scripts/verify-dysymtab-alias-repair.py']})
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(log.read_text()[-2500:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
