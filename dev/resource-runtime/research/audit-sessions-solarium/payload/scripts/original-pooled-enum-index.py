"""Verify explicitly pinned RIP loads of original Swift enum-index pool cells."""
import struct

def validate(ns,image_path,records):
    image=ns['image'](image_path);result=[];seen=set()
    required={'symbol','provider','slot_offset','instruction_offset','instruction_bytes','literal_bytes'}
    for row in records:
        assert set(row)==required
        name,provider=row['symbol'],row['provider']
        assert name.startswith('_$s') and name.endswith('mFWC') and provider in image.dependencies
        owner=ns['image'](provider);entry=owner.exports[name]
        assert entry[0]=='address' and entry[2]==0
        assert [(n,v) for n,v in owner.exports.items() if v[0]=='address' and v[1]==entry[1]]==[(name,entry)]
        literal=bytes.fromhex(row['literal_bytes']);assert len(literal)==4 and struct.unpack('<I',literal)[0]<=65535
        assert ns['read'](entry[1],4)==literal
        assert any(start<=entry[1] and entry[1]+4<=start+size and not flags&0x80000400 for _,_,start,size,flags in owner.sections)
        instruction=image.base+int(row['instruction_offset'],0);code=bytes.fromhex(row['instruction_bytes']);assert len(code)==7 and code[:3]==b'\x48\x8b\x05'
        assert any(start<=instruction and instruction+7<=start+size and flags&0x80000400 for _,_,start,size,flags in image.sections)
        assert ns['read'](instruction,7)==code
        slot=image.base+int(row['slot_offset'],0);assert slot%8==0 and slot not in seen;seen.add(slot)
        assert instruction+7+struct.unpack_from('<i',code,3)[0]==slot
        assert not any(start<=slot<start+size for _,start,size,_,_ in image.segments)
        assert ns['pointer'](slot)==entry[1]
        result.append(dict(symbol=name,provider=provider,slot=hex(slot),instruction=hex(instruction),instruction_bytes=code.hex(),original_target=hex(entry[1]),original_encoded_slot=ns['read'](slot,8).hex(),literal_bytes=literal.hex()))
    return result
