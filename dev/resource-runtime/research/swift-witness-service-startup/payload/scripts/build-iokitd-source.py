#!/usr/bin/env python3
"""Build the complete pinned iokitd source and both actual MIG servers privately."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--output-dir',default='runtime/iokitd-source');parser.add_argument('--report',default='artifacts/iokitd-source-build.json');args=parser.parse_args()
repo=root/'vendor/darling/src/external/iokitd';darling=root/'vendor/darling'
commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip();assert commit=='5549ac4cd2db923c256f016a1381b3bfb716730a'
build=(root/args.output_dir).resolve();assert build.is_relative_to(root/'runtime');build.mkdir(exist_ok=True)
generated=build/'generated';generated.mkdir(exist_ok=True)
sdk=darling/'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
apple=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
xnu=darling/'src/external/xnu';resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip())
includes=[generated,repo/'src',darling/'src/external/libcxx/include',darling/'src/external/libcxxabi/include',
          darling/'src/include',darling/'src/duct/include',sdk/'usr/include',resource/'include',darling/'framework-include',
          darling/'framework-private-include',xnu/'osfmk',xnu/'iokit',darling/'src/external/IOKitUser',Path('/usr/include')]
definitions=['-DDARLING','-DIOKIT=1','-DIOKIT_ALL_IPC=1','-DIOKIT_SERVER_VERSION=20150101','-D__DARWIN_UNIX03','-D_DARWIN_C_SOURCE','-DTARGET_OS_WASI=0']
common=['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc','-nostdinc++',*['-I'+str(p) for p in includes],
        '-idirafter',str(apple/'usr/include'),'-F',str(sdk/'System/Library/Frameworks'),*definitions,'-fblocks','-O1','-g','-Wno-deprecated-declarations','-Wno-nullability-completeness']
mig=root/'runtime/darlingserver-source-build/build-mig'
for name in ['iokitmig','powermanagement']:
    subprocess.run([str(mig),'-arch','x86_64','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc',*['-I'+str(p) for p in includes],*definitions,
                    '-user',str(generated/(name+'User.c')),'-header',str(generated/(name+'.h')),
                    '-server',str(generated/(name+'Server.c')),'-sheader',str(generated/(name+'Server.h')),str(repo/(name+'.defs'))],check=True)
section=(repo/'CMakeLists.txt').read_text().split('set(iokitd_sources',1)[1].split('\n)',1)[0]
paths=[]
for item in section.split():
    item=item.replace('${CMAKE_CURRENT_BINARY_DIR}',str(generated)).replace('${CMAKE_CURRENT_SOURCE_DIR}',str(repo))
    paths.append(Path(item) if item.startswith('/') else repo/item)
assert len(paths)>=21
objects=[];manifest=[]
for i,path in enumerate(paths):
    path=path.resolve();obj=build/(str(i)+'-'+path.stem+'.o');command=[*common]
    if path.suffix in ['.mm','.cpp']:command+=['-std=c++17','-stdlib=libc++']
    command+=['-c',str(path),'-o',str(obj)];print('Compile',path.relative_to(root),flush=True);subprocess.run(command,check=True)
    objects.append(obj);manifest.append(dict(source=str(path.relative_to(root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),command=command))
guest=root/'runtime/rootfs/usr/libexec/darling';binary=build/'iokitd'
command=['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(guest),'-o',str(binary),*map(str,objects),
         '-L'+str(guest/'usr/lib'),'-L'+str(guest/'usr/lib/native'),'-F'+str(guest/'System/Library/Frameworks'),
         '-lSystem','-lc++','-lc++abi','-lbsm.0','-lobjc','-lX11','-lXRandR','-lXext','-lEGL',
         str(guest/'System/Library/Frameworks/OpenGL.framework/Versions/A/Libraries/libGL.dylib'),'-framework','IOSurface','-framework','CoreFoundation','-framework','Foundation']
subprocess.run(command,check=True)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=dict(source_commit=commit,complete_source_files=len(paths),sources=manifest,binary=str(binary.relative_to(root)),binary_sha256=digest(binary),link_command=command,
            headers={str(p.relative_to(root)):digest(p) for p in list((repo/'src').glob('*.h'))+[repo/'CMakeLists.txt',repo/'iokitmig.defs',repo/'powermanagement.defs']},
            full_iokitd_source_build=True,installed=False,runtime_execution_verified=False,full_xcode_build_ready=False)
(root/args.report).write_text(json.dumps(report,indent=2)+'\n');print('Built complete source iokitd',len(paths))
