#!/usr/bin/env python3
"""Run the original AppKit feature query with its real named enum-index bytes."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--baseline-probe',required=True);p.add_argument('--stage',required=True);args=p.parse_args();read=lambda n:json.loads((root/n).read_text());sha=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest();folder=Path(tempfile.mkdtemp(prefix='appkit-solarium-enum-',dir=root/'runtime'));sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source='fixtures/hello/appkit-solarium-enum.c';obj=folder/'test.o';program=folder/'test'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]
for c in commands:subprocess.run(c,cwd=root,check=True)
mod=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=mod['profile'](stage=args.stage,configuration=args.configuration);env=mod['environment'](profile)
for n in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(n,None)
scope=profile['direct_resource_environment']['tool_environment'];old=read(args.baseline_probe)['scope']['tool_environment'];config=read(args.configuration);overlay=read(config['resource_overlay_stage']);provider=str(Path(overlay['frameworks'])/'AppKit.framework/Versions/C/AppKit');cases=[]
for mode in ['missing','present','wrong-value']:
 c=list(profile['command'][:-2]);selected=old if mode=='missing' else scope
 for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
  i=next(i for i,v in enumerate(c) if v.startswith(key+'='));c[i]=key+'='+selected[key]
 owner='/Volumes/SystemRoot/workspace/runtime/resource-framework-overlay-automationmode-v1/frameworks/AppKit.framework/Versions/C/AppKit' if mode=='missing' else '/Volumes/SystemRoot/workspace/'+provider
 script=folder/(mode+'.sh');guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n);script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(program.relative_to(root)),owner,'2' if mode=='wrong-value' else '1'])+'\nstatus=$?\nprintf "SOLARIUM_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n');c+=['/bin/bash',guest(script.relative_to(root))];c[3]='120';log=folder/(mode+'.log')
 with log.open('w') as out:result=subprocess.run(c,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
 text=log.read_text();status={'missing':12,'present':0,'wrong-value':15}[mode];marker='SOLARIUM_ENUM_INDEX_MISSING' if mode=='missing' else 'ORIGINAL_NSSOLARIUM_ENABLED_ENUM_AND_READONLY_OK' if mode=='present' else 'SOLARIUM_ENUM_VALUE 1'
 verified=result.returncode==status and re.findall(r'^SOLARIUM_NATIVE_STATUS (\d+)$',text,re.M)==[str(status)] and marker in text;cases.append(dict(mode=mode,verified=verified,outer_status=result.returncode,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)),command=c));print(mode,result.returncode,text[-1700:],flush=True)
 if not verified:break
report=dict(verified=len(cases)==3 and all(c['verified'] for c in cases),configuration=args.configuration,stage=args.stage,provider=provider,provider_sha256=sha(provider),cases=cases,sources={n:sha(n) for n in [source,'scripts/probe-appkit-solarium-enum.py',args.configuration,args.baseline_probe]},original_function_body_preserved=True,full_AppKit_compatibility_verified=False,full_goal_complete=False);(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json');raise SystemExit(0 if report['verified'] else 1)
