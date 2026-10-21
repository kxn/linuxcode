"""Verify an original Intel stub's symbol name, dependency ordinal and GOT target.

For shared-cache GOT slots absent from patch metadata, the original indirect
symbol table is independent evidence. Never choose a function by address alone.
"""
from pathlib import Path
import hashlib,struct

def verify(ns,image_path,target,slots,symbol,provider,library_root):
 path=Path(library_root)/image_path.lstrip('/');data=path.read_bytes()
 assert data[:8]==bytes.fromhex('cffaedfe07000001')
 image=ns['image'](image_path);assert provider in image.dependencies
 wanted={int(s,16) if isinstance(s,str) else s for s in slots};assert wanted and len(wanted)==len(slots)
 count,command_bytes=struct.unpack_from('<II',data,16);end=32+command_bytes;assert end<=len(data)
 at=32;stubs=[];symtab=None;indirect=None
 for _ in range(count):
  assert at+8<=end;cmd,length=struct.unpack_from('<II',data,at);assert length>=8 and at+length<=end
  if cmd==2:
   assert length==24 and symtab is None;symtab=struct.unpack_from('<4I',data,at+8)
  elif cmd==0xb:
   assert length==80 and indirect is None;indirect=struct.unpack_from('<2I',data,at+56)
  elif cmd==0x19:
   assert length>=72;nsect=struct.unpack_from('<I',data,at+64)[0];assert 72+80*nsect<=length
   for i in range(nsect):
    s=at+72+80*i;address,size=struct.unpack_from('<QQ',data,s+32);flags,reserved1,width=struct.unpack_from('<III',data,s+64)
    if flags&255==8:
     assert width==6 and size%width==0;stubs.append((address,size,reserved1))
  at+=length
 assert at==end and symtab and indirect
 symoff,nsyms,stroff,strsize=symtab;indoff,nind=indirect
 assert symoff+16*nsyms<=len(data) and stroff+strsize<=len(data) and indoff+4*nind<=len(data)
 rows=[]
 for start,size,first in stubs:
  assert first+size//6<=nind
  for i,address in enumerate(range(start,start+size,6)):
   code=ns['read'](address,6);assert code[:2]==b'\xff\x25'
   slot=address+6+struct.unpack_from('<i',code,2)[0]
   if slot not in wanted:continue
   index=struct.unpack_from('<I',data,indoff+4*(first+i))[0];assert index<nsyms
   no,kind,section,desc,value=struct.unpack_from('<IBBHQ',data,symoff+16*index)
   assert no<strsize and kind&0xe0==0 and kind&0xe==0 and kind&1 and not section and not value and not desc&0x40
   zero=data.find(b'\0',stroff+no,stroff+strsize);assert zero>=0
   name=data[stroff+no:zero].decode();ordinal=desc>>8
   assert name==symbol and ordinal==image.dependencies.index(provider)+1
   assert ns['pointer'](slot)==target==ns['resolve'](provider,symbol)
   rows.append(dict(stub=hex(address),stub_sha256=hashlib.sha256(code).hexdigest(),slot=hex(slot),symbol_index=index,symbol=name,ordinal=ordinal,provider=provider,target=hex(target)))
 assert rows and {int(row['slot'],16) for row in rows}==wanted
 return dict(kind='original-indirect-symbol-and-stub-GOT',selected=[symbol,provider],target=hex(target),slots=[hex(s) for s in sorted(wanted)],stubs=rows,original_file_sha256={image_path:hashlib.sha256(data).hexdigest(),provider:hashlib.sha256((Path(library_root)/provider.lstrip('/')).read_bytes()).hexdigest()})
