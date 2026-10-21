#!/usr/bin/env python3
"""Build the complete Darling libxpc source into a separate runtime variant."""
from pathlib import Path
import argparse,fcntl,hashlib,json,re,shutil,subprocess
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',default='runtime/libxpc-source')
parser.add_argument('--report',default='artifacts/libxpc-source.json')
parser.add_argument('--variant-base',default='runtime/rootfs/usr/libexec/darling')
args=parser.parse_args()
repo=root/'vendor/darling/src/external/libxpc'
expected='394e033333d3c253a12f08a99090c113b0917d00'
config=json.loads((root/'config/libxpc-source-build.json').read_text())
for relative,commit in config['source_repositories'].items():
    if subprocess.check_output(['git','-C',str(root/relative),'rev-parse','HEAD'],text=True).strip()!=commit:
        raise ValueError('Changed source/header revision: '+relative)
for relative,digest in config['base_libraries'].items():
    if hashlib.sha256((root/relative).read_bytes()).hexdigest()!=digest:
        raise ValueError('Changed baseline library: '+relative)
if subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()!=expected:
    raise ValueError('Changed Darling libxpc base revision')
section=re.search(r'set\(xpc_sources\s+(.*?)\n\)',(repo/'CMakeLists.txt').read_text(),re.S).group(1)
sources=re.findall(r'^\s*(src/\w+\.[cm])\s*$',section,re.M)
if len(sources)<35:raise ValueError('Incomplete source set')
build=root/args.output_dir;build.mkdir(exist_ok=True)
variant_base=(root/args.variant_base).resolve();assert variant_base.is_dir() and variant_base.is_relative_to(root/'runtime')
sdk=root/'vendor/darling/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
apple=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
objects=[]
resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip())
frameworks=sdk/'System/Library/Frameworks'
framework_flags=[item for directory in [frameworks,*sorted(frameworks.glob('*.framework/Frameworks'))]
    for item in ['-F',str(directory)]]
for relative in sources:
    source=repo/relative;obj=build/(source.stem+'.o');objects.append(str(obj))
    print('Compile',relative,flush=True)
    subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),
        '-nostdinc','-isystem',str(sdk/'usr/include'),'-isystem',str(resource/'include'),
        *framework_flags,
        '-idirafter',str(apple/'usr/include'),'-I',str(repo/'include'),'-I',str(repo/'internal-include'),
        '-include',str(repo/'internal-include/xpc/prefix.h'),'-D__XPC_BUILDING_XPC__',
        '-D__XPC_PROJECT_BUILD__','-DDARLING','-DPLATFORM_MacOSX','-D__DARWIN_UNIX03',
        '-DTARGET_OS_WASI=0','-DNDEBUG','-fblocks','-fvisibility=hidden','-fPIC','-O2',
        '-Wno-extern-initializer','-Wno-gnu-folding-constant','-Wno-nullability-completeness','-Wno-duplicate-protocol',
        '-c',str(source),'-o',str(obj)],check=True)
guest=root/'runtime/rootfs/usr/libexec/darling';output=build/'libxpc.dylib'
temporary=output.with_name(output.name+'.pending')
siblings=['system_c','system_kernel','system_blocks','dispatch','system_platform','system_malloc',
    'launch','system_info','dyld','unwind','compiler_rt','system_pthread','system_trace']
def guest_path(path):
    return '/Volumes/SystemRoot/workspace/'+str(Path(path).relative_to(root))
ld='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld'
guest_sdk='/Volumes/SystemRoot/usr/libexec/darling'
subprocess.run([str(root/'bin/darling'),'shell',ld,'-dylib','-arch','x86_64','-platform_version','macos','11','11',
    '-install_name','/usr/lib/system/libxpc.dylib','-compatibility_version','1.0.0',
    '-syslibroot',guest_sdk,'-L',guest_sdk+'/usr/lib/system','-L',guest_sdk+'/usr/lib',
    *['-l'+name for name in siblings],'-upward_library',guest_sdk+'/usr/lib/libobjc.A.dylib',
    '-reexported_symbols_list',guest_path(repo/'scripts/reexported-symbols.exp'),
    *[guest_path(path) for path in objects],'-o',guest_path(temporary)],check=True,timeout=120)
temporary.replace(output)
# Darling itself creates an overlay with this whole directory as its lower
# layer. A bind mount on an individual file below that layer is NOT traversed
# by overlayfs, so select a complete, separate directory tree instead.
variant=build/'darling-root'
# Serialize publication with all Darling sessions. Reflink a fresh baseline
# instead of overwriting dependencies that might still be mapped by a session.
with (root/'runtime/session.lock').open('a') as session_lock:
    fcntl.flock(session_lock,fcntl.LOCK_EX)
    pending=build/'darling-root.pending';previous=build/'darling-root.previous'
    for owned in (pending,previous):
        if owned.exists():shutil.rmtree(owned)
    subprocess.run(['cp','-a','--reflink=auto',str(variant_base),str(pending)],check=True)
    subprocess.run(['cp','-p','--reflink=auto',str(output),str(pending/'usr/lib/system/libxpc.dylib')],check=True)
    if variant.exists():variant.replace(previous)
    pending.replace(variant)
    if previous.exists():shutil.rmtree(previous)
def exported(path):
    listing=subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(path)],text=True)
    return set(re.findall(r'^(?:0x[\da-fA-F]+|\[re-export\])\s+(\S+)',listing,re.M)),listing.count('[re-export]')
old_exports,old_reexports=exported(guest/'usr/lib/system/libxpc.dylib')
new_exports,new_reexports=exported(output)
if old_exports-new_exports or old_reexports!=new_reexports:
    raise ValueError('Original libxpc export/reexport contract was not preserved')
modified=subprocess.check_output(['git','-C',str(repo),'diff','--name-only'],text=True).splitlines()
modified+=subprocess.check_output(['git','-C',str(repo),'ls-files','--others','--exclude-standard'],text=True).splitlines()
report=dict(installed=False,full_compatibility=False,source_commit=expected,
    full_libxpc_source_build=True,full_darling_rebuild=False,
    complete_source_files=len(sources),source_files={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in sources},
    modified_files={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in modified},
    original_exports_preserved=len(old_exports),launch_reexports_preserved=old_reexports,
    source_exports=len(new_exports),
    source_configuration=config,
    variant_base=str(variant_base.relative_to(root)),
    public_header_sha256=hashlib.sha256((repo/'include/xpc/xpc.h').read_bytes()).hexdigest(),
    library_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),bootstrap_execution_verified=False,
    variant_root=str(variant.relative_to(root)))
(root/args.report).write_text(json.dumps(report,indent=2)+'\n')
print('Built complete source libxpc:',output)
