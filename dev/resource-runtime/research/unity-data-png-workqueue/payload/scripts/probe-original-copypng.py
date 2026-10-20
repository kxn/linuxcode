#!/usr/bin/env python3
"""Run original copypng/pngcrush through the configured exact-path tool scope."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,struct,subprocess,tempfile,zlib
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='original-copypng-',dir=root/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();tool='/Applications/Xcode.app/Contents/Developer/usr/bin/copypng';tool_hashes={}
for name in ['copypng','pngcrush']:
 rel='Xcode.app/Contents/Developer/usr/bin/'+name;installed=root/'runtime/state/prefix/Applications'/rel;extracted=root/'runtime/xcode-extract'/rel;assert sha(installed)==sha(extracted);tool_hashes[name]=sha(installed)
inputs=[root/'runtime/unity-ios-cocoapods-ios26-v1/ios'/n for n in ['LaunchScreen-iPhonePortrait.png','LaunchScreen-iPhoneLandscape.png','LaunchScreen-iPad.png']]
chunk=lambda name,data:struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
w,h=17,11;pixels=bytes(c for y in range(h) for x in range(w) for c in [(x*19+y*7)%256,(x*11+y*23)%256,(x*31+y*13)%256,255]);rows=b''.join(b'\0'+pixels[y*w*4:(y+1)*w*4] for y in range(h));synthetic=folder/'opaque-pattern.png';synthetic.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''));inputs.append(synthetic);(folder/'opaque-pattern.rgba').write_bytes(pixels)
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY','failed=0'];cases=[]
for i,source in enumerate(inputs):
 output=folder/('output-'+str(i)+'.png');argv=[tool,'-compress','-strip-PNG-text',guest(source),guest(output)];lines+=[shlex.join(argv),'s=$?',f'printf "ORIGINAL_COPYPNG_{i}_STATUS %s\\n" "$s"','if [ "$s" -ne 0 ]; then failed=1; fi'];cases.append(dict(source=str(source.relative_to(root)),source_sha256=sha(source),output=str(output.relative_to(root)),arguments=argv))
lines.append('exit "$failed"');script=folder/'run.sh';script.write_text('\n'.join(lines)+'\n');command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='180';log=folder/'run.log'
with log.open('w') as out:r=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ORIGINAL_COPYPNG_([0-9]+)_STATUS ([0-9]+)$',t,re.M)
for c in cases:
 output=root/c['output'];c['output_exists']=output.is_file()
 if output.is_file():c.update(output_sha256=sha(output),output_bytes=output.stat().st_size)
verified=r.returncode==0 and statuses==[(str(i),'0') for i in range(len(cases))] and all(c['output_exists'] for c in cases);report=dict(verified=verified,configuration=a.configuration,stage=a.stage,original_tool_sha256=tool_hashes,original_tools_byte_equal_XIP=True,cases=cases,native_statuses=statuses,outer_status=r.returncode,command=command,source_runtime=profile['source_runtime'],log=str(log.relative_to(root)),log_sha256=sha(log),sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/a.configuration,root/a.stage]},independent_pixel_verification=False,full_goal_complete=False);(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-6000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
