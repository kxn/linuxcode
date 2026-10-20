#!/usr/bin/env python3
"""Validate explicit original candidates and damaged controls in one session."""
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
parser.add_argument('--preparation-report',required=True)
parser.add_argument('--stage',required=True)
args=parser.parse_args()
sha=lambda path:hashlib.sha256((root/path).read_bytes()).hexdigest()
prepared=json.loads((root/args.preparation_report).read_text())
assert prepared['complete']
pins=json.loads((root/'config/coregraphics-image-pins.json').read_text())
folder=Path(tempfile.mkdtemp(prefix='original-dyld-validation-batch-',dir=root/'runtime'))
tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/dyld_info'
installed='runtime/state/prefix'+tool
extracted='runtime/xcode-extract/Xcode.app/Contents/Developer'+tool.split('/Contents/Developer',1)[1]
assert sha(installed)==sha(extracted)


def commands(data):
    assert data[:8]==bytes.fromhex('cffaedfe07000001')
    cursor=32
    result=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,cursor)
        assert size>=8 and cursor+size<=len(data)
        result.append((command,cursor,size))
        cursor+=size
    return result


def uuid(data):
    values=[data[at+8:at+24] for command,at,size in commands(data) if command==0x1b]
    assert len(values)==1
    return values[0]


inputs=[]
lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
for row in prepared['images']:
    target=row['prepared_target']
    assert target and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in target)
    assert not any(item['target']==target for item in inputs)
    pin=pins[target]
    original='runtime/fullsystem-libraries'+pin['path']
    image='runtime/rebuilt-'+target+'/'+Path(pin['path']).name
    reconstructed=json.loads((root/('runtime/rebuilt-'+target+'/reconstruction.json')).read_text())
    assert sha(original)==pin['sha256']==reconstructed['original_image_sha256']
    assert sha(image)==reconstructed['staged_image_sha256']
    data=(root/image).read_bytes()
    assert uuid(data)==uuid((root/original).read_bytes())
    broken_header=bytearray(data);struct.pack_into('<I',broken_header,36,4)
    header=folder/(target+'-bad-command-size.dylib');header.write_bytes(broken_header)
    bind=next(at for command,at,size in commands(data) if command in (0x22,0x80000022))
    off,size=struct.unpack_from('<II',data,bind+16);blob=data[off:off+size];cursor=0
    while cursor<len(blob):
        start=cursor;opcode=blob[cursor]&0xf0;cursor+=1
        if opcode==0x70:break
        if opcode==0x40:cursor=blob.index(0,cursor)+1
        elif opcode in (0x20,0x60):
            while blob[cursor]&128:cursor+=1
            cursor+=1
        else:assert opcode in (0,0x10,0x30,0x50,0x90)
    else:raise ValueError('No binding segment opcode: '+target)
    assert len([c for c,at,size in commands(data) if c==0x19])<15
    broken_bind=bytearray(data);broken_bind[off+start]=0x7f
    binding=folder/(target+'-bad-binding-segment.dylib');binding.write_bytes(broken_bind)
    inputs.append(dict(target=target,image=image,image_sha256=sha(image),original=original,
        reference_image_sha256=sha(original),original_uuid=uuid(data).hex()))
    for mode,path in [('valid',root/image),('bad-header',header),('bad-binding',binding)]:
        lines += [shlex.join([tool,'-validate_only','/Volumes/SystemRoot/workspace/'+str(path.relative_to(root))]),
            'status=$?', 'printf "APPLE_DYLD_BATCH_CASE '+target+' '+mode+' %s\\n" "$status"']
lines.append('exit 0')
script=folder/'validate.sh';script.write_text('\n'.join(lines)+'\n')
module=runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
p=module['profile'](stage=args.stage)
command=p['command'][:-2]+['/bin/bash','/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
command[3]='180';env=module['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^APPLE_DYLD_BATCH_CASE (\S+) (\S+) (\d+)$',text,re.M)
assert len(statuses)==len(set((target,mode) for target,mode,status in statuses)), 'Duplicate result markers'
assert not set(target for target,mode,status in statuses)-{row['target'] for row in inputs}
reports=[]
for row in inputs:
    cases=[(mode,status) for target,mode,status in statuses if target==row['target']]
    verified=result.returncode==0 and cases==[('valid','0'),('bad-header','1'),('bad-binding','1')]
    assert sha(row['image'])==row['image_sha256'] and sha(row['original'])==row['reference_image_sha256']
    record=dict(verified=verified,format_validation_only=True,runtime_execution_verified=False,
        **row,tool=tool,tool_sha256=sha(installed),original_tool_bytes_equal_extracted=True,
        stage=args.stage,command=command,outer_status=result.returncode,cases=cases,
        log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)),
        sources={str(Path(__file__).relative_to(root)):sha(Path(__file__).relative_to(root))})
    path=folder/(row['target']+'-result.json');path.write_text(json.dumps(record,indent=2)+'\n')
    reports.append(dict(target=row['target'],report=str(path.relative_to(root)),verified=verified))
assert sha(installed)==sha(extracted)
record=dict(verified=bool(reports) and all(row['verified'] for row in reports),
    preparation_report=args.preparation_report,preparation_report_sha256=sha(args.preparation_report),
    serialized_native_session=True,format_validation_only=True,runtime_execution_verified=False,
    reports=reports,outer_status=result.returncode,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)))
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-2500:])
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
