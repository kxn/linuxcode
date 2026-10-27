#!/usr/bin/env python3
"""Build the complete launchctl translation unit and its native conversion test."""
from pathlib import Path
import hashlib,json,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;d=r/'vendor/darling';s=d/'src/launchd'
w=Path(tempfile.mkdtemp(prefix='launchctl-source-',dir=r/'runtime'))
sdk=d/'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
apple=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
common=['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-idirafter',str(apple/'usr/include'),'-DDARLING','-DPRIVATE','-DPLATFORM_MacOSX','-D__DARWIN_UNIX03','-fblocks','-fPIC','-O2','-Wno-everything','-I',str(s/'src'),'-I',str(s/'liblaunch'),'-include',str(sdk/'usr/include/sys/fileport.h')]
commands=[];sources=[s/'support/launchctl.c',r/'fixtures/hello/launchctl-long-strings.c']
guest=r/'runtime/rootfs/usr/libexec/darling'
link=['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(guest),'-L',str(guest/'usr/lib/system'),'-framework','CoreFoundation','-lxpc','-ledit','-lSystem']
def run(cmd):
 commands.append(cmd)
 with (w/'build.log').open('a') as out:subprocess.run(cmd,cwd=r,check=True,stdout=out,stderr=subprocess.STDOUT)
for i,path in enumerate(sources):run([*common,'-MMD','-MF',str(w/(str(i)+'.d')),'-c',str(path),'-o',str(w/(str(i)+'.o'))])
run([*link,str(w/'0.o'),'-o',str(w/'launchctl')])
run([*link,str(w/'1.o'),'-o',str(w/'native-test')])
inputs={Path(__file__).resolve(),*sources,s/'support/launchctl-cfstring.h'}
for dep in w.glob('*.d'):
 for item in dep.read_text().replace('\\\n',' ').split(':',1)[1].split():
  path=Path(item)
  if path.is_file() and path.is_relative_to(r):inputs.add(path)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(full_launchctl_translation_unit=True,source_files=1,commands=commands,files={str(p.relative_to(r)):sha(p) for p in sorted(inputs)},link_inputs={str(p.relative_to(r)):sha(p) for p in [guest/'usr/lib/libSystem.dylib',guest/'usr/lib/libedit.dylib',guest/'usr/lib/system/libxpc.dylib',guest/'System/Library/Frameworks/CoreFoundation.framework/CoreFoundation']},binary=str((w/'launchctl').relative_to(r)),binary_sha256=sha(w/'launchctl'),native_test=str((w/'native-test').relative_to(r)),native_test_sha256=sha(w/'native-test'),log=str((w/'build.log').relative_to(r)),installed=False)
(w/'build.json').write_text(json.dumps(record,indent=2)+'\n');print(w/'build.json')
