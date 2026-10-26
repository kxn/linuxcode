#!/usr/bin/env python3
"""Update the pinned Darling loader's static fcntl from the tested kernel source.

This is a source component update, not a complete dyld rebuild. Preserve the
ImageLoader ABI, original segments and addresses; add one RX segment containing
the compiled fcntl and generated descriptor RPC, and redirect the old entry.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel-build',required=True);p.add_argument('--output',required=True);a=p.parse_args()
folder=root/a.output;assert folder.is_relative_to(root/'runtime') and not folder.exists();folder.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=root/'runtime/rootfs/usr/libexec/darling/usr/lib/dyld';original=source.read_bytes()
assert sha(source)==json.loads((root/'config/libdyld-source-build.json').read_text())['packaged_loader_sha256']
assert struct.unpack_from('>I',original)[0]==0xcafebabe
fatcount=struct.unpack_from('>I',original,4)[0];selected=[]
for i in range(fatcount):
    cpu,sub,offset,size,alignment=struct.unpack_from('>IIIII',original,8+20*i)
    if cpu==0x1000007:selected.append((i,offset,size))
assert len(selected)==1
fatindex,sliceoffset,slicesize=selected[0];assert sliceoffset+slicesize==len(original)
thin=bytearray(original[sliceoffset:]);header=list(struct.unpack_from('<8I',thin));assert header[0]==0xfeedfacf and header[3]==7
segments=[];at=32
for i in range(header[4]):
    kind,size=struct.unpack_from('<II',thin,at)
    if kind==25:segments.append(struct.unpack_from('<II16sQQQQiiII',thin,at))
    at+=size
assert at==32+header[5]
firstsection=min(struct.unpack_from('<16s16sQQI',thin,32+72)[4],4096)
assert at+72<=firstsection and not any(thin[at:at+72])
align=lambda n:(n+4095)&~4095
vm=align(max(s[3]+s[4] for s in segments));fileoffset=align(len(thin))
listing=subprocess.check_output(['llvm-nm-19','--arch','x86_64',str(source)],text=True)
symbols={}
for line in listing.splitlines():
    m=re.match(r'([0-9a-f]+)\s+\S\s+(\S+)',line)
    if m:symbols.setdefault(m[2],set()).add(int(m[1],16))
build=json.loads((root/a.kernel_build).read_text());fcntlrow=next(r for r in build['sources'] if '/emulation/' in r['source'] and r['source'].endswith('/fcntl.c'));rpcrow=next(r for r in build['sources'] if r['source'].endswith('/darlingserver/src/rpc.c'))
objects=[Path(r['command'][r['command'].index('-o')+1]) for r in [fcntlrow,rpcrow]]
for row in [fcntlrow,rpcrow]:assert sha(root/row['source'])==row['sha256']
undefined=set();defined=set()
for obj in objects:
    for line in subprocess.check_output(['llvm-nm-19',str(obj)],text=True).splitlines():
        fields=line.split()
        if len(fields)==2 and fields[0]=='U':undefined.add(fields[1])
        elif len(fields)==3:defined.add(fields[2])
aliases={};lines=[]
for name in sorted(undefined-defined):
    assert name in symbols and len(symbols[name])==1,name
    value=next(iter(symbols[name]));aliases[name]=value
    # Link at zero with shifted absolute branch targets. The emitted RX bytes
    # then use the correct PC-relative offsets when mapped at `vm` + slide.
    lines+=['.globl '+name,'.private_extern '+name,name+' = '+str(value-vm)]
assembly=folder/'aliases.S';assembly.write_text('\n'.join(lines)+'\n');aliasobject=folder/'aliases.o'
commands=[['clang-19','-target','x86_64-apple-macos11','-c',str(assembly),'-o',str(aliasobject)]]
component=folder/'component.dylib'
commands.append(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-dead_strip','-no_fixup_chains','-exported_symbol','_sys_fcntl_nocancel',*[str(o) for o in objects],str(aliasobject),'-o',str(component)])
for command in commands:subprocess.run(command,check=True)
data=component.read_bytes();h=struct.unpack_from('<8I',data);pos=32;text=None
for i in range(h[4]):
    kind,size=struct.unpack_from('<II',data,pos)
    if kind==25:
        s=struct.unpack_from('<II16sQQQQiiII',data,pos)
        if s[2].rstrip(b'\0')==b'__TEXT':text=s
        else:assert s[2].rstrip(b'\0')==b'__LINKEDIT','unexpected data/GOT segment'
    if kind==0x80000022:
        values=struct.unpack_from('<12I',data,pos);assert not any(values[3:11:2]),'component requires runtime fixups'
    if kind in [0xc,0x18,0x80000018]:raise AssertionError('component imports a dynamic library')
    pos+=size
assert text and text[3]==0 and text[5]==0 and text[7:9]==(5,5)
listing=subprocess.check_output(['llvm-nm-19',str(component)],text=True)
entry=int(re.search(r'^([0-9a-f]+)\s+t\s+_sys_fcntl_nocancel$',listing,re.M)[1],16)
oldentry=next(iter(symbols['_sys_fcntl_nocancel']));target=vm+entry
oldsegment=next(s for s in segments if s[3]<=oldentry<s[3]+s[4]);oldfile=oldentry-oldsegment[3]+oldsegment[5]
before=bytes(thin[oldfile:oldfile+5]);assert before==bytes.fromhex('554889e548'),before.hex()
thin[oldfile:oldfile+5]=b'\xe9'+struct.pack('<i',target-(oldentry+5))
segment=struct.pack('<II16sQQQQiiII',25,72,b'__BOOT_FCNTL',vm,text[4],fileoffset,text[6],5,5,0,0)
thin[at:at+72]=segment;header[4]+=1;header[5]+=72;struct.pack_into('<8I',thin,0,*header)
thin+=b'\0'*(fileoffset-len(thin))+data[:text[6]]
output=bytearray(original[:sliceoffset])+thin;struct.pack_into('>I',output,8+fatindex*20+12,len(thin))
targetfile=folder/'dyld';targetfile.write_bytes(output);targetfile.chmod(0o755)
changed=[i for i,(x,y) in enumerate(zip(original,output)) if x!=y]
allowed=set(range(8+fatindex*20+12,8+fatindex*20+16))|set(range(sliceoffset+16,sliceoffset+24))|set(range(sliceoffset+at,sliceoffset+at+72))|set(range(sliceoffset+oldfile,sliceoffset+oldfile+5))
assert all(i in allowed for i in changed)
report=dict(source=str(source.relative_to(root)),source_sha256=sha(source),loader=str(targetfile.relative_to(root)),loader_sha256=sha(targetfile),source_component_update=True,full_loader_source_rebuild=False,old_ImageLoader_ABI_preserved=True,old_entry=oldentry,new_entry=target,entry_original_bytes=before.hex(),entry_replacement_bytes=bytes(thin[oldfile:oldfile+5]).hex(),segment_vmaddr=vm,segment_fileoff=fileoffset,component_rebases=0,component_dynamic_imports=0,aliases=aliases,kernel_build=a.kernel_build,kernel_source=fcntlrow,rpc_source=rpcrow,commands=commands,files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/a.kernel_build,root/fcntlrow['source'],root/rpcrow['source'],assembly,*objects]},runtime_execution_verified=False,full_goal_complete=False)
(folder/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('BUILD_REPORT',folder/'build.json')
