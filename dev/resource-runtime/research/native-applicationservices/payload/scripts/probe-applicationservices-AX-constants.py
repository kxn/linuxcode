#!/usr/bin/env python3
"""Read genuine AX globals through ApplicationServices and CoreFoundation."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage',required=True)
parser.add_argument('--configuration',required=True)
parser.add_argument('--contract',required=True)
args=parser.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
contract=json.loads((root/args.contract).read_text());assert contract['verified']
assert sha(root/('runtime/fullsystem-libraries'+contract['provider']))==contract['provider_sha256']
folder=Path(tempfile.mkdtemp(prefix='applicationservices-AX-native-',dir=root/'runtime'))
source=root/'fixtures/hello/applicationservices-AX-constants.c';obj=folder/'test.o';binary=folder/'test'
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11',
                '-syslibroot',str(sdk),'-lSystem','-framework','CoreFoundation',
                '-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p=module['profile'](stage=args.stage,configuration=args.configuration);env=module['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
scope=p['direct_resource_environment']['tool_environment']
argv=['/usr/bin/env',*[k+'='+v for k,v in scope.items()],'/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))]
for row in contract['constants']:argv.extend([row['symbol'],row['value']])
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
    shlex.join(argv)+'\nstatus=$?\nprintf "AX_CONSTANTS_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
command=p['command'][:-2]+['/bin/bash','/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
command[3]='60';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^AX_CONSTANTS_NATIVE_STATUS (\d+)$',text,re.M)
values=re.findall(r'^AX_VALUE (\S+) (.+)$',text,re.M);providers=re.findall(r'^AX_PROVIDER (.+)$',text,re.M)
config=json.loads((root/args.configuration).read_text())
overlay=json.loads((root/config['resource_overlay_stage']).read_text())
expected_provider='/Volumes/SystemRoot/workspace/'+overlay['frameworks']+'/ApplicationServices.framework/Versions/A/Frameworks/HIServices.framework/Versions/A/HIServices'
expected=[(row['symbol'],row['value']) for row in contract['constants']]
verified=result.returncode==0 and statuses==['0'] and values==expected and providers==[expected_provider]*len(expected)
report=dict(verified=verified,configuration=args.configuration,configuration_sha256=sha(root/args.configuration),
            contract=args.contract,contract_sha256=sha(root/args.contract),outer_status=result.returncode,
            native_status=statuses,values=values,providers=providers,expected_provider=expected_provider,
            command=command,program=str(binary.relative_to(root)),program_sha256=sha(binary),
            log=str(log.relative_to(root)),log_sha256=sha(log),full_resource_compilation_verified=False,
            sources={str(q.relative_to(root)):sha(q) for q in [Path(__file__),source,root/'scripts/direct-resource-tool-runtime-profile.py']})
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(text[-2600:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
