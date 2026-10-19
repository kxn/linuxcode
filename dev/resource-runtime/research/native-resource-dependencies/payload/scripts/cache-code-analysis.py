#!/usr/bin/env python3
"""Analysis-only function boundaries and verified tail jump tables in x86 code.

Synthetic labels come exclusively from Apple's LC_FUNCTION_STARTS. The source
image is unchanged. The output is an objdump input, never a runnable library.
Assembler-authored entries can also name data; these are not proof of code.
"""
from bisect import bisect_right
from pathlib import Path
import re
import struct
import subprocess
import sys

def reference_with_function_labels(source, destination):
    data=bytearray(Path(source).read_bytes())
    cursor=32;section_index=0;text_sections=[];linkedit=symtab=dysymtab=starts=None
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,cursor)
        if command==0x19:
            segment=data[cursor+8:cursor+24].split(b'\0')[0]
            if segment==b'__TEXT':base=struct.unpack_from('<Q',data,cursor+24)[0]
            if segment==b'__LINKEDIT':linkedit=cursor
            for index in range(struct.unpack_from('<I',data,cursor+64)[0]):
                section_index+=1;at=cursor+72+80*index
                name=data[at:at+16].split(b'\0')[0]
                address,length=struct.unpack_from('<QQ',data,at+32)
                flags=struct.unpack_from('<I',data,at+64)[0]
                if flags&0x80000400:text_sections.append((address,address+length,section_index,name))
        elif command==2:symtab=cursor
        elif command==0xb:dysymtab=cursor
        elif command==0x26:starts=struct.unpack_from('<II',data,cursor+8)
        cursor+=size
    if None in (linkedit,symtab,dysymtab,starts):raise ValueError('Missing function/symbol metadata')
    offset,length=starts;payload=data[offset:offset+length];position=0;address=base;functions=[]
    while position<len(payload):
        shift=value=0
        while True:
            byte=payload[position];position+=1;value|=(byte&127)<<shift
            if byte<128:break
            shift+=7
            if shift>63:raise ValueError('Invalid function-start ULEB')
        if value==0:
            if any(payload[position:]):raise ValueError('Unexpected function-start trailer')
            break
        address+=value
        matches=[section for first,last,section,_ in text_sections if first<=address<last]
        if len(matches)!=1:raise ValueError('Function entry is not in one instruction section')
        functions.append((address,matches[0]))
    if not functions:raise ValueError('No original function entry records')
    symbols=bytearray();strings=bytearray(b'\0')
    for address,section in functions:
        name=f'L_linuxcode_function_{address:x}'.encode()+b'\0'
        symbols+=struct.pack('<IBBHQ',len(strings),0xe,section,0,address)
        strings+=name
    data+=bytes(-len(data)%8)
    symbol_offset=len(data);data+=symbols
    string_offset=len(data);data+=strings
    struct.pack_into('<IIII',data,symtab+8,symbol_offset,len(functions),string_offset,len(strings))
    # Replace the analysis symbol table completely; there are no stubs to name
    # through the original indirect-symbol indexes in this analysis copy.
    struct.pack_into('<18I',data,dysymtab+8,0,len(functions),len(functions),0,len(functions),0,*([0]*12))
    fileoff=struct.unpack_from('<Q',data,linkedit+40)[0]
    filesize=len(data)-fileoff
    struct.pack_into('<Q',data,linkedit+32,(filesize+4095)&~4095)
    struct.pack_into('<Q',data,linkedit+48,filesize)
    Path(destination).write_bytes(data)
    return [address for address,_ in functions]

def parse_instructions(disassembly):
    instructions={}
    for line in disassembly.splitlines():
        match=re.match(r'^([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)',line)
        if match:instructions[int(match[1],16)]=(bytes.fromhex(match[2]),match[3])
    return instructions

