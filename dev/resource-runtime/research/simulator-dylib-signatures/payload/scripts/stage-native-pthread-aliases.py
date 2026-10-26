#!/usr/bin/env python3
"""Apply upstream pthread aliases to a private FAT library without changing code."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,struct,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.isalnum()
read=lambda n:json.loads((root/n).read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parent=read(a.parent_stage);base=root/Path(parent['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent/'darling-root';source=base/'usr/lib/system/libsystem_pthread.dylib';original=source.read_bytes();assert original[:4]==bytes.fromhex('cafebabe')
api=runpy.run_path(str(root/'scripts/macho-named-reexport.py'));rows=[];additions={}
for line in (root/'vendor/darling/src/external/libpthread/xcodescripts/pthread.aliases').read_text().splitlines():
 line=line.split('#')[0].strip()
 if line:target,alias=line.split();additions[alias]=target
def update(data):
 b=bytearray(data);assert data[:4]==bytes.fromhex('cffaedfe');at=32;exports=None;linkedit=None
 for i in range(struct.unpack_from('<I',b,16)[0]):
  kind,n=struct.unpack_from('<II',b,at)
  if kind==25 and b[at+8:at+24].rstrip(b'\0')==b'__LINKEDIT':linkedit=at
  if kind in [0x22,0x80000022]:exports=at+40
  if kind==0x80000033:exports=at+8
  assert kind!=29,'stale signature would need re-signing'
  at+=n
 assert exports is not None and linkedit is not None
 off,n=struct.unpack_from('<II',b,exports);old=api['entries'](bytes(b[off:off+n]));new=dict(old)
 for alias,target in additions.items():assert alias.encode() not in old and target.encode() in old;new[alias.encode()]=old[target.encode()]
 fresh=api['trie'](new);assert api['entries'](fresh)==new
 b+=bytes(-len(b)%8);where=len(b);b+=fresh;struct.pack_into('<II',b,exports,where,len(fresh));fileoff=struct.unpack_from('<Q',b,linkedit+40)[0];filesize=len(b)-fileoff;struct.pack_into('<Q',b,linkedit+48,filesize);struct.pack_into('<Q',b,linkedit+32,(filesize+4095)&~4095)
 allowed=set(range(exports,exports+8))|set(range(linkedit+32,linkedit+40))|set(range(linkedit+48,linkedit+56));assert all(x==y or i in allowed for i,(x,y) in enumerate(zip(data,b)))
 return bytes(b),dict(original_exports_preserved=len(old),aliases=additions,allowed_header_bytes=sorted(allowed),all_other_original_bytes_preserved=True)
count=struct.unpack_from('>I',original,4)[0];parts=[]
for i in range(count):
 cpu,sub,off,n,align=struct.unpack_from('>IIIII',original,8+20*i);data=original[off:off+n];assert len(data)==n
 if cpu==0x1000007:data,change=update(data)
 else:change=dict(original_slice_bytes_preserved=True)
 parts.append((cpu,sub,data,align));rows.append(dict(cpu=cpu,subtype=sub,**change))
assert sum(cpu==0x1000007 for cpu,sub,data,align in parts)==1
output=bytearray(original[:8+count*20])
for i,(cpu,sub,data,align) in enumerate(parts):
 assert align<=20;output+=bytes(-len(output)% (1<<align));off=len(output);output+=data;struct.pack_into('>IIIII',output,8+20*i,cpu,sub,off,len(data),align)
folder=root/('runtime/pthread-alias-runtime-'+a.tag);report=root/('artifacts/private-procfs-pthread-alias-'+a.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir();guest=folder/'darling-root';subprocess.run(['cp','-a','--reflink=auto',str(base),str(guest)],check=True)
target=guest/'usr/lib/system/libsystem_pthread.dylib';target.write_bytes(output)
for key,item in parent['source_runtime'].items():
 dest=folder/Path(item['path']).name;shutil.copy2(root/item['path'],dest);parent['source_runtime'][key]=dict(path=str(dest.relative_to(root)),sha256=sha(dest));parent['files'][str(dest.relative_to(root))]=sha(dest)
parent['files'][str(target.relative_to(root))]=sha(target)
for name in [a.parent_stage,'scripts/stage-native-pthread-aliases.py','scripts/macho-named-reexport.py','vendor/darling/src/external/libpthread/src/CMakeLists.txt','vendor/darling/src/external/libpthread/xcodescripts/pthread.aliases']:parent['files'][name]=sha(root/name)
parent['system_version_binding']=str((guest/'System/Library/CoreServices/SystemVersion.plist').relative_to(root));parent['mtab']=str((guest/'private/etc/mtab').relative_to(root));parent['files'][parent['system_version_binding']]=sha(root/parent['system_version_binding']);parent['pthread_aliases']=dict(source=str(source.relative_to(root)),source_sha256=sha(source),library=str(target.relative_to(root)),library_sha256=sha(target),slices=rows,full_pthread_source_rebuild=False);parent['runtime_execution_verified']=False;parent['full_goal_complete']=False
report.write_text(json.dumps(parent,indent=2)+'\n');print(report.relative_to(root))
