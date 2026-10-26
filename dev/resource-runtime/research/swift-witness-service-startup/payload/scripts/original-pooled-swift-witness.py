"""Verify original RIP loads of uniquely exported Swift value witness tables."""
import struct

def validate(ns,image_path,records):
 image=ns['image'](image_path);rows=[];seen=set()
 for row in records:
  assert set(row)=={'symbol','provider','slot_offset','references','type_layout_bytes'}
  name,provider=row['symbol'],row['provider']
  assert name.startswith('_$s') and name.endswith('WV') and provider=='/usr/lib/swift/libswiftCore.dylib'
  assert image.dependencies.count(provider)==1
  owner=ns['image'](provider);entry=owner.exports[name];assert entry[0]=='address' and entry[2]==0
  assert [(n,v) for n,v in owner.exports.items() if v[0]=='address' and v[1]==entry[1]]==[(name,entry)],'Ambiguous witness identity'
  assert any(start<=entry[1] and entry[1]+88<=start+size and not flags&0x80000400 for _,_,start,size,flags in owner.sections)
  layout=bytes.fromhex(row['type_layout_bytes']);assert len(layout)==24 and ns['read'](entry[1]+64,24)==layout
  size,stride,flags,extra=struct.unpack('<QQII',layout);alignment=(flags&255)+1
  assert alignment&(alignment-1)==0 and size<=stride and stride>0 and stride%alignment==0
  assert size<1<<48 and stride<1<<48
  for index in range(8):
   function=ns['pointer'](entry[1]+8*index)
   assert any(start<=function<start+length and attrs&0x80000400 for _,_,start,length,attrs in owner.sections),'Witness function leaves original code'
  slot=image.base+int(row['slot_offset'],0);assert slot%8==0 and slot not in seen;seen.add(slot)
  assert not any(start<=slot<start+length for _,start,length,_,_ in image.segments)
  assert ns['pointer'](slot)==entry[1] and row['references']
  references=[];instructions=set()
  for ref in row['references']:
   assert set(ref)=={'offset','bytes'};instruction=image.base+int(ref['offset'],0);code=bytes.fromhex(ref['bytes'])
   assert instruction not in instructions;instructions.add(instruction)
   assert len(code)==7 and code[0] in (0x48,0x4c) and code[1]==0x8b and code[2]&0xc7==5
   assert any(start<=instruction and instruction+7<=start+length and attrs&0x80000400 for _,_,start,length,attrs in image.sections)
   assert ns['read'](instruction,7)==code and instruction+7+struct.unpack_from('<i',code,3)[0]==slot
   references.append(dict(instruction=hex(instruction),instruction_bytes=code.hex()))
  rows.append(dict(symbol=name,provider=provider,ordinal=image.dependencies.index(provider)+1,slot=hex(slot),original_target=hex(entry[1]),original_encoded_slot=ns['read'](slot,8).hex(),type_layout_bytes=layout.hex(),size=size,stride=stride,alignment=alignment,references=references))
 return rows
