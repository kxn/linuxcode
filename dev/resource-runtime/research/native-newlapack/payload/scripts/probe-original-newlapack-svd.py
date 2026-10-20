#!/usr/bin/env python3
"""Verify the SDK NEWLAPACK ABI, real SVD residuals, and prior CPU APIs."""
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
parser.add_argument('--configuration',required=True)
parser.add_argument('--baseline-probe',required=True)
parser.add_argument('--stage',required=True)
args=parser.parse_args()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
read=lambda p:json.loads((root/p).read_text())
folder=Path(tempfile.mkdtemp(prefix='newlapack-svd-native-',dir=root/'runtime'))
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source='fixtures/hello/newlapack-svd.c'
obj=folder/'svd.o';program=folder/'svd-test'
commands=[['clang-19','-target','x86_64-apple-macos26','-isysroot',str(sdk),'-std=c11','-O2',
           '-c',str(root/source),'-o',str(obj)],
          ['ld64.lld-19','-arch','x86_64','-platform_version','macos','26','26',
           '-no_fixup_chains','-no_adhoc_codesign','-syslibroot',str(sdk),
           '-framework','Accelerate','-lSystem',str(obj),'-o',str(program)]]
for command in commands:subprocess.run(command,cwd=root,check=True)
symbols=subprocess.check_output(['llvm-nm-19','--undefined-only',str(obj)],text=True)
assert '_dgesvd$NEWLAPACK' in symbols and '$ILP64' not in symbols
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p=module['profile'](stage=args.stage,configuration=args.configuration)
env=module['environment'](p)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
scope=p['direct_resource_environment']['tool_environment']
baseline=read(args.baseline_probe)
oldscope=baseline['scope']['tool_environment']
config=read(args.configuration);overlay=read(config['resource_overlay_stage'])
lapack=next(x for x in overlay['added_original_frameworks'] if x['target']=='lapack-patch-got-v2')
outer,suffix=lapack['image'].split('/frameworks/',1)
image=str(Path(overlay['frameworks'])/suffix)
assert sha(image)==lapack['image_sha256']
assert str(Path(image).parent) in overlay['extra_library_paths']
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path)
framework=str(Path(overlay['frameworks'])/'Accelerate.framework/Versions/A/Accelerate')
veclib=next(x for x in overlay['added_original_frameworks'] if x['target']=='veclib-header-facade-v1')
vecimage=str(Path(overlay['frameworks'])/veclib['image'].split('/frameworks/',1)[1])
old_cpu='fixtures/hello/native-accelerate-cpu.c'
original=(root/old_cpu).read_text();adapted=original
replacements={
    'path && strstr(path,"/runtime/native-framework-stage/Accelerate.framework/")':
        'path && !strcmp(path,"'+guest(framework)+'")',
    'path && strstr(path,"/runtime/native-framework-stage/vecLib.framework/")':
        'path && !strcmp(path,"'+guest(vecimage)+'")'}
pins=read('config/coregraphics-image-pins.json')
vimage_target='vimage-closure-resource-v1'
vimage_pin=pins[vimage_target]
outer,suffix=vimage_pin['path'].split('.framework/',1)
vimage=str(Path(overlay['frameworks'])/(Path(outer).name+'.framework')/suffix)
vimage_proof=read('runtime/rebuilt-'+vimage_target+'/reconstruction.json')
old_vimage=read('runtime/rebuilt-vimage/reconstruction.json')
assert vimage_proof['original_image_sha256']==old_vimage['original_image_sha256']
assert sha(vimage)==vimage_proof['staged_image_sha256']
for before,after in replacements.items():
    assert adapted.count(before)==1
    adapted=adapted.replace(before,after)
