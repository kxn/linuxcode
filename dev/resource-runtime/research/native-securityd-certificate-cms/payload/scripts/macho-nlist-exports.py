"""Expose requested existing nlist definitions; preserve all executable bytes."""
from pathlib import Path
import runpy,struct
h=runpy.run_path(str(Path(__file__).with_name('macho-named-reexport.py')))
def add(source,names):
    assert source[:8]==bytes.fromhex('cffaedfe07000001')
    at=32;sections=[];linkedit=export=table=None;base=None
    for _ in range(struct.unpack_from('<I',source,16)[0]):
        cmd,size=struct.unpack_from('<II',source,at)
        if cmd==0x19:
            segment=source[at+8:at+24].split(b'\0')[0]
            if segment==b'__TEXT':base=struct.unpack_from('<Q',source,at+24)[0]
            if segment==b'__LINKEDIT':linkedit=at
            for i in range(struct.unpack_from('<I',source,at+64)[0]):
                section=at+72+80*i;sections.append(struct.unpack_from('<I',source,section+64)[0]&255)
        elif cmd in (0x22,0x80000022):export=at+40
        elif cmd==0x80000033:export=at+8
        elif cmd==2:table=struct.unpack_from('<IIII',source,at+8)
        elif cmd==0x1d:raise ValueError('Refuse stale code signatures')
        at+=size
    assert None not in (linkedit,export,table,base)
    off,length=struct.unpack_from('<II',source,export);old=h['entries'](source[off:off+length]);new=dict(old)
    symoff,count,stroff,strsize=table;definitions={};wanted={n.encode() for n in names}-old.keys()
    for i in range(count):
        no,kind,section,desc,value=struct.unpack_from('<IBBHQ',source,symoff+16*i)
        if kind&0xe0 or kind&0x0e!=0x0e:continue
        assert no<strsize;zero=source.index(0,stroff+no,stroff+strsize);name=source[stroff+no:zero]
        if name not in wanted:continue
        assert 0<section<=len(sections) and sections[section-1] not in (8,0x10,0x11,0x12,0x13)
        flags=4 if desc&0x80 else 0;payload=h['uleb'](flags)+h['uleb'](value-base)
        assert name not in definitions or definitions[name]==payload,('ambiguous definition',name)
        definitions[name]=payload
    new.update(definitions);fresh=h['trie'](new);assert h['entries'](fresh)==new
    result=bytearray(source);result.extend(bytes(-len(result)%8));off=len(result);result.extend(fresh)
    struct.pack_into('<II',result,export,off,len(fresh));fileoff=struct.unpack_from('<Q',source,linkedit+40)[0];length=len(result)-fileoff
    struct.pack_into('<Q',result,linkedit+48,length);struct.pack_into('<Q',result,linkedit+32,(length+4095)&~4095)
    allowed=set(range(export,export+8))|set(range(linkedit+32,linkedit+40))|set(range(linkedit+48,linkedit+56))
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(source,result)))
    assert all(new[n]==v for n,v in old.items())
    return bytes(result),dict(added_names=sorted(n.decode() for n in definitions),missing_names=sorted(n.decode() for n in wanted-definitions.keys()),original_export_payloads_preserved=len(old),original_instructions_and_other_bytes_preserved=True)
