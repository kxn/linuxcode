#!/usr/bin/env python3
"""Load the selected original JavaScriptCore and run real public C API scripts."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shlex, subprocess, tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--configuration',required=True)
parser.add_argument('--stage',required=True)
args=parser.parse_args()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
folder=Path(tempfile.mkdtemp(prefix='original-jsc-native-',dir=root/'runtime'))
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source='fixtures/hello/original-javascriptcore-evaluate.c'; obj=folder/'test.o';program=folder/'test'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/source),'-o',str(obj)],
    ['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),
     '-lSystem','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]
for command in commands:subprocess.run(command,cwd=root,check=True)
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p=module['profile'](stage=args.stage,configuration=args.configuration);env=module['environment'](p)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
c=json.loads((root/args.configuration).read_text());overlay=json.loads((root/c['resource_overlay_stage']).read_text())
provider=str(Path(overlay['frameworks'])/'JavaScriptCore.framework/Versions/A/JavaScriptCore')
assert (root/provider).is_file()
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path)
script=folder/'evaluate.sh'; script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
    shlex.join([guest(program.relative_to(root)),'/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/JavaScriptCore',provider])+
    '\nstatus=$?\nprintf "ORIGINAL_JSC_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
command=list(p['command'][:-2])
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
    at=next(i for i,arg in enumerate(command) if arg.startswith(key+'='))
    command[at]=key+'='+p['direct_resource_environment']['tool_environment'][key]
command+=['/bin/bash',guest(script.relative_to(root))];command[3]='180'
log=folder/'evaluate.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^ORIGINAL_JSC_NATIVE_STATUS (\d+)$',text,re.M)
verified=result.returncode==0 and statuses==['0'] and 'ORIGINAL_JSC_EVALUATION_UNICODE_ARRAYS_EXCEPTIONS_AND_CONTEXT_ISOLATION_OK' in text
report=dict(verified=verified,configuration=args.configuration,provider=provider,provider_sha256=sha(provider),
    outer_status=result.returncode,native_status=statuses,command=command,commands=commands,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)),
    sources={n:sha(n) for n in [source,'scripts/probe-original-javascriptcore.py',args.configuration]},
    context_creation_observed='JSC_REAL_CONTEXT_CREATED' in text,resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(text[-3000:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
