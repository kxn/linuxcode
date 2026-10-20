#!/usr/bin/env python3
"""Compile with original Swift and execute the original frame-range overlay."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--configuration',required=True);parser.add_argument('--baseline-probe',required=True);parser.add_argument('--stage',required=True);args=parser.parse_args()
read=lambda p:json.loads((root/p).read_text());sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
folder=Path(tempfile.mkdtemp(prefix='swift-quartzcore-native-',dir=root/'runtime'));source='fixtures/SwiftQuartzFrameRange/main.swift';copy=folder/'main.swift';shutil.copy2(root/source,copy)
obj=folder/'range.o';program=folder/'range';guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p)
compiler='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc';installed='runtime/state/prefix'+compiler;extracted='runtime/xcode-extract/Xcode.app/Contents/Developer'+compiler.split('/Contents/Developer',1)[1];assert sha(installed)==sha(extracted)
common=['-target','x86_64-apple-macosx15.0','-sdk','/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk']
compilation=[('OBJECT',[compiler,guest(copy.relative_to(root)),'-Onone','-emit-object','-module-name','QuartzFrameRange',*common,'-o',guest(obj.relative_to(root))]),
 ('LINK',[compiler,guest(obj.relative_to(root)),*common,'-o',guest(program.relative_to(root))])]
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));p=module['profile'](stage=args.stage,configuration=args.configuration);env=module['environment'](p)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
script=folder/'compile.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+''.join(shlex.join(argv)+'\nstatus=$?\nprintf "QUARTZCORE_'+mode+'_STATUS %s\\n" "$status"\nif [ "$status" -ne 0 ]; then exit "$status"; fi\n' for mode,argv in compilation))
command=list(p['command'][:-2])+['/bin/bash',guest(script.relative_to(root))];command[3]='180';log=folder/'compile.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();compiled=result.returncode==0 and all(re.search('^QUARTZCORE_'+mode+'_STATUS 0$',text,re.M) for mode,_ in compilation)
report=dict(verified=False,configuration=args.configuration,original_compiler_sha256=sha(installed),original_compiler_bytes_equal_extracted=True,compile_command=command,compile_outer_status=result.returncode,compile_log=str(log.relative_to(root)),compile_log_sha256=sha(log.relative_to(root)),cases=[],sources={n:sha(n) for n in [source,'scripts/probe-original-swift-quartzcore.py',args.configuration,args.baseline_probe]})
print('COMPILE',result.returncode,text[-2000:],flush=True)
if compiled:
    symbol='_$sSo16CAFrameRateRangeV10QuartzCoreE7minimum7maximum9preferredABSf_S2fSgtcfC'
    undefined=subprocess.check_output(['llvm-nm-19','--undefined-only',str(obj)],text=True)
    assert symbol in undefined,'The test did not import the original constructor'
    report['original_constructor_import_verified']=True;report['object_sha256']=sha(obj.relative_to(root));report['program_sha256']=sha(program.relative_to(root))
    c=read(args.configuration);g=read(c['graphics_stage']);provider=str(Path(g['library']).parents[4]/'libraries/libswiftQuartzCore.dylib');assert (root/provider).is_file()
    report.update(provider=provider,provider_sha256=sha(provider))
    scope=p['direct_resource_environment']['tool_environment'];oldscope=read(args.baseline_probe)['scope']['tool_environment']
    for mode in ['missing','present','wrong-value']:
        command=list(p['command'][:-2]);selected=oldscope if mode=='missing' else scope
        for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
            at=next(i for i,value in enumerate(command) if value.startswith(key+'='));command[at]=key+'='+selected[key]
        argv=[guest(program.relative_to(root)),provider,mode];script=folder/(mode+'.sh');script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(argv)+'\nstatus=$?\nprintf "QUARTZCORE_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
        command+=['/bin/bash',guest(script.relative_to(root))];command[3]='120';log=folder/(mode+'.log')
        with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
        text=log.read_text();statuses=re.findall(r'^QUARTZCORE_NATIVE_STATUS (\d+)$',text,re.M)
        if mode=='missing':verified=result.returncode!=0 and (('Symbol not found' in text and symbol in text) or 'QUARTZCORE_NATIVE_STATUS 12' in text)
        elif mode=='present':verified=result.returncode==0 and statuses==['0'] and 'ORIGINAL_SWIFT_QUARTZCORE_CONSTRUCTOR_OPTIONAL_FLOAT_GET_SET_OK 23' in text
        else:verified=result.returncode==15 and statuses==['15']
        report['cases'].append(dict(mode=mode,verified=verified,outer_status=result.returncode,native_status=statuses,command=command,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root))))
        print(mode,result.returncode,text[-1800:],flush=True)
        if not verified:break
    report['verified']=len(report['cases'])==3 and all(c['verified'] for c in report['cases'])
report.update(full_QuartzCore_API_verified=False,resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json');raise SystemExit(0 if report['verified'] else 1)