before='"/runtime/native-framework-stage/vImage.framework/"'
assert adapted.count(before)==2
adapted=adapted.replace(before,'"/'+vimage+'"')
assert original.count('assert(')==adapted.count('assert(')
cpu_source=folder/'cpu-image-paths-relocated.c';cpu_source.write_text(adapted)
cpu_obj=folder/'cpu.o';cpu_program=folder/'cpu-test'
cpu_commands=[['clang-19','-target','x86_64-apple-macos26','-isysroot',str(sdk),'-std=c11','-O2',
               '-c',str(cpu_source),'-o',str(cpu_obj)],
              ['ld64.lld-19','-arch','x86_64','-platform_version','macos','26','26',
               '-no_fixup_chains','-no_adhoc_codesign','-syslibroot',str(sdk),
               '-framework','Foundation','-lSystem',str(cpu_obj),'-o',str(cpu_program)]]
for command in cpu_commands:subprocess.run(command,cwd=root,check=True)
commands+=cpu_commands
cpu=str(cpu_program.relative_to(root))
cases=[]
for mode in ['missing','svd','cpu']:
    selected=oldscope if mode=='missing' else scope
    command=list(p['command'][:-2])
    for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
        at=next(i for i,value in enumerate(command) if value.startswith(key+'='))
        command[at]=key+'='+selected[key]
    binary=cpu if mode=='cpu' else str(program.relative_to(root))
    script=folder/(mode+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join([guest(binary),guest(framework) if mode=='cpu' else image])+
        '\nstatus=$?\nprintf "NEWLAPACK_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command+=['/bin/bash',guest(script.relative_to(root))];command[3]='180'
    log=folder/(mode+'.log')
    with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text=log.read_text();statuses=re.findall(r'^NEWLAPACK_NATIVE_STATUS (\d+)$',text,re.M)
    if mode=='missing':
        verified=result.returncode!=0 and 'Symbol not found' in text and '_dgesvd$NEWLAPACK' in text
    elif mode=='svd':
        verified=result.returncode==0 and statuses==['0'] and 'NEWLAPACK_LP64_SVD_WORKSPACE_GUARDS_SINGULAR_VALUES_ORTHOGONALITY_AND_RESIDUALS_OK' in text
    else:
        verified=result.returncode==0 and statuses==['0'] and all(marker in text for marker in [
            'ORIGINAL_VDSP_RESOLVER_STRIDES_FLOAT_CASES_DOUBLE_OK 306',
            'ORIGINAL_BNNS_GRAPH_COMPILE_OPTIONS_DEFAULTS_SET_GET_INDEPENDENCE_DESTROY_OK',
            'ORIGINAL_VIMAGE_PADDED_ROWS_BYTE_FLOAT_BYTE_NUMERIC_ROUNDTRIP_OK'])
    cases.append(dict(mode=mode,verified=bool(verified),outer_status=result.returncode,native_status=statuses,
        program=binary,program_sha256=sha(binary),log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)),command=command))
    print(mode,result.returncode,text[-2000:],flush=True)
    if not verified:break
headers=sdk/'System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/Headers'
inputs=[source,'scripts/probe-original-newlapack-svd.py',old_cpu,'runtime/native-accelerate-cpu/resolvers.h',args.configuration,args.baseline_probe,
        config['resource_overlay_stage'],str((headers/'lapack.h').relative_to(root)),
        str((headers/'lapack_types.h').relative_to(root)),str((headers/'lapack_version.h').relative_to(root))]
record=dict(verified=len(cases)==3 and all(c['verified'] for c in cases),configuration=args.configuration,
    baseline_probe=args.baseline_probe,scope=p['direct_resource_environment'],cases=cases,
    expected_provider=image,expected_provider_sha256=sha(image),LP64_SDK_integer_bytes=4,
    compiled_symbol='_dgesvd$NEWLAPACK',ILP64_symbol_not_used=True,commands=commands,
    relocated_cpu_source=str(cpu_source.relative_to(root)),relocated_cpu_source_sha256=sha(cpu_source.relative_to(root)),
    cpu_only_image_paths_changed=True,cpu_image_predicates_relocated=2,cpu_vImage_owner_paths_relocated=2,
    cpu_vImage_original_image_unchanged=True,cpu_vImage_provider=vimage,cpu_vImage_provider_sha256=sha(vimage),
    cpu_assertions_unchanged=True,
    sources={n:sha(n) for n in inputs},full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
