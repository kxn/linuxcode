#!/usr/bin/env python3
"""Recover numeric platform-version mapping metadata from a pinned Intel Apple dyld."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True);a=p.parse_args();src=Path(a.source);out=Path(a.output);report=Path(a.report);assert not out.exists() and not report.exists();b=src.read_bytes();assert b[:8]==bytes.fromhex('cffaedfe07000001');segments=[];at=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
 cmd,size=struct.unpack_from('<II',b,at);assert size>=8 and at+size<=len(b)
 if cmd==0x19:
  vm,vmsize,offset,filesize=struct.unpack_from('<4Q',b,at+24);assert offset+filesize<=len(b);segments.append((vm,offset,filesize))
 at+=size

def read(vm,n):
 for base,off,size in segments:
  if base<=vm and vm+n<=base+size:return b[off+vm-base:off+vm-base+n]
 raise ValueError('Unmapped address')

symbols=subprocess.check_output(['llvm-nm-19',str(src)],text=True);tables=[int(l.split()[0],16) for l in symbols.splitlines() if l.endswith(' __ZN5dyld3L11sVersionMapE')];assert len(tables)==2
function=next(int(l.split()[0],16) for l in symbols.splitlines() if 'APIs17mapFromVersionSetE' in l)
disassembly=subprocess.check_output(['llvm-objdump-19','-d','--start-address='+hex(function),'--stop-address='+hex(function+0x138),str(src)],text=True)
stride=int(re.search(r'addq\s+\$0x([0-9a-f]+), %r15',disassembly)[1],16);table_size=int(re.search(r'cmpq\s+\$0x([0-9a-f]+), %r15',disassembly)[1],16);assert stride==40 and table_size%stride==0 and table_size<=128*stride
assert hex(tables[0])[2:] in disassembly;data=read(tables[0],table_size);assert data==read(tables[1],table_size)
fields=['set','macos','ios','watchos','tvos','bridgeos'];rows=[]
for i in range(table_size//stride):
 values=struct.unpack_from('<10I',data,i*stride);assert values[-2:]==(0,0);rows.append(dict(zip(fields,values[:6])))
assert all(x['set']<y['set'] for x,y in zip(rows,rows[1:]));assert rows[0]==dict(set=0x7db0901,macos=0xa0700,ios=0x50000,watchos=0,tvos=0,bridgeos=0)
lines=['// Numeric release mapping metadata; no Apple executable instructions.','#ifndef DARLING_DYLD_VERSION_MAP_H','#define DARLING_DYLD_VERSION_MAP_H','#include <array>','#include <stdint.h>','namespace dyld3 {','struct DarlingVersionSetEntry {','    uint32_t set, macos, ios, watchos, tvos, bridgeos;','    bool operator<(uint32_t value) const { return set < value; }','};',f'static const std::array<DarlingVersionSetEntry, {len(rows)}> sDarlingVersionMap = {{{{']
lines += ['    { '+', '.join('0x%08x'%row[k] for k in fields)+' },' for row in rows];lines+=['}};','} // namespace dyld3','#endif'];out.parent.mkdir(parents=True,exist_ok=True);out.write_text('\n'.join(lines)+'\n')
report.write_text(json.dumps(dict(verified=True,source=str(src),source_sha256=hashlib.sha256(b).hexdigest(),table_vm_addresses=list(map(hex,tables)),table_sha256=hashlib.sha256(data).hexdigest(),table_stride=stride,table_entries=len(rows),two_compiled_tables_byte_equal=True,mapper_disassembly=disassembly,platform_order_confirmed_by_mapper=['macos','ios','watchos','tvos','bridgeos'],rows=rows,output=str(out),output_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),metadata_only=True,full_goal_complete=False),indent=2)+'\n');print('EXTRACTED_VERSION_SETS',len(rows))
