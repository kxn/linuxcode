#!/usr/bin/env python3
"""Build the complete x86_64 libdyld source against the pinned Darling loader ABI."""
from pathlib import Path
import argparse,fcntl,hashlib,json,re,shutil,subprocess
root=Path(__file__).resolve().parent.parent
repo=root/'vendor/darling/src/external/dyld';darling=root/'vendor/darling'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',default='runtime/libdyld-source')
parser.add_argument('--variant-base',default='runtime/sandbox-source/darling-root')
parser.add_argument('--report',default='artifacts/libdyld-source.json')
parser.add_argument('--minimum-os',default='11',help='Deployment floor for this private source-built system library; keep aligned with the selected guest identity')
args=parser.parse_args()
if not re.fullmatch(r'\d+(?:\.\d+){0,2}',args.minimum_os):parser.error('Invalid minimum OS version')
build=root/args.output_dir;build.mkdir(parents=True,exist_ok=True)
guest=root/'runtime/rootfs/usr/libexec/darling'
sdk=darling/'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
apple=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
config_path=root/'config/libdyld-source-build.json'
config=json.loads(config_path.read_text())
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==config['source_commit']
for relative,value in config['loader_abi_files'].items():
    assert digest(repo/relative)==value
assert digest(guest/'usr/lib/dyld')==config['packaged_loader_sha256']
assert digest(guest/'usr/lib/system/libdyld.dylib')==config['packaged_libdyld_sha256']
assert not (root/'runtime/state/prefix/usr/lib/dyld').exists()
text=re.sub(r'#[^\n]*','',(repo/'CMakeLists.txt').read_text())
section=text.split('add_circular(system_dyld FAT',1)[1].split('UPWARD',1)[0].split('SOURCES',1)[1]
sources=re.findall(r'\S+\.(?:cpp|c|S)',section)
assert len(sources)==29 and sources.count('src/runnable_archs.c')==1
resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip())
generated=build/'include';system=generated/'System';system.mkdir(parents=True,exist_ok=True)
for base in [darling/'src/external/xnu/osfmk',darling/'src/external/xnu/bsd']:
    for path in base.iterdir():
        link=system/path.name
        if path.is_dir() and not link.exists():link.symlink_to(path,target_is_directory=True)
includes=[generated,repo/'include',repo/'include/mach-o',repo/'dyld3/shared-cache',repo/'dyld3',repo/'src',repo/'launch-cache',repo,
    darling/'src/external/libcxx/include',sdk/'usr/include',resource/'include']
objects=[]
for index,relative in enumerate(sources):
    source=repo/relative;obj=build/(str(index)+'-'+source.stem+'.o');objects.append(obj)
    print('Compile',relative,flush=True)
    cxx=source.suffix=='.cpp'
    subprocess.run(['clang++-19' if cxx else 'clang-19','-target','x86_64-apple-macos'+args.minimum_os,'-isysroot',str(sdk),
        '-nostdinc',*(['-nostdinc++','-std=c++17','-fno-rtti','-fno-exceptions'] if cxx else []),
        *['-I'+str(p) for p in includes],'-idirafter',str(apple/'usr/include'),
        *(['-include',str(darling/'src/duct/include/CrashReporterClient.h')] if cxx else []),
        '-DDARLING','-DPRIVATE=1','-DPLATFORM_MacOSX','-D__DARWIN_UNIX03','-DHAVE_STDINT_H=1',
        '-DBUILDING_LIBDYLD=1','-D_LIBCPP_NO_EXCEPTIONS=1','-D_LIBC_NO_FEATURE_VERIFICATION',
        '-fblocks','-fPIC','-O0','-Wno-deprecated-declarations','-Wno-nullability-completeness',
        '-Wno-macro-redefined','-c',str(source),'-o',str(obj)],check=True)
output=build/'libdyld.dylib';pending=output.with_name('libdyld.dylib.pending')
siblings=['system_c','system_kernel','system_malloc','system_blocks','system_pthread',
    'system_sandbox','dispatch','compiler_rt','system_platform','launch']
guestpath=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
ld='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld'
subprocess.run([str(root/'bin/darling'),'shell',ld,'-dylib','-arch','x86_64','-platform_version','macos',args.minimum_os,'11',
    '-install_name','/usr/lib/system/libdyld.dylib','-compatibility_version','1.0.0','-current_version','421.1.0',
    '-syslibroot','/Volumes/SystemRoot/usr/libexec/darling',
    '-L','/Volumes/SystemRoot/usr/libexec/darling/usr/lib/system',
    *[v for name in siblings for v in ['-upward_library','/Volumes/SystemRoot/usr/libexec/darling/usr/lib/system/lib'+name+'.dylib']],
    *[guestpath(p) for p in objects],'-o',guestpath(pending)],check=True,timeout=120)
pending.replace(output)
exports=lambda p:set(re.findall(r'^(?:0x[\da-fA-F]+|\[re-export\])\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(p)],text=True),re.M))
old=exports(guest/'usr/lib/system/libdyld.dylib');new=exports(output)
assert not old-new and '__dyld_get_dlopen_image_header' in new
base=root/args.variant_base;variant=build/'darling-root'
with (root/'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    pending_root=build/'darling-root.pending';previous=build/'darling-root.previous'
    for owned in (pending_root,previous):
        if owned.exists():shutil.rmtree(owned)
    subprocess.run(['cp','-a','--reflink=auto',str(base),str(pending_root)],check=True)
    subprocess.run(['cp','-p','--reflink=auto',str(output),str(pending_root/'usr/lib/system/libdyld.dylib')],check=True)
    if variant.exists():variant.replace(previous)
    pending_root.replace(variant)
    if previous.exists():shutil.rmtree(previous)
report=dict(installed=False,full_libdyld_source_build=True,full_loader_source_rebuild=False,
    minimum_os=args.minimum_os,SDK_version='11',
    complete_source_files=len(sources),source_configuration=config,
    source_files={p:digest(repo/p) for p in sources},
    source_build_inputs={p:digest(repo/p) for p in ['CMakeLists.txt','include/mach-o/dyld_priv.h','include/mach-o/utils.h']},
    library_sha256=digest(output),
    original_exports_preserved=len(old),source_exports=len(new),
    variant_root=str(variant.relative_to(root)),runtime_execution_verified=False,
    loader_abi_coupling='Pinned dyld2 ImageLoader header and packaged loader. Registry validation via NSModule API under the existing libdyld recursive lock; header through actual C++ virtual interface, without private-field offsets.',
    full_compatibility=False,full_xcode_build_ready=False,signing_ready=False)
(root/args.report).write_text(json.dumps(report,indent=2)+'\n')
print('Built complete source libdyld:',output)
