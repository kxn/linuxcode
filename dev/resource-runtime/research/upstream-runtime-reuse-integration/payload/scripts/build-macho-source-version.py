#!/usr/bin/env python3
"""Rebuild the existing cache-introspection component with Apple's source-version API.

All new function bodies are selected unchanged from pinned Apple dyld sources.
Only writes a new private directory; does not launch Darling or change libSystem.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,subprocess
ROOT=Path(__file__).resolve().parent.parent

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def extract(repo,relative,pattern):
    text=(repo/relative).read_text();match=re.search(pattern,text,re.M)
    assert match,pattern
    start=text.index('{',match.end());end=start+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[match.start():end]

def exports(path):
    output=subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(path)],text=True)
    return set(re.findall(r'^(?:0x[\da-fA-F]+|\[re-export\])\s+(\S+)',output,re.M))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);a=parser.parse_args()
    output=a.output.resolve();assert output.is_relative_to(ROOT/'runtime') and not output.exists()
    repo=ROOT/'vendor/apple-dyld';config_path=ROOT/'config/dyld-cache-introspection.json';config=json.loads(config_path.read_text())
    head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip();assert head==config['source_commit']
    for name,digest in config['files'].items():assert sha(repo/name)==digest,name
    source_status=subprocess.check_output(['git','-C',str(repo),'status','--porcelain','--untracked-files=no'],text=True);assert not source_status
    generated_report=ROOT/'artifacts/macho-slices-source.json';generated=json.loads(generated_report.read_text());assert generated['source_commit']==head
    for name,digest in generated['generated_files'].items():assert sha(ROOT/'runtime/macho-slices-source'/name)==digest,name
    output.mkdir();selected=output/'selected';selected.mkdir();objects=output/'objects';objects.mkdir();libraries=output/'libraries';libraries.mkdir()
    for name in generated['generated_files']:shutil.copy2(ROOT/'runtime/macho-slices-source'/name,selected/name)
    functions=[extract(repo,'mach_o/UnsafeHeader.cpp',r'^'+kind+r' UnsafeHeader::'+name+r'\(') for kind,name in [('bool','hasMachOBigEndianMagic'),('Error','forEachLoadCommand'),('void','forEachLoadCommandSafe'),('bool','sourceVersion')]]
    api=extract(repo,'libdyld/utils.cpp',r'^bool macho_source_version\(')
    def license(relative):return (repo/relative).read_text().split('#include',1)[0]
    header=selected/'source-version-header.cpp';header.write_text(license('mach_o/UnsafeHeader.cpp')+'#include "UnsafeHeader.h"\n#include "Misc.h"\nnamespace mach_o {\n'+'\n\n'.join(functions)+'\n}\n')
    public=selected/'source-version-api.cpp';public.write_text(license('libdyld/utils.cpp')+'#include <mach-o/loader.h>\n#include "UnsafeHeader.h"\nusing mach_o::UnsafeHeader; using mach_o::Version64;\nextern "C" __attribute__((visibility("default")))\n'+api+'\n')
    # Recompile the complete existing component; do not link stale local objects.
    sources=[('compat',ROOT/'scripts/dyld-cache-introspection.c'),('architecture',repo/'mach_o/Architecture.cpp'),('arch-api',ROOT/'scripts/macho-arch-compat.cpp'),('universal',selected/'Universal-fixed.cpp'),('macho-error',repo/'mach_o/Error.cpp'),('header-selected',selected/'UnsafeHeader-selected.cpp'),('slice-api',selected/'slice-api.cpp'),('source-version-header',header),('source-version-api',public)]
    sdk=ROOT/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';commands=[];objs=[]
    for name,source in sources:
        obj=objects/(name+'.o');objs.append(obj)
        if source.suffix=='.c':cmd=['clang-19','-target','x86_64-apple-macos15.4','-isysroot',str(sdk),'-fblocks','-O2','-DTARGET_OS_EXCLAVEKIT=0','-I',str(repo/'include')]
        else:
            cmd=['clang++-19','-target','x86_64-apple-macos15.4','-isysroot',str(sdk),'-std=c++20','-nostdinc++','-I',str(sdk/'usr/include/c++/v1'),'-I',str(repo/'mach_o'),'-I',str(repo/'common'),'-fblocks','-DTARGET_OS_EXCLAVEKIT=0','-D_LIBCPP_DISABLE_AVAILABILITY','-fno-rtti','-fno-exceptions','-fvisibility=hidden','-O2']
            if name=='macho-error':cmd+=['-I',str(ROOT/'vendor/darling/src/external/libplatform/private')]
        cmd+=['-MMD','-MF',str(objects/(name+'.d')),'-c',str(source),'-o',str(obj)];commands.append(cmd);subprocess.run(cmd,check=True)
    guest=ROOT/'runtime/rootfs/usr/libexec/darling';library=libraries/'libDarlingCacheIntrospection.dylib'
    link=['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','15.4','15.4','-install_name','/usr/lib/libDarlingCacheIntrospection.dylib','-syslibroot',str(guest),'-L',str(guest/'usr/lib'),'-lSystem','-dead_strip',*[str(p) for p in objs],'-o',str(library)];commands.append(link);subprocess.run(link,check=True)
    data=library.read_bytes();at=32;dependencies=[];initializers=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        kind,size=struct.unpack_from('<II',data,at)
        if kind in (0xc,0x80000018,0x8000001f,0x80000023):
            start=at+struct.unpack_from('<I',data,at+8)[0];dependencies.append(data[start:data.index(0,start)].decode())
        if kind==25:
            for i in range(struct.unpack_from('<I',data,at+64)[0]):
                section=at+72+80*i;name=data[section:section+16].split(b'\0')[0]
                if name==b'__mod_init_func' and struct.unpack_from('<Q',data,section+40)[0]:initializers.append(name.decode())
        at+=size
    assert dependencies==['/usr/lib/libSystem.B.dylib'] and not initializers,(dependencies,initializers)
    baseline=ROOT/'runtime/native-library-stage/libDarlingCacheIntrospection.dylib';old=exports(baseline);new=exports(library);assert old<=new,sorted(old-new);assert new-old=={'_macho_source_version'},sorted(new-old)
    undefined=subprocess.check_output(['llvm-nm-19','-u',str(library)],text=True).splitlines()
    report=dict(full_existing_component_rebuilt=True,component_translation_units=len(sources),source_commit=head,source_dirty=False,
                library=str(library.relative_to(ROOT)),library_sha256=sha(library),original_install_name='/usr/lib/libDarlingCacheIntrospection.dylib',
                parent_library=str(baseline.relative_to(ROOT)),parent_library_sha256=sha(baseline),existing_exports_preserved=len(old),new_export_names=sorted(new-old),total_exports=len(new),
                selected_original_API='libdyld/utils.cpp:macho_source_version',selected_unmodified_API_body_sha256=hashlib.sha256(api.encode()).hexdigest(),
                selected_unmodified_header_methods=['hasMachOBigEndianMagic','forEachLoadCommand','forEachLoadCommandSafe','sourceVersion'],
                selected_method_body_sha256=[hashlib.sha256(s.encode()).hexdigest() for s in functions],existing_hasMachOMagic_definition_reused=True,
                dependencies=dependencies,module_initializers=initializers,undefined_symbols=undefined,commands=commands,
                files={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),config_path,generated_report,*[p for _,p in sources],*[repo/p for p in config['files']],*objs,library]},
                libSystem_modified=False,old_component_modified=False,native_execution_verified=False,full_macho_buffer_validation_claimed=False)
    (output/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(output/'build.json')

if __name__=='__main__':main()
