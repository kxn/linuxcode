"""Verify the exact original pooled Swift Any type-storage reference."""
import struct

def validate(ns,image_path,records):
    image=ns['image'](image_path);result=[];seen=set()
    for row in records:
        assert set(row)=={'symbol','provider','slot_offset','instruction_offset','instruction_bytes'}
        name,provider=row['symbol'],row['provider']
        assert name=='_$sypN' and provider=='/usr/lib/swift/libswiftCore.dylib'
        assert image.dependencies.count(provider)==1
        owner=ns['image'](provider);entry=owner.exports[name]
        assert entry[0]=='address' and entry[2]==0
        assert [(n,v) for n,v in owner.exports.items() if v[0]=='address' and v[1]==entry[1]]==[(name,entry)]
        assert any(start<=entry[1] and entry[1]+24<=start+size and not flags&0x80000400 for _,_,start,size,flags in owner.sections)
        assert ns['read'](entry[1]+8,8)==struct.pack('<Q',0x303)
        instruction=image.base+int(row['instruction_offset'],0);code=bytes.fromhex(row['instruction_bytes'])
        assert len(code)==11 and code[:3]==b'\x48\x8b\x35' and code[7:]==b'\x48\x83\xc6\x08'
        assert any(start<=instruction and instruction+11<=start+size and flags&0x80000400 for _,_,start,size,flags in image.sections)
        assert ns['read'](instruction,11)==code
        slot=image.base+int(row['slot_offset'],0);assert slot%8==0 and slot not in seen;seen.add(slot)
        assert instruction+7+struct.unpack_from('<i',code,3)[0]==slot
        assert not any(start<=slot<start+size for _,start,size,_,_ in image.segments)
        assert ns['pointer'](slot)==entry[1]
        result.append(dict(symbol=name,provider=provider,ordinal=image.dependencies.index(provider)+1,slot=hex(slot),instruction=hex(instruction),instruction_bytes=code.hex(),original_target=hex(entry[1]),original_encoded_slot=ns['read'](slot,8).hex(),metadata_header_addend=8,metadata_kind=0x303))
    return result
