#!/usr/bin/env python3
"""Compare public and direct-private IPv6 imports with original Apple Clang."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='apple-ipv6-headers-',dir=root/'runtime'));m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for n in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(n,None)
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));sdk='/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS26.5.sdk';clang='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';source=root/'fixtures/hello/ios-public-ipv6-header.m';script=folder/'run.sh'
lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
for mode in ['private','public']:
 command=[clang,'-target','arm64-apple-ios13.0','-isysroot',sdk,'-fmodules','-fimplicit-module-maps','-fmodules-cache-path='+guest(folder/'module-cache'),'-fsyntax-only',guest(source)]
 if mode=='private':command+=['-DDIRECT_PRIVATE_IPV6_IMPORT=1']
 lines += [shlex.join(command),'status=$?','printf "APPLE_IPV6_HEADER '+mode+' %s\\n" "$status"']
lines.append('exit 0');script.write_text('\n'.join(lines)+'\n');command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='120';log=folder/'native.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^APPLE_IPV6_HEADER (\S+) (\d+)$',text,re.M);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();installed=root/('runtime/state/prefix'+clang);extracted=root/('runtime/xcode-extract/Xcode.app/Contents/Developer'+clang.split('/Contents/Developer',1)[1]);assert sha(installed)==sha(extracted)
verified=result.returncode==0 and statuses==[('private','1'),('public','0')] and 'private header' in text.lower();report=dict(verified=verified,outer_status=result.returncode,cases=statuses,command=command,log=str(log.relative_to(root)),log_sha256=sha(log),configuration=a.configuration,stage=a.stage,original_Apple_clang_sha256=sha(installed),original_tool_bytes_equal_extracted=True,sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source]},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(text);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
