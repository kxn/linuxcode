#!/usr/bin/env python3
"""Check an original reexport against its real terminal object and cache value."""
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
parser.add_argument('--baseline-configuration',required=True)
parser.add_argument('--stage',required=True)
parser.add_argument('--original-value',required=True)
args=parser.parse_args()
read=lambda path:json.loads((root/path).read_text())
sha=lambda path:hashlib.sha256((root/path).read_bytes()).hexdigest()
oracle=read(args.original_value)
assert oracle['symbol']=='_AVAudioSessionRoutingContextChangeNotification'
assert sha('runtime/fullsystem-libraries'+oracle['original_provider'])==oracle['source_sha256']
folder=Path(tempfile.mkdtemp(prefix='avfaudio-reexport-native-',dir=root/'runtime'))
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source='fixtures/hello/avfaudio-reexport.c'
obj=folder/'probe.o';binary=folder/'probe'
subprocess.run(['clang-19','-target','x86_64-apple-macos26','-isysroot',str(sdk),
    '-fblocks','-O2','-c',str(root/source),'-o',str(obj)],check=True,cwd=root)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','26','26',
    '-syslibroot',str(sdk),'-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True,cwd=root)
normalize=runpy.run_path(str(root/'scripts/normalize-macho-weak-bind.py'))['normalize']
binary.write_bytes(normalize(binary.read_bytes())[0])
config=read(args.configuration)
graphics=Path(read(config['graphics_stage'])['library']).parents[4]
overlay=Path(read(config['resource_overlay_stage'])['frameworks'])
actual_avf=overlay/'AVFAudio.framework/Versions/A/AVFAudio'
actual_session=graphics/'frameworks/AudioSession.framework/Versions/A/AudioSession'
assert (root/actual_avf).is_file() and (root/actual_session).is_file()
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
base=module['parent']['profile'](stage=args.stage)
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path)
cases=[]
for mode,configuration in [('missing',args.baseline_configuration),('present',args.configuration)]:
    p=module['select'](base,configuration=configuration)
    env=module['environment'](p)
    for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
    command=list(p['command'][:-2])
    for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
        index=next(i for i,value in enumerate(command) if value.startswith(key+'='))
        command[index]=key+'='+p['direct_resource_environment']['tool_environment'][key]
    avf='/System/Library/Frameworks/AVFAudio.framework/Versions/A/AVFAudio' if mode=='missing' else guest(actual_avf)
    script=folder/(mode+'.sh')
    argv=[guest(binary.relative_to(root)),mode,avf,guest(actual_session),oracle['ASCII_value']]
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(argv)+
        '\nstatus=$?\nprintf "AVF_REEXPORT_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command+=['/bin/bash',guest(script.relative_to(root))];command[3]='120'
    log=folder/(mode+'.log')
    with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text=log.read_text();statuses=re.findall(r'^AVF_REEXPORT_NATIVE_STATUS (\d+)$',text,re.M)
    marker='AVF_OLD_PROVIDER_REEXPORT_ABSENT_OK' if mode=='missing' else 'AVF_ORIGINAL_REEXPORT_SLOT_OBJECT_IDENTITY_AND_CFSTRING_VALUE_OK'
    verified=result.returncode==0 and statuses==['0'] and marker in text
    if mode=='present':
        owners=re.findall(r'^AVF_REEXPORT_TERMINAL_OWNER (.+)$',text,re.M)
        verified=verified and owners==[guest(actual_session)]
    cases.append(dict(mode=mode,verified=verified,configuration=configuration,configuration_sha256=sha(configuration),
        outer_status=result.returncode,native_status=statuses,command=command,
        log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root))))
    print(mode,result.returncode,text[-2200:],flush=True)
    if not verified:break
record=dict(verified=len(cases)==2 and all(c['verified'] for c in cases),cases=cases,
    binary=str(binary.relative_to(root)),binary_sha256=sha(binary.relative_to(root)),
    AVFAudio_image=str(actual_avf),AVFAudio_image_sha256=sha(actual_avf),
    terminal_image=str(actual_session),terminal_image_sha256=sha(actual_session),
    original_value=args.original_value,original_value_sha256=sha(args.original_value),
    sources={path:sha(path) for path in [str(Path(__file__).relative_to(root)),source]},
    full_framework_API_compatibility_verified=False,resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
