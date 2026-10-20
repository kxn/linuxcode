#!/usr/bin/env python3
"""Validate a genuine code-free facade, real damaged controls, and Apple dyld format."""
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
pins=json.loads((root/'config/coregraphics-image-pins.json').read_text());pin=pins[args.target]
assert pin.get('original_reexport_facade')
original='runtime/fullsystem-libraries'+pin['path']
image='runtime/rebuilt-'+args.target+'/'+Path(pin['path']).name
before=(root/original).read_bytes();after=(root/image).read_bytes()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
assert sha(original)==pin['sha256']
module=runpy.run_path(str(root/'scripts/original-reexport-facade.py'))
proof=module['inspect'](before,after)
layout=module['layout'](after);rejected=[]
def rejects(name,offset,payload,original=False):
    changed=bytearray(before if original else after);changed[offset:offset+len(payload)]=payload
    try:
        if original:module['validate_original'](changed)
        else:module['inspect'](before,changed)
    except (ValueError,struct.error):rejected.append(name)
    else:raise AssertionError('Damaged actual facade accepted: '+name)

segments=[(at,raw) for kind,at,raw in layout['commands'] if kind==0x19]
text_at=next(at for at,raw in segments if raw[8:24].split(b'\0')[0]==b'__TEXT')
rejects('added_executable_bytes',text_at+72+40,struct.pack('<Q',1))
info=layout['sections']['__DATA_CONST','__objc_imageinfo'][2]
rejects('changed_imageinfo',info+4,struct.pack('<I',0))
dep_at,dep=next((at,raw) for kind,at,raw in layout['commands'] if kind==0x8000001f)
depname=struct.unpack_from('<I',dep,8)[0]
rejects('changed_reexport_provider',dep_at+depname+1,b'x')
rejects('reexport_changed_to_load',dep_at,struct.pack('<I',0xc))
uuid_at=next(at for kind,at,raw in layout['commands'] if kind==0x1b)
rejects('changed_uuid',uuid_at+8,bytes([after[uuid_at+8]^1]))
build_at=next(at for kind,at,raw in layout['commands'] if kind==0x32)
rejects('unexpected_initializer_command',build_at,struct.pack('<I',0x1a))
old=module['layout'](before)
oldtext=next(at for kind,at,raw in old['commands'] if kind==0x19 and raw[8:24].split(b'\0')[0]==b'__TEXT')
rejects('nonempty_original_code',oldtext+72+40,struct.pack('<Q',1),original=True)
folder=Path(tempfile.mkdtemp(prefix='original-reexport-facade-',dir=root/'runtime'))
badheader=bytearray(after);struct.pack_into('<I',badheader,36,4)
badname=bytearray(after);struct.pack_into('<I',badname,dep_at+8,len(dep))
(folder/'bad-command-size.dylib').write_bytes(badheader)
(folder/'bad-reexport-name.dylib').write_bytes(badname)
tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/dyld_info'
installed='runtime/state/prefix'+tool
extracted='runtime/xcode-extract/Xcode.app/Contents/Developer'+tool.split('/Contents/Developer',1)[1]
assert sha(installed)==sha(extracted)
lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
for label,p in [('valid',root/image),('bad-header',folder/'bad-command-size.dylib'),('bad-reexport-name',folder/'bad-reexport-name.dylib')]:
    lines += [shlex.join([tool,'-validate_only','/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))]),
        'status=$?', 'printf "ORIGINAL_FACADE_CASE '+label+' %s\\n" "$status"']
lines.append('exit 0');script=folder/'validate.sh';script.write_text('\n'.join(lines)+'\n')
profile_module=runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
profile=profile_module['profile'](stage=args.stage)
command=profile['command'][:-2]+['/bin/bash','/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))];command[3]='90'
env=profile_module['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
log=folder/'run.log'
with log.open('w') as stream:result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
text=log.read_text();cases=re.findall(r'^ORIGINAL_FACADE_CASE (\S+) (\d+)$',text,re.M)
verified=result.returncode==0 and cases==[('valid','0'),('bad-header','1'),('bad-reexport-name','1')]
assert sha(original)==proof['original_sha256'] and sha(image)==proof['candidate_sha256']
record=dict(verified=bool(verified),target=args.target,original=original,image=image,inspection=proof,
    rejected_actual_corruptions=rejected,format_validation_only=True,runtime_execution_verified=False,
    original_tool_bytes_equal_extracted=True,tool=tool,tool_sha256=sha(installed),stage=args.stage,
    outer_status=result.returncode,cases=cases,command=command,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)),
    sources={p:sha(p) for p in ['scripts/original-reexport-facade.py',str(Path(__file__).relative_to(root)),
        'artifacts/'+args.target+'-input.json','runtime/rebuilt-'+args.target+'/reconstruction.json']})
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-2400:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
