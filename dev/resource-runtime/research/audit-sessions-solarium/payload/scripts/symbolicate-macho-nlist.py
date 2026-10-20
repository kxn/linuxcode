#!/usr/bin/env python3
"""Resolve captured Mach-O PCs from bounded nlist tables without decoding binds.

Symbolication is not image validation. In particular this does not turn an
LLVM bind-decoder failure into a successful format check.
"""
from pathlib import Path
import argparse,bisect,hashlib,json,struct
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stem',required=True);args=parser.parse_args()
assert args.stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.stem)
raw=root/('logs/'+args.stem+'.gdb.log');maps=root/('logs/'+args.stem+'.maps.log');regions=[];cache={};evidence={}
for line in maps.read_text().splitlines():
 p=line.split(maxsplit=5)
 if len(p)==6:
  a,b=(int(x,16) for x in p[0].split('-'));regions.append((a,b,int(p[2],16),p[5]))
def translate(name):
 for prefix,base in [('/workspace/',root),('/state/prefix/',root/'runtime/state/prefix'),('/usr/libexec/darling/',root/'runtime/rootfs/usr/libexec/darling')]:
  if name.startswith(prefix):return base/name[len(prefix):]
def symbols(path):
 if path in cache:return cache[path]
 data=path.read_bytes();offset=0;size=len(data)
 if data[:4]==b'\xca\xfe\xba\xbe':
  count=struct.unpack_from('>I',data,4)[0];assert 8+20*count<=len(data)
  matches=[struct.unpack_from('>IIIII',data,8+20*i) for i in range(count)]
  chosen=[row for row in matches if row[0]==0x1000007];assert len(chosen)==1;offset,size=chosen[0][2:4]
 assert offset+size<=len(data);d=data[offset:offset+size];assert d[:8]==bytes.fromhex('cffaedfe07000001')
 ncmds,cmdbytes=struct.unpack_from('<II',d,16);end=32+cmdbytes;assert end<=len(d);at=32;loads=[];table=None
 for _ in range(ncmds):
  assert at+8<=end;cmd,length=struct.unpack_from('<II',d,at);assert length>=8 and at+length<=end
  if cmd==0x19:
   assert length>=72;vm,vmsize,fileoff,filesize=struct.unpack_from('<QQQQ',d,at+24);assert fileoff+filesize<=len(d);loads.append((offset+fileoff,filesize,vm))
  if cmd==2:
   assert length==24 and table is None;table=struct.unpack_from('<IIII',d,at+8)
  at+=length
 assert at==end;sy=[]
 if table:
  symoff,count,stroff,strsize=table;assert symoff+16*count<=len(d) and stroff+strsize<=len(d)
  for i in range(count):
   no,kind,section,desc,value=struct.unpack_from('<IBBHQ',d,symoff+16*i)
   if kind&0xe0 or kind&0x0e!=0x0e:continue
   assert no<strsize;zero=d.find(b'\0',stroff+no,stroff+strsize);assert zero>=0
   sy.append((value,d[stroff+no:zero].decode('utf-8',errors='replace')))
 sy.sort();result=(loads,sy,[s[0] for s in sy]);cache[path]=result;evidence[str(path.relative_to(root))]=dict(sha256=hashlib.sha256(data).hexdigest(),slice_offset=offset,defined_nlist_symbols=len(sy));return result
out=[]
for line in raw.read_text().splitlines():
 if line.startswith(('PC ','FRAME ')):
  pc=int(line.split()[-1],16);region=next((x for x in regions if x[0]<=pc<x[1]),None)
  if region:
   a,b,off,name=region;fo=pc-a+off;line+=' '+name+' fileoff='+hex(fo);path=translate(name)
   if path and path.is_file():
    loads,sy,addresses=symbols(path);load=next((x for x in loads if x[0]<=fo<x[0]+x[1]),None)
    if load:
     vm=fo-load[0]+load[2];line+=' vmaddr='+hex(vm);index=bisect.bisect_right(addresses,vm)-1
     if index>=0:line+=' nearest_preceding_symbol='+sy[index][1]+'+'+hex(vm-sy[index][0])
 out.append(line)
output=root/('logs/'+args.stem+'.nlist-symbolicated.log');report=root/('artifacts/'+args.stem+'-nlist-symbolication.json');assert not output.exists() and not report.exists();output.write_text('\n'.join(out)+'\n');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();report.write_text(json.dumps(dict(symbolication_only=True,format_validation=False,raw=str(raw.relative_to(root)),raw_sha256=sha(raw),maps=str(maps.relative_to(root)),maps_sha256=sha(maps),output=str(output.relative_to(root)),output_sha256=sha(output),images=evidence),indent=2)+'\n');print(output.relative_to(root))
