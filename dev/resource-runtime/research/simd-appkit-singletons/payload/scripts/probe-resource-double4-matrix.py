#!/usr/bin/env python3
"""Exercise original missing-symbol and source constant cases in Darling."""
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
parser.add_argument('--baseline-configuration',required=True)
parser.add_argument('--configuration',required=True)
args=parser.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
config=json.loads((root/args.configuration).read_text())
build_path=config['resource_system_build'];build=json.loads((root/build_path).read_text())
assert sha(root/build_path)==config['resource_system_build_sha256']
assert build['constant_bytes_equal_original'] and build['SDK_layout_compile_assertions_passed']
folder=Path(tempfile.mkdtemp(prefix='resource-double4-native-',dir=root/'runtime'))
source=root/'fixtures/hello/simd-double4-native.c';obj=folder/'test.o';binary=folder/'test'
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2',
                '-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11',
                '-syslibroot',str(sdk),'-lSystem','-no_fixup_chains','-no_adhoc_codesign',
                str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
cases=[]
for name,configuration in [('missing',args.baseline_configuration),('present',args.configuration)]:
    p=module['profile'](stage=args.stage,configuration=configuration)
    env=module['environment'](p)
    for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
    scope=p['direct_resource_environment']['tool_environment']
    argv=['/usr/bin/env',*[k+'='+v for k,v in scope.items()],
          '/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root)),
          '/Volumes/SystemRoot/workspace/'+build['constant_helper']]
    script=folder/(name+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join(argv)+'\nstatus=$?\nprintf "SIMD_CONSTANT_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command=p['command'][:-2]+['/bin/bash','/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
    command[3]='60';log=folder/(name+'.log')
    with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text=log.read_text();status=re.findall(r'^SIMD_CONSTANT_NATIVE_STATUS (\d+)$',text,re.M)
    if name=='missing':verified=result.returncode!=0 and 'Symbol not found: _matrix_identity_double4x4' in text
    else:verified=result.returncode==0 and status==['0'] and bool(re.search(
        r'^SIMD_DOUBLE4X4_ORIGINAL_BYTES_LAYOUT_REEXPORT_AND_USE_OK 60$',text,re.M))
    cases.append(dict(mode=name,configuration=configuration,configuration_sha256=sha(root/configuration),
                      command=command,outer_status=result.returncode,native_status=status,verified=verified,
                      log=str(log.relative_to(root)),log_sha256=sha(log)))
    print(name,text[-2000:],flush=True)
report=dict(verified=all(c['verified'] for c in cases),cases=cases,build=build_path,build_sha256=sha(root/build_path),
            program=str(binary.relative_to(root)),program_sha256=sha(binary),
            checks=60,original_resource_compilation_verified=False,
            sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source,
                root/'scripts/direct-resource-tool-runtime-profile.py']})
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if report['verified'] else 1)