def validated_constant_ranges(disassembly,records,base,read):
    """Validate explicitly pinned vector literals by their real load readers."""
    import hashlib
    dependency=Path(__file__).resolve().parent.parent/'runtime/tools/python-capstone'
    sys.path.insert(0,str(dependency))
    import capstone as cs
    from capstone import x86_const as x
    if not Path(cs._cs._name).resolve().is_relative_to(dependency.resolve()):
        raise ValueError('Constant analysis must use the pinned project-local decoder')
    decoder=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_64);decoder.detail=True
    instructions=parse_instructions(disassembly);result=[]
    for record in records:
        start=base+int(record['offset'],0);end=start+record['length']
        if hashlib.sha256(read(start,end-start)).hexdigest()!=record['sha256']:
            raise ValueError('Pinned code-section constant bytes changed')
        covered=set()
        for reader in record['readers']:
            address=base+int(reader,0);encoded,_=instructions[address]
            item=next(decoder.disasm(encoded,address,count=1),None)
            if item is None or item.size!=len(encoded) or item.mnemonic not in ('movaps','vmovaps'):
                raise ValueError('Expected an original aligned vector-load instruction')
            operands=item.operands
            if len(operands)!=2 or operands[0].type!=x.X86_OP_REG or operands[1].type!=x.X86_OP_MEM:
                raise ValueError('Unexpected constant-reader operands')
            memory=operands[1].mem;operand=operands[1]
            if memory.base!=x.X86_REG_RIP or memory.index or memory.segment or operand.access!=cs.CS_AC_READ:
                raise ValueError('Constant reader is not a plain RIP-relative read')
            target=address+item.size+memory.disp
            if operand.size not in (16,32) or not start<=target<target+operand.size<=end:
                raise ValueError('Constant load exceeds its pinned data range')
            covered.update(range(target,target+operand.size))
        if covered!=set(range(start,end)):raise ValueError('Constant loads do not cover the complete pinned range')
        result.append({'start':start,'end':end,'readers':record['readers'],'sha256':record['sha256']})
    for address,(_,operand) in instructions.items():
        if any(r['start']<=address<r['end'] for r in result):continue
        branch=re.search(r'\b(?:callq?|jmpq?|j\w+)\s+(0x[0-9a-f]+)',operand)
        if branch and any(r['start']<=int(branch[1],16)<r['end'] for r in result):
            raise ValueError('A direct code branch enters a pinned constant range')
    return result

