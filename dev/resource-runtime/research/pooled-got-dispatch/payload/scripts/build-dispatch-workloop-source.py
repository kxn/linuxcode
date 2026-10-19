#!/usr/bin/env python3
"""Build the complete configured Darling libdispatch in a private coherent root."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,fcntl,hashlib,json,re,runpy,shutil,subprocess
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--output-dir',default='runtime/dispatch-workloop-source');parser.add_argument('--report',default='artifacts/dispatch-workloop-source-build.json');args=parser.parse_args()
repo=root/'vendor/darling/src/external/libdispatch';build=(root/args.output_dir).resolve();assert build.is_relative_to(root/'runtime');build.mkdir(exist_ok=True)
generated=build/'generated';(generated/'src/firehose').mkdir(parents=True,exist_ok=True)
sdk=root/'vendor/darling/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip())
apple=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parent=runpy.run_path(str(root/'scripts/workqueue-stack-runtime-profile.py'))['profile']()
base=root/'runtime/workqueue-stack-kernel-source/darling-root'
baseline=base/'usr/lib/system/libdispatch.dylib'
definitions=['-Dtypeof=__typeof__','-DPRIVATE','-D__PTHREAD_EXPOSE_INTERNALS__','-D__BLOCKS__','-DDISPATCH_USE_DTRACE=0','-DNeXT_RUNTIME=1','-DNS_RETURNS_INNER_POINTER=',
    '-DDISPATCH_USE_INTERNAL_WORKQUEUE=0','-DDISPATCH_USE_KEVENT_WORKQUEUE=0','-DDISPATCH_USE_KEVENT_WORKLOOP=0','-DHAVE_PTHREAD_WORKQUEUE_QOS=0','-DVOUCHER_USE_MACH_VOUCHER=0','-DDISPATCH_USE_WORKQUEUE_NARROWING=0','-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1','-DOS_EVENTLINK_USE_MACH_EVENTLINK=0','-DPLATFORM_MacOSX']
includes=[repo,repo/'private',repo/'src',generated/'src/firehose',generated/'src',root/'vendor/darling/src/include',sdk/'usr/include',resource/'include']
common=['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc',*['-I'+str(p) for p in includes],'-idirafter',str(apple/'usr/include'),'-F',str(sdk/'System/Library/Frameworks'),'-fblocks','-fPIC','-D__DARWIN_UNIX03','-DDARLING',*definitions,'-O0','-g','-w','-Wno-error=int-conversion','-Wno-error=incompatible-pointer-types','-Wno-error=implicit-function-declaration']
common+=['-idirafter',str(root/'vendor/darling/src/external/xnu/osfmk')]
mig=root/'runtime/darlingserver-source-build/build-mig'
for relative in ['src/protocol','src/firehose/firehose','src/firehose/firehose_reply']:
    dest=generated/relative
    subprocess.run([str(mig),'-arch','x86_64','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-I'+str(sdk/'usr/include'),'-I'+str(repo/'src'),'-DPRIVATE','-user',str(dest)+'User.c','-header',str(dest)+'.h','-server',str(dest)+'Server.c','-sheader',str(dest)+'Server.h',str(repo/(relative+'.defs'))],check=True)
text=re.sub(r'#[^\n]*','',(repo/'CMakeLists.txt').read_text())
section=re.search(r'set\(dispatch_SRCS\s+(.*?)\n\)',text,re.S).group(1)
sources=[Path(p.replace('${CMAKE_CURRENT_BINARY_DIR}',str(generated))) if p.startswith('${') else repo/p for p in section.split()]
assert len(sources)==32,len(sources)
objects=build/'objects';objects.mkdir(exist_ok=True);manifest=[]
for index,source in enumerate(sources):
    obj=objects/(str(index)+'-'+source.stem+'.o')
    command=[*common]
    if source.suffix=='.cpp':
        command=[command[0],'-I'+str(root/'vendor/darling/src/external/libcxx/include'),*command[1:],'-std=c++11','-fno-exceptions','-D_Bool=bool','-nostdinc++','-Wno-error=elaborated-enum-base']
    if source.suffix=='.m':command+=['-fobjc-runtime=macosx-10.11']
    command+=['-c',str(source),'-o',str(obj)]
    manifest.append(dict(source=str(source.relative_to(root)),sha256=digest(source),object=str(obj.relative_to(root)),command=command))
def compile_one(pair):
    i,item=pair;result=subprocess.run(item['command'],capture_output=True,text=True);(objects/(str(i)+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(item['source']+'\n'+result.stderr)
    print('Compiled',item['source'],flush=True)
with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(compile_one,enumerate(manifest)))
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
ld='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld';gsdk='/Volumes/SystemRoot/usr/libexec/darling'
output=build/'libdispatch.dylib';pending=output.with_name(output.name+'.pending')
siblings=['system_c','system_kernel','system_malloc','system_blocks','system_pthread','dyld','system_duct','unwind','system_platform','compiler_rt']
link=[str(root/'bin/darling'),'shell',ld,'-dylib','-arch','x86_64','-platform_version','macos','11','11','-install_name','/usr/lib/system/libdispatch.dylib','-compatibility_version','1.0.0','-syslibroot',gsdk,'-L',gsdk+'/usr/lib/system',*['-l'+n for n in siblings],'-upward_library',gsdk+'/usr/lib/libobjc.A.dylib','-order_file',guest(repo/'xcodeconfig/libdispatch.order'),'-alias_list',guest(repo/'xcodeconfig/libdispatch.aliases'),*[guest(root/item['object']) for item in manifest],'-o',guest(pending)]
subprocess.run(link,check=True,timeout=120)
def exports(p):return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(p)],text=True),re.M))
old,new=exports(baseline),exports(pending);assert old<=new,sorted(old-new)
variant=build/'darling-root'
with (root/'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    if variant.exists():
        assert digest(pending)==digest(output)==digest(variant/'usr/lib/system/libdispatch.dylib'),'Use a fresh --output-dir and --report for changed code; the selected runtime has been preserved'
        pending.unlink()
    else:
        pending.replace(output)
        subprocess.run(['cp','-a','--reflink=auto',str(base),str(variant)],check=True)
        shutil.copy2(output,variant/'usr/lib/system/libdispatch.dylib')
    selected={}
    for key,item in parent['source_runtime'].items():
        filename=Path(item['path']).name;shutil.copy2(root/item['path'],build/filename)
        selected[key]=dict(path=str((build/filename).relative_to(root)),sha256=digest(build/filename));assert selected[key]['sha256']==item['sha256']
headers={str(p.relative_to(root)):digest(p) for p in repo.rglob('*.h')}
headers.update({str(p.relative_to(root)):digest(p) for p in [repo/'CMakeLists.txt',repo/'xcodeconfig/libdispatch.order',repo/'xcodeconfig/libdispatch.aliases',*[repo/(s+'.defs') for s in ['src/protocol','src/firehose/firehose','src/firehose/firehose_reply']]]})
record=dict(full_libdispatch_source_build=True,complete_source_files=len(sources),source_revision=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),sources=manifest,source_headers=headers,library=str(output.relative_to(root)),library_sha256=digest(output),baseline=str(baseline.relative_to(root)),baseline_sha256=digest(baseline),original_exports_preserved=len(old),source_exports=len(new),previous_source_runtime=parent['source_runtime'],source_runtime=selected,variant_root=str(variant.relative_to(root)),kernel_workloop_backend_enabled=False,link_command=link,full_xcode_build_ready=False)
(root/args.report).write_text(json.dumps(record,indent=2)+'\n')
print('Built complete source libdispatch and coherent private runtime',flush=True)
