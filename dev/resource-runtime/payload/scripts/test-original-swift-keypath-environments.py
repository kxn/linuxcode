#!/usr/bin/env python3
"""Use genuine Apple Swift IR and execution to verify marker KeyPath environments."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,runpy,shlex,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
module=runpy.run_path(str(root/'scripts/xcode-tool-dispatch-runtime-profile.py'));profile=module['profile']()
folder=Path(tempfile.mkdtemp(prefix='original-swift-keypath-',dir=root/'runtime'))
for name in ['MarkerKeyPath.swift','main.swift']:shutil.copy2(root/'fixtures/SwiftKeyPathEnvironment'/name,folder/name)
g='/Volumes/SystemRoot/workspace/'+str(folder.relative_to(root))+'/'
compiler='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc'
common=['-module-name','MarkerKeyPath','-target','x86_64-apple-macosx15.0','-sdk','/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk']
commands=[('IR',[compiler,g+'MarkerKeyPath.swift','-emit-ir',*common,'-o',g+'MarkerKeyPath.ll']),
          ('COMPILE',[compiler,g+'MarkerKeyPath.swift',g+'main.swift',*common,'-o',g+'KeyPathSmoke']),
          ('RUN',[g+'KeyPathSmoke'])]
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\n'+''.join(shlex.join(argv)+'\nstatus=$?\nprintf "ORIGINAL_SWIFT_KEYPATH_'+name+'_STATUS %s\\n" "$status"\nif [ "$status" -ne 0 ]; then exit "$status"; fi\n' for name,argv in commands))
command=profile['command'][:-2]+['/bin/bash',g+'run.sh'];command[3]='180';log=folder/'run.log'
with log.open('w') as stream:result=subprocess.run(command,env=module['environment'](profile),stdout=stream,stderr=subprocess.STDOUT)
text=log.read_text();print(text[-2000:],end='')
assert result.returncode==0 and all(re.search(r'^ORIGINAL_SWIFT_KEYPATH_'+name+r'_STATUS 0$',text,re.M) for name,_ in commands)
assert '\nORIGINAL_SWIFT_MARKER_KEYPATH_RUNTIME_OK 3\n' in text
ir=(folder/'MarkerKeyPath.ll').read_text()
line=next(line for line in ir.splitlines() if line.startswith('@"generic environment ') and 'Sendable' in line and 'HasValue' in line)
match=re.search(r'constant <\{ (.*?) \}> <\{ i32 (\d+), i16 (\d+), i8 (-?\d+), \[1 x i8\] zeroinitializer, i32 (\d+)',line)
assert match,line
fields=match[1].split(', ');flags=int(match[2]);declared=flags>>12
# One flags/count/parameter/padding prefix plus one 12-byte real requirement.
assert fields==['i32','i16','i8','[1 x i8]','i32','i32','i32']
assert flags==8193 and declared==2 and int(match[5])==128
marker_line=next(line for line in ir.splitlines() if line.startswith('@"generic environment ') and 'Sendable' in line and 'HasValue' not in line)
marker_match=re.search(r'constant <\{ (.*?) \}> <\{ i32 (\d+), i16 (\d+), i8 (-?\d+), \[1 x i8\] zeroinitializer \}>',marker_line)
assert marker_match,marker_line
assert marker_match[1].split(', ')==['i32','i16','i8','[1 x i8]']
assert int(marker_match[2])==4097 and int(marker_match[3])==1
paths=[script,log,folder/'MarkerKeyPath.ll',folder/'KeyPathSmoke',folder/'MarkerKeyPath.swift',folder/'main.swift',
       root/'scripts/test-original-swift-keypath-environments.py',root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc']
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),verified=True,wrapper_exit_status=result.returncode,
 original_Apple_compiler_used=True,original_IR_declared_requirements=declared,original_IR_emitted_requirements=1,
 original_metadata_edited=False,native_generic_KeyPath_projections=3,source_runtime=profile['source_runtime'],
 marker_only_declared_requirements=1,marker_only_emitted_requirements=0,
 command=command,files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
 full_SwiftUI_runtime_verified=False,full_resource_compilation_verified=False)
output=root/'artifacts/original-swift-keypath-environments.json'
output.parent.mkdir(parents=True,exist_ok=True)
if output.exists():
 sha=hashlib.sha256(output.read_bytes()).hexdigest();archive=root/'artifacts/swift-keypath-history'/sha;archive.mkdir(parents=True,exist_ok=True);shutil.copy2(output,archive/'report.json')
output.write_text(json.dumps(record,indent=2)+'\n')
print('Original compiler overcounts (two/one and one/zero) and three genuine KeyPath projections verified')
