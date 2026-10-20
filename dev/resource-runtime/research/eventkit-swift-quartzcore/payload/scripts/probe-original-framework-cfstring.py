#!/usr/bin/env python3
"""Check an original CFString global through the real CoreFoundation API."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--configuration',required=True)
parser.add_argument('--baseline-probe',required=True)
parser.add_argument('--contract',required=True)
parser.add_argument('--stage',required=True)
parser.add_argument('--binding-mode',choices=['now','lazy'],default='now')
args=parser.parse_args()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
read=lambda p:json.loads((root/p).read_text())
contract=read(args.contract);assert contract['verified']
assert sha('runtime/fullsystem-libraries'+contract['provider'])==contract['provider_sha256']
folder=Path(tempfile.mkdtemp(prefix='original-cfstring-native-',dir=root/'runtime'))
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source='fixtures/hello/framework-cfstring.c';obj=folder/'test.o';program=folder/'test'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/source),'-o',str(obj)],
    ['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),
     '-lSystem','-framework','CoreFoundation','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]
for command in commands:subprocess.run(command,cwd=root,check=True)
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p=module['profile'](stage=args.stage,configuration=args.configuration);env=module['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
scope=p['direct_resource_environment']['tool_environment'];oldscope=read(args.baseline_probe)['scope']['tool_environment']
c=read(args.configuration);overlay=read(c['resource_overlay_stage'])
outer,suffix=contract['provider'].split('.framework/',1)
provider=str(Path(overlay['frameworks'])/(Path(outer).name+'.framework')/suffix)
assert (root/provider).is_file()
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path)
cases=[]
for mode in ['missing','present','wrong-value']:
    command=list(p['command'][:-2]);selected=oldscope if mode=='missing' else scope
    for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
        at=next(i for i,arg in enumerate(command) if arg.startswith(key+'='));command[at]=key+'='+selected[key]
    value=contract['value'] if mode!='wrong-value' else contract['value']+'-wrong'
    argv=[guest(program.relative_to(root)),contract['provider'],contract['symbol'],value,provider,args.binding_mode]
    script=folder/(mode+'.sh');script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join(argv)+'\nstatus=$?\nprintf "CFSTRING_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command+=['/bin/bash',guest(script.relative_to(root))];command[3]='120'
    log=folder/(mode+'.log')
    with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text=log.read_text();statuses=re.findall(r'^CFSTRING_NATIVE_STATUS (\d+)$',text,re.M)
    expected={'missing':12,'present':0,'wrong-value':15}[mode]
    verified=result.returncode==expected and statuses==[str(expected)]
    if mode=='missing':verified &= 'CFSTRING_MISSING_SYMBOL' in text
    if mode=='present':verified &= ('ORIGINAL_CFSTRING_TYPE_UTF8_VALUE_PROVIDER_AND_GLOBAL_IDENTITY_OK' in text and
        'CFSTRING_PROVIDER '+guest(provider) in text)
    cases.append(dict(mode=mode,verified=bool(verified),outer_status=result.returncode,native_status=statuses,
        command=command,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root))))
    print(mode,result.returncode,text[-1400:],flush=True)
    if not verified:break
report=dict(verified=len(cases)==3 and all(c['verified'] for c in cases),configuration=args.configuration,binding_mode=args.binding_mode,
    contract=args.contract,contract_sha256=sha(args.contract),expected_provider=provider,expected_provider_sha256=sha(provider),
    program=str(program.relative_to(root)),program_sha256=sha(program.relative_to(root)),cases=cases,commands=commands,
    sources={n:sha(n) for n in [source,'scripts/probe-original-framework-cfstring.py',args.configuration,args.baseline_probe]},
    full_framework_API_compatibility_verified=False,resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if report['verified'] else 1)
