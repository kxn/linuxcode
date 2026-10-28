#!/usr/bin/env python3
"""Add the source-built bootstrap vchroot component to an existing private loader.

Reuses the bootstrap-fcntl component method to preserve the pinned ImageLoader
ABI. The old prefix globals remain shared with the loader's fdpath/unexpand;
only vchroot_expand is redirected. No original Unity bytes/names are changed.
"""
from pathlib import Path
import argparse, hashlib, json, re, shlex, shutil, struct, subprocess
ROOT=Path(__file__).resolve().parent.parent

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def symbols(path):
    rows={}
    for line in subprocess.check_output(['llvm-nm-19','--arch','x86_64',str(path)],text=True).splitlines():
        match=re.match(r'([0-9a-f]+)\s+\S\s+(\S+)',line)
        if match:rows.setdefault(match[2],set()).add(int(match[1],16))
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bootstrap-report',required=True)
    p.add_argument('--loader-build',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--statfs-family',action='store_true',help='Compile the complete statfs/fstatfs and stat conversion units into the same bootstrap source component')
    a=p.parse_args()
    folder=(ROOT/a.output).absolute()
    assert folder.is_relative_to(ROOT/'runtime') and not folder.exists()
    proof=json.loads((ROOT/a.bootstrap_report).read_text())
    assert proof['bootstrap_objects_built'] and proof['VARIANT_DYLD'] and not proof['added_imports'] and not proof['forbidden_bootstrap_imports']
    prior=json.loads((ROOT/a.loader_build).read_text())
    assert prior['old_ImageLoader_ABI_preserved'] and prior['source_component_update']
    loader=ROOT/prior['loader'];assert sha(loader)==prior['loader_sha256']
    row=proof['records']['after'];source=ROOT/row['source'];assert sha(source)==row['source_sha256']
    folder.mkdir()
    # These globals also belong to preexisting fdpath/unexpand. Preserve one
    # owner rather than introducing a second initialized root-path cache.
    text=source.read_text()
    for old,new in [('static char prefix_path[4096] = {0};','extern char prefix_path[4096];'),('static int prefix_path_len = -1;','extern int prefix_path_len;')]:
        assert text.count(old)==1; text=text.replace(old,new)
    compiled_source=folder/'vchroot-bootstrap.c';compiled_source.write_text(text)
    obj=folder/'vchroot.o';command=list(row['command'])
    assert command.count(str(source))==1
    command[command.index(str(source))]=str(compiled_source);command[command.index('-o')+1]=str(obj)
    subprocess.run(command,check=True)
    objects=[obj];source_units=[];dependency_files=[];compile_commands=[command];mounts_selection=None
    roots=['_vchroot_expand']
    if a.statfs_family:
        emulation=ROOT/'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src'
        mounts=emulation.parent/'include/xnu_syscall/bsd/helper/stat/mounts.h'
        include_root=folder/'source-include'
        selected_mounts=include_root/'darling/emulation/xnu_syscall/bsd/helper/stat/mounts.h'
        selected_mounts.parent.mkdir(parents=True)
        shutil.copy2(mounts,selected_mounts)
        mounts_selection=dict(source=str(mounts.relative_to(ROOT)),compiled_header=str(selected_mounts.relative_to(ROOT)),sha256=sha(mounts))
        assert sha(selected_mounts)==mounts_selection['sha256']
        dependency_files.extend([mounts,selected_mounts])
        # fstatfs64 calls statfs_linux_to_bsd64; compile its defining complete
        # conversion unit as well, rather than retaining an older mount ABI.
        sources=[emulation/'xnu_syscall/bsd/impl/stat/statfs.c',
                 emulation/'xnu_syscall/bsd/impl/stat/fstatfs.c',
                 emulation/'conversion/stat/common.c']
        for index,unit in enumerate(sources):
            output_object=folder/('statfs-'+str(index)+'.o');dep=folder/('statfs-'+str(index)+'.d')
            build_command=list(row['command'])
            # Historical bootstrap commands put a generated include tree first.
            # Select the actual current mount reader rather than its old copy.
            build_command[1:1]=['-I'+str(include_root)]
            build_command[build_command.index(str(source))]=str(unit)
            build_command[build_command.index('-o')+1]=str(output_object)
            build_command+=['-MMD','-MF',str(dep)]
            subprocess.run(build_command,check=True)
            source_units.append(dict(source=str(unit.relative_to(ROOT)),source_sha256=sha(unit),
                                     object=str(output_object.relative_to(ROOT)),object_sha256=sha(output_object),command=build_command))
            compile_commands.append(build_command);objects.append(output_object)
            dependencies=[Path(name) for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]) if Path(name).is_file()]
            if unit.name=='fstatfs.c':
                assert [path for path in dependencies if path.name=='mounts.h']==[selected_mounts]
            dependency_files.extend(dependencies)
            dependency_files.append(dep)
        roots+=['_sys_statfs','_sys_statfs64','_sys_fstatfs','_sys_fstatfs64']
    original=loader.read_bytes();assert struct.unpack_from('>I',original)[0]==0xcafebabe
    slices=[]
    for index in range(struct.unpack_from('>I',original,4)[0]):
        cpu,sub,offset,size,align=struct.unpack_from('>5I',original,8+20*index)
        if cpu==0x1000007:slices.append((index,offset,size))
    (fat_index,slice_offset,slice_size),=slices
    assert slice_offset+slice_size==len(original)
    thin=bytearray(original[slice_offset:]);header=list(struct.unpack_from('<8I',thin));assert header[0]==0xfeedfacf and header[3]==7
    segments=[];sections=[];at=32
    for _ in range(header[4]):
        kind,size=struct.unpack_from('<II',thin,at)
        if kind==25:
            segment=struct.unpack_from('<II16sQQQQiiII',thin,at);segments.append(segment)
            for j in range(segment[9]):
                section=struct.unpack_from('<16s16sQQI',thin,at+72+80*j)
                if section[4]:sections.append(section[4])
        at+=size
    assert at==32+header[5] and at+72<=min(sections) and not any(thin[at:at+72])
    align=lambda n:(n+4095)&~4095
    vm=align(max(s[3]+s[4] for s in segments));fileoff=align(len(thin))
    old_symbols=symbols(loader);undefined=set();defined=set()
    for object_path in objects:
        for line in subprocess.check_output(['llvm-nm-19',str(object_path)],text=True).splitlines():
            fields=line.split()
            if len(fields)==2 and fields[0]=='U':undefined.add(fields[1])
            elif len(fields)==3:defined.add(fields[2])
    aliases={};lines=[];unused_object_imports=[]
    for name in sorted(undefined-defined):
        if name not in old_symbols:
            # ld -dead_strip must remove unreachable functions referencing it;
            # a live unresolved import still fails the default static link.
            unused_object_imports.append(name)
            continue
        assert len(old_symbols[name])==1,name
        value=next(iter(old_symbols[name]));aliases[name]=value
        lines+=['.globl '+name,'.private_extern '+name,name+' = '+str(value-vm)]
    assert '_prefix_path' in aliases and '_prefix_path_len' in aliases
    assembly=folder/'aliases.S';assembly.write_text('\n'.join(lines)+'\n');alias_obj=folder/'aliases.o'
    commands=compile_commands+[['clang-19','-target','x86_64-apple-macos11','-c',str(assembly),'-o',str(alias_obj)]]
    subprocess.run(commands[-1],check=True)
    component=folder/'component.dylib';link=['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-dead_strip','-no_fixup_chains',
        *sum((['-exported_symbol',name] for name in roots),[]),*[str(path) for path in objects],str(alias_obj),'-o',str(component)];commands.append(link);subprocess.run(link,check=True)
    data=component.read_bytes();head=struct.unpack_from('<8I',data);pos=32;text_segment=None
    for _ in range(head[4]):
        kind,size=struct.unpack_from('<II',data,pos)
        if kind==25:
            segment=struct.unpack_from('<II16sQQQQiiII',data,pos)
            if segment[2].rstrip(b'\0')==b'__TEXT':text_segment=segment
            else:assert segment[2].rstrip(b'\0')==b'__LINKEDIT','Unexpected writable/GOT segment'
        if kind==0x80000022:assert not any(struct.unpack_from('<12I',data,pos)[3:11:2]),'Runtime fixups required'
        assert kind not in (0xc,0x18,0x80000018),'Component imports dylib'
        pos+=size
    assert text_segment and text_segment[3]==0 and text_segment[5]==0 and text_segment[7:9]==(5,5)
    linked_symbols=symbols(component);redirects=[];patch_ranges=[]
    for name in roots:
        assert len(old_symbols[name])==len(linked_symbols[name])==1
        oldentry=next(iter(old_symbols[name]));target=vm+next(iter(linked_symbols[name]))
        oldsegment=next(s for s in segments if s[3]<=oldentry<s[3]+s[4]);oldfile=oldentry-oldsegment[3]+oldsegment[5]
        before=bytes(thin[oldfile:oldfile+5]);assert before[:4]==bytes.fromhex('554889e5'),(name,before.hex())
        thin[oldfile:oldfile+5]=b'\xe9'+struct.pack('<i',target-(oldentry+5));patch_ranges.append((oldfile,5))
        redirects.append(dict(symbol=name,old_entry=oldentry,new_entry=target,original_bytes=before.hex(),replacement_bytes=bytes(thin[oldfile:oldfile+5]).hex()))
    thin[at:at+72]=struct.pack('<II16sQQQQiiII',25,72,b'__BOOT_VCHROOT',vm,text_segment[4],fileoff,text_segment[6],5,5,0,0)
    header[4]+=1;header[5]+=72;struct.pack_into('<8I',thin,0,*header)
    thin+=b'\0'*(fileoff-len(thin))+data[:text_segment[6]]
    result=bytearray(original[:slice_offset])+thin;struct.pack_into('>I',result,8+fat_index*20+12,len(thin))
    changed=[i for i,(x,y) in enumerate(zip(original,result)) if x!=y]
    allowed=set(range(8+fat_index*20+12,8+fat_index*20+16))|set(range(slice_offset+16,slice_offset+24))|set(range(slice_offset+at,slice_offset+at+72))
    for offset,length in patch_ranges:allowed.update(range(slice_offset+offset,slice_offset+offset+length))
    assert all(i in allowed for i in changed)
    output=folder/'dyld';output.write_bytes(result);output.chmod(0o755)
    first=redirects[0]
    inputs=[Path(__file__),ROOT/a.bootstrap_report,ROOT/a.loader_build,source,compiled_source,*objects,assembly,alias_obj,component,output,*dependency_files]
    inputs.extend(ROOT/item['source'] for item in source_units)
    report=dict(source=str(loader.relative_to(ROOT)),source_sha256=sha(loader),loader=str(output.relative_to(ROOT)),loader_sha256=sha(output),
                old_ImageLoader_ABI_preserved=True,source_component_update=True,full_loader_source_rebuild=False,
                old_entry=first['old_entry'],new_entry=first['new_entry'],component_rebases=0,component_dynamic_imports=0,component_writable_segments=0,
                original_prefix_globals_preserved=True,aliases=aliases,dead_stripped_object_imports=unused_object_imports,commands=commands,bootstrap_object_proof=a.bootstrap_report,
                parent_loader_build=a.loader_build,entry_original_bytes=first['original_bytes'],entry_replacement_bytes=first['replacement_bytes'],
                original_source=str(source.relative_to(ROOT)),original_source_sha256=sha(source),compiled_source=str(compiled_source.relative_to(ROOT)),compiled_source_sha256=sha(compiled_source),
                shared_prefix_global_declarations_only_transformed=True,runtime_execution_verified=False,
                statfs_family_source_update=a.statfs_family,source_units=source_units,entry_redirects=redirects,
                raw_Linux_mount_reader_reused=a.statfs_family,prior_fcntl_component_bytes_preserved=True,
                mounts_header_selection=mounts_selection,
                files={str(path.relative_to(ROOT)):sha(path) for path in inputs if path.is_relative_to(ROOT)},
                toolchain_headers={str(path):sha(path) for path in inputs if not path.is_relative_to(ROOT)})
    (folder/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'build.json')

if __name__=='__main__':main()
