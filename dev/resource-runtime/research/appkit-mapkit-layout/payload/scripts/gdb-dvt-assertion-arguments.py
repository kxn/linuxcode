"""Read a stopped x86_64 DVT assertion's arguments; never call inferior code."""
import gdb,json,re,struct
inferior=gdb.selected_inferior()
def memory(p,n):
    if not p or n<0 or n>16384:raise ValueError('bounded read')
    return inferior.read_memory(p,n).tobytes()
def u64(p):return struct.unpack('<Q',memory(p,8))[0]
def cstring(p,limit=512):
    out=bytearray()
    for i in range(limit):
        b=memory(p+i,1)[0]
        if not b:break
        if b<32 or b>126:raise ValueError('not an ASCII string')
        out.append(b)
    return out.decode()
def class_info(obj):
    isa=u64(obj);isa=(isa&0x00007ffffffffff8) if isa&1 else isa
    data=u64(isa+32)&0x00007ffffffffff8
    flags=struct.unpack('<I',memory(data,4))[0]
    ro=u64(data+8) if flags&0x80000000 else data
    if ro&1:ro=u64(ro&~1)
    name=cstring(u64(ro+24),192)
    if not re.fullmatch(r'[A-Za-z_$0-9.]+',name):raise ValueError('not a class name')
    return isa,ro,name
queue=[];seen=set()
def object_info(p,label):
    if p in seen:return
    seen.add(p)
    try:isa,ro,name=class_info(p)
    except Exception:
        try:print('DVT_CSTRING',label,hex(p),repr(cstring(p)))
        except Exception:pass
        return
    record=dict(label=label,address=hex(p),class_name=name)
    if 'String' in name:
        try:
            flags=struct.unpack('<I',memory(p+8,4))[0]&255
            inline=(flags&0x60)==0;explicit=(flags&5)!=4
            text=p+16+(8 if explicit else 0) if inline else u64(p+16)
            length=u64(p+16 if inline else p+24) if explicit else memory(text,1)[0]
            if flags&4:text+=1
            if length<=4096:
                record['text']=memory(text,length*(2 if flags&16 else 1)).decode('utf-16-le' if flags&16 else 'utf-8',errors='replace')
        except Exception:pass
    if 'Error' in name or 'Bundle' in name:
        fields={};current=isa
        for _ in range(6):
            if not current:break
            try:
                data=u64(current+32)&0x00007ffffffffff8;flags=struct.unpack('<I',memory(data,4))[0];base=u64(data+8) if flags&0x80000000 else data
                if base&1:base=u64(base&~1)
                ivars=u64(base+48)
                if ivars:
                    stride,count=struct.unpack('<II',memory(ivars,8));stride&=0xfffffffc
                    if stride<32 or stride>64 or count>128:break
                    for i in range(count):
                        at=ivars+8+i*stride;offset=struct.unpack('<i',memory(u64(at),4))[0]
                        field=cstring(u64(at+8),128);kind=cstring(u64(at+16),128)
                        if offset<0 or offset>4096:continue
                        value=u64(p+offset);fields[field]=dict(type=kind,value=hex(value))
                        if kind.startswith('@') and value:queue.append((value,label+'.'+field))
                current=u64(current+8)
            except Exception:break
        record['ivars']=fields
    if name=='__NSDictionaryI':
        try:
            header=u64(p+8);count=header&((1<<57)-1);record['dictionary_header']=hex(header)
            if count<=32:
                for i in range(2*count):
                    value=u64(p+16+8*i)
                    if value:queue.append((value,label+'.raw-slot-'+str(i)))
        except Exception:pass
    print('DVT_OBJECT',json.dumps(record,ensure_ascii=False))
regs={n:int(gdb.parse_and_eval('$'+n)) for n in ['rdi','rsi','rdx','rcx','r8','r9','rsp','rbp','rip']}
print('DVT_ASSERTION_REGISTERS',json.dumps({k:hex(v) for k,v in regs.items()}))
print('DVT_ASSERTION_LINE',regs['r9'])
try:print('DVT_ASSERTION_SELECTOR',cstring(regs['rdx']))
except Exception:pass
for ptr,label in [(regs['rcx'],'object'),(regs['r8'],'filename'),(u64(regs['rsp']+8),'signature'),(u64(regs['rsp']+16),'message-format')]:object_info(ptr,label)
try:
    va=u64(regs['rsp']+24);gp,fp,overflow,save=struct.unpack('<IIQQ',memory(va,24));print('DVT_VA_LIST',hex(va),gp,fp,hex(overflow),hex(save))
    for i in range(8):
        if gp<48:arg=u64(save+gp);gp+=8
        else:arg=u64(overflow);overflow+=8
        object_info(arg,'argument-'+str(i))
except Exception as e:print('DVT_VA_LIST_READ_FAILED',str(e))
handled=0
while queue and handled<96:
    p,label=queue.pop(0);object_info(p,label);handled+=1
