#!/usr/bin/env python3
"""Check the original NE UUID through libSystem and actual read-only memory."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--configuration',required=True);parser.add_argument('--baseline-probe',required=True);parser.add_argument('--stage',required=True);args=parser.parse_args()
read=lambda p:json.loads((root/p).read_text());sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
folder=Path(tempfile.mkdtemp(prefix='ne-agent-uuid-native-',dir=root/'runtime'))
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source='fixtures/hello/ne-agent-uuid.c';obj=folder/'test.o';program=folder/'test'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/source),'-o',str(obj)],
 ['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',
  '-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]
for command in commands:subprocess.run(command,cwd=root,check=True)
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));p=module['profile'](stage=args.stage,configuration=args.configuration);env=module['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
scope=p['direct_resource_environment']['tool_environment'];oldscope=read(args.baseline_probe)['scope']['tool_environment']
c=read(args.configuration);build=read(c['resource_system_build']);provider=build['NE_agent_helper'];contract=read('artifacts/ne-privacy-dns-original-constant-contract-v1.json')
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path);cases=[]
for mode in ['missing','present','wrong-value']:
    command=list(p['command'][:-2]);selected=oldscope if mode=='missing' else scope
    for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
        at=next(i for i,arg in enumerate(command) if arg.startswith(key+'='));command[at]=key+'='+selected[key]
    value='00000000-0000-0000-0000-000000000000' if mode=='wrong-value' else contract['UUID']
    script=folder/(mode+'.sh');script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
      shlex.join([guest(program.relative_to(root)),provider,value])+'\nstatus=$?\nprintf "NE_AGENT_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command+=['/bin/bash',guest(script.relative_to(root))];command[3]='120';log=folder/(mode+'.log')
    with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text=log.read_text();statuses=re.findall(r'^NE_AGENT_NATIVE_STATUS (\d+)$',text,re.M);expected={'missing':12,'present':0,'wrong-value':15}[mode]
    marker='NE_AGENT_UUID_MISSING' if mode=='missing' else ('NE_AGENT_ORIGINAL_UUID_BYTES_IDENTITY_PROVIDER_AND_READONLY_OK' if mode=='present' else '')
    verified=result.returncode==expected and statuses==[str(expected)] and marker in text
    cases.append(dict(mode=mode,verified=verified,outer_status=result.returncode,native_status=statuses,command=command,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root))))
    print(mode,result.returncode,text[-1500:],flush=True)
    if not verified:break
report=dict(verified=len(cases)==3 and all(x['verified'] for x in cases),configuration=args.configuration,build=c['resource_system_build'],build_sha256=sha(c['resource_system_build']),provider=provider,provider_sha256=sha(provider),cases=cases,commands=commands,
 sources={n:sha(n) for n in [source,'scripts/probe-ne-agent-uuid.py',args.configuration,args.baseline_probe]},resource_compilation_verified=False,network_service_API_verified=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json');raise SystemExit(0 if report['verified'] else 1)