def tail_jump_tables(disassembly,functions,read,diagnostics=None):
    instructions=parse_instructions(disassembly);tables={};candidates={}
    dependency=Path(__file__).resolve().parent.parent/'runtime/tools/python-capstone'
    sys.path.insert(0,str(dependency))
    import capstone as cs
    from capstone import x86_const as x
    if not Path(cs._cs._name).resolve().is_relative_to(dependency.resolve()):
        raise ValueError('Analysis must use the pinned project-local Capstone library')
    decoder=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_64);decoder.detail=True
    decoded={}
    def decode(address):
        if address not in decoded:
            encoded,_=instructions[address]
            item=next(decoder.disasm(encoded,address,count=1),None)
            if item is None or item.size!=len(encoded):raise KeyError(address)
            decoded[address]=item
        return decoded[address]
    aliases={}
    for family in (('rax','eax','ax','al','ah'),('rbx','ebx','bx','bl','bh'),
            ('rcx','ecx','cx','cl','ch'),('rdx','edx','dx','dl','dh'),
            ('rsi','esi','si','sil'),('rdi','edi','di','dil'),
            ('rbp','ebp','bp','bpl'),('rsp','esp','sp','spl')):
        for name in family:aliases[name]=family[0]
    def root(register):
        name=decoder.reg_name(register) or ''
        if name in aliases:return aliases[name]
        match=re.fullmatch(r'(r\d+)(?:d|w|b)?',name)
        if match:return match[1]
        match=re.fullmatch(r'(?:xmm|ymm|zmm)(\d+)',name)
        return 'vector'+match[1] if match else name
    def location(operand):
        if operand.size!=8:return None
        if operand.type==x.X86_OP_REG:return ('reg',root(operand.reg))
        if operand.type==x.X86_OP_MEM:
            memory=operand.mem
            if not memory.segment and not memory.index and root(memory.base) in ('rbp','rsp'):
                return ('mem',root(memory.base),memory.disp)
        return None
    def barrier(item):
        return (any(item.group(group) for group in (cs.CS_GRP_CALL,cs.CS_GRP_RET,cs.CS_GRP_INT,cs.CS_GRP_IRET))
            or item.mnemonic in ('syscall','sysenter','vmcall','vmmcall','hlt','ud2'))
    def propagate(item,tracked):
        # Track exact 64-bit copies. Every reported register write kills its
        # aliases; potentially aliasing stores kill saved memory values.
        operands=item.operands;copied=None
        if item.id in (x.X86_INS_MOV,x.X86_INS_MOVABS,x.X86_INS_MOVQ) and len(operands)==2:
            if location(operands[1]) in tracked:copied=location(operands[0])
        for operand in operands:
            if operand.type!=x.X86_OP_MEM or not operand.access&cs.CS_AC_WRITE:continue
            memory=operand.mem
            base=root(memory.base) if not memory.segment and not memory.index else None
            kept=set()
            for value in tracked:
                if value[0]!='mem':kept.add(value);continue
                if base==value[1] and operand.size and not (
                        memory.disp<value[2]+8 and value[2]<memory.disp+operand.size):
                    kept.add(value)
            tracked=kept
        # PUSH/ENTER have implicit memory writes absent from the operand list.
        if item.mnemonic.startswith(('push','enter')):
            tracked={value for value in tracked if value[0]!='mem'}
        _,writes=item.regs_access();written={root(register) for register in writes}
        tracked={value for value in tracked if value[1] not in written}
        if copied is not None:tracked.add(copied)
        return tracked
    def dispatch_follows(address,target_register,function_start,table):
        tracked={('reg',root(target_register))};visited=set()
        address+=decode(address).size
        for _ in range(32):
            if address in visited or not function_start<=address<table:return None
            visited.add(address);item=decode(address);operands=item.operands
            if item.group(cs.CS_GRP_JUMP):
                if item.id!=x.X86_INS_JMP or len(operands)!=1:return None
                if operands[0].type==x.X86_OP_IMM:
                    address=operands[0].imm;continue
                return max(visited) if location(operands[0]) in tracked else None
            if barrier(item):return None
            tracked=propagate(item,tracked)
            if not tracked:return None
            address+=item.size
        return None
    def table_loads(address,base_register,function_start,table):
        # Optimized C++ hoists the table base out of a loop. Follow real
        # control-flow edges while preserving exact base provenance, instead
        # of imposing an adjacency requirement on LEA and MOVSXD.
        pending=[(address+decode(address).size,frozenset({('reg',root(base_register))}))]
        visited=set();budget=4096
        while pending and budget:
            cursor,frozen=pending.pop();state=(cursor,frozen)
            if state in visited or not function_start<=cursor<table:continue
            visited.add(state);budget-=1
            try:trial=decode(cursor)
            except KeyError:continue
            operands=trial.operands;bases=set(frozen)
            if trial.group(cs.CS_GRP_CALL):
                # Darwin x86_64 calls preserve these integer registers.
                # An unknown callee may write memory and all caller-saved
                # registers, so no stack cell or vector value survives it.
                preserved={'rbx','rbp','rsp','r12','r13','r14','r15'}
                bases={value for value in bases if value[0]=='reg' and value[1] in preserved}
                if bases:pending.append((cursor+trial.size,frozenset(bases)))
                continue
            if barrier(trial):continue
            if trial.group(cs.CS_GRP_JUMP):
                if len(operands)!=1 or operands[0].type!=x.X86_OP_IMM:continue
                pending.append((operands[0].imm,frozen))
                if trial.id!=x.X86_INS_JMP:pending.append((cursor+trial.size,frozen))
                continue
            if trial.id==x.X86_INS_MOVSXD and len(operands)==2 and operands[0].type==x.X86_OP_REG and operands[0].size==8 and operands[1].type==x.X86_OP_MEM:
                memory=operands[1].mem
                if trial.addr_size==8 and ('reg',root(memory.base)) in bases and memory.index and memory.scale==4 and not memory.disp and not memory.segment:
                    remaining=propagate(trial,bases)
                    if remaining:yield trial,remaining
                    continue
            bases=propagate(trial,bases)
            if bases:pending.append((cursor+trial.size,frozenset(bases)))
    def padding(data):
        # Intel's canonical multi-byte NOP forms, plus INT3 padding.
        bases=[bytes.fromhex(value) for value in (
            '90','0f 1f 00','0f 1f 40 00','0f 1f 44 00 00',
            '0f 1f 80 00 00 00 00','0f 1f 84 00 00 00 00 00')]
        # LLVM pads up to the x86 15-byte instruction limit with repeated
        # operand-size prefixes and an optional CS prefix, e.g. the 12-byte
        # 66 66 66 2e 0f 1f 84 00 00 00 00 00 form.
        nops=[b'\xcc']
        for base in bases:
            for segment_prefix in (b'',b'\x2e'):
                for count in range(16-len(base)-len(segment_prefix)):
                    nops.append(b'\x66'*count+segment_prefix+base)
        while data:
            found=next((value for value in sorted(nops,key=len,reverse=True) if data.startswith(value)),None)
            if found is None:return False
            data=data[len(found):]
        return True
    for address,(code,operand) in instructions.items():
        if not operand.startswith('leaq') or '(%rip)' not in operand:continue
        try:item=decode(address)
        except KeyError:continue
        operands=item.operands
        if item.id!=x.X86_INS_LEA or len(operands)!=2 or operands[0].type!=x.X86_OP_REG or operands[1].type!=x.X86_OP_MEM:continue
        memory=operands[1].mem
        if memory.base!=x.X86_REG_RIP or memory.index or memory.segment:continue
        base_register=operands[0].reg;table=address+item.size+memory.disp
        index=bisect_right(functions,address)-1
        if index<0 or index+1>=len(functions):continue
        start,end=functions[index:index+2]
        if not start<=address<table<end:continue
        dispatch_max=None
        try:
            for move,bases in table_loads(address,base_register,start,table):
                offsets={('reg',root(move.operands[0].reg))};cursor=move.address+move.size;add=None
                for _ in range(8):
                    trial=decode(cursor);operands=trial.operands
                    if barrier(trial) or trial.group(cs.CS_GRP_JUMP):break
                    if trial.id==x.X86_INS_ADD and len(operands)==2 and all(op.type==x.X86_OP_REG and op.size==8 for op in operands):
                        left,right=(location(op) for op in operands)
                        if (left in bases and right in offsets) or (right in bases and left in offsets):
                            add=trial;target_register=operands[0].reg;break
                    elif trial.id==x.X86_INS_LEA and len(operands)==2 and operands[0].type==x.X86_OP_REG and operands[0].size==8 and operands[1].type==x.X86_OP_MEM:
                        memory=operands[1].mem
                        left,right=('reg',root(memory.base)),('reg',root(memory.index))
                        if trial.addr_size==8 and memory.scale==1 and not memory.disp and not memory.segment and (
                                (left in bases and right in offsets) or (right in bases and left in offsets)):
                            add=trial;target_register=operands[0].reg;break
                    bases=propagate(trial,bases);offsets=propagate(trial,offsets)
                    if not bases or not offsets:break
                    cursor+=trial.size
                if add is None:continue
                dispatch_max=dispatch_follows(add.address,target_register,start,table)
                if dispatch_max is None:continue
                break
        except KeyError:continue
        if dispatch_max is None:continue
        candidates[table]={'function':start,'function_end':end,'instruction':address,'dispatch_max':dispatch_max}
    families={}
    if diagnostics is not None:diagnostics['candidates']=candidates
    for table,record in sorted(candidates.items()):families.setdefault(record['function'],[]).append(table)
    for function,bases in families.items():
        verified={};first=bases[0]
        # LLVM can place several relative tables together at a function's tail.
        # Bound each by the next semantically identified table, then the next
        # LC_FUNCTION_STARTS entry. All cases must lead back into real code
        # before the entire table family; accept the family only as a whole.
        for index,table in enumerate(bases):
            record=candidates[table]
            if max(record['instruction'],record['dispatch_max'])>=first:break
            end=bases[index+1] if index+1<len(bases) else record['function_end']
            targets=[];cursor=table
            while cursor+4<=end:
                target=table+struct.unpack('<i',read(cursor,4))[0]
                if not function<=target<first or target not in instructions:break
                targets.append(target);cursor+=4
            if len(targets)<2 or not padding(read(cursor,end-cursor)):break
            verified[table]={'start':table,'end':end,'entries':len(targets),'function':function,'targets':targets}
        if len(verified)==len(bases):tables.update(verified)
    ordered=sorted(tables.values(),key=lambda table:table['start'])
    starts=[table['start'] for table in ordered]
    def inside_table(address):
        index=bisect_right(starts,address)-1
        return index>=0 and address<ordered[index]['end']
    for address,(_,operand) in instructions.items():
        if inside_table(address):continue
        branch=re.search(r'\b(?:callq?|jmpq?|j\w+)\s+(0x[0-9a-f]+)',operand)
        if branch and inside_table(int(branch[1],16)):
            raise ValueError('A direct code branch enters a proposed data table')
    return list(tables.values())
