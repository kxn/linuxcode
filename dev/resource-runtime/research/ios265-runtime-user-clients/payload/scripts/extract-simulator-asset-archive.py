#!/usr/bin/env python3
"""Extract the main PBZX AppleArchive stream of a simulator asset on Linux."""
from pathlib import Path,PurePosixPath
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import argparse,hashlib,json,lzma,os,struct,time
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--records',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True);a=p.parse_args();src=Path(a.source);out=Path(a.output);report=Path(a.report);assert not out.exists() and not report.exists();out.mkdir(parents=True);started=time.monotonic();records=json.loads(Path(a.records).read_text());assert src.stat().st_size==records['file_size'];row=max((x for x in records['records'] if x['fields'].get('LBL')=='main' and x['fields'].get('YOP')==ord('E')),key=lambda x:x['fields']['DAT']);offset=row['offset']+row['header_size'];length=row['fields']['DAT'];end=offset+length

def exact(f,n):
 b=f.read(n)
 if len(b)!=n:raise ValueError('Truncated archive')
 return b

def decode(b,n):
 data=lzma.decompress(b) if b.startswith(b'\xfd7zXZ\0') else b
 if len(data)!=n:raise ValueError('PBZX expanded size mismatch')
 return data

def chunks():
 with src.open('rb') as f,ThreadPoolExecutor(max_workers=8) as pool:
  f.seek(offset);assert exact(f,4)==b'pbzx';limit=struct.unpack('>Q',exact(f,8))[0];assert 0<limit<=64*1024*1024;pending=deque()
  while f.tell()<end or pending:
   while f.tell()<end and len(pending)<16:
    expanded,packed=struct.unpack('>QQ',exact(f,16));assert expanded<=limit and packed<=end-f.tell() and packed<=64*1024*1024;pending.append(pool.submit(decode,exact(f,packed),expanded))
   yield pending.popleft().result()
  assert f.tell()==end

class Stream:
 def __init__(self):self.parts=iter(chunks());self.current=b'';self.at=0;self.total=0
 def read(self,n):
  pieces=[];need=n
  while need:
   if self.at==len(self.current):
    try:self.current=next(self.parts);self.at=0
    except StopIteration:break
   size=min(need,len(self.current)-self.at);pieces.append(self.current[self.at:self.at+size]);self.at+=size;need-=size
  b=b''.join(pieces);self.total+=len(b);return b
 def skip(self,n):
  while n:b=exact(self,min(n,1024*1024));n-=len(b)

def header_fields(b):
 values={};blobs=[];at=6
 while at<len(b):
  assert len(b)-at>=4;key=b[at:at+3].decode('ascii');kind=chr(b[at+3]);at+=4;assert key not in values
  if kind=='P':
   assert len(b)-at>=2;size=int.from_bytes(b[at:at+2],'little');at+=2;assert size<=len(b)-at;value=b[at:at+size].decode('utf-8');at+=size
  else:
   size={'*':0,'1':1,'2':2,'4':4,'8':8,'A':2,'B':4,'C':8,'F':4,'G':20,'H':32,'I':48,'J':64,'S':8,'T':12}[kind];assert size<=len(b)-at;value=int.from_bytes(b[at:at+size],'little');at+=size
   if kind in 'ABC':blobs.append((key,value))
  values[key]=value
 assert at==len(b);return values,blobs

s=Stream();files=[];seen=set()
while True:
 first=s.read(6)
 if not first:break
 assert len(first)==6 and first[:4] in [b'AA01',b'YAA1'];size=int.from_bytes(first[4:],'little');assert size>=6;values,blobs=header_fields(first+exact(s,size-6));name=values.get('PAT');kind=values.get('TYP');target=None
 if name:
  path=PurePosixPath(name);assert not path.is_absolute() and '..' not in path.parts and '\0' not in name and name not in seen;seen.add(name);target=out.joinpath(*path.parts);assert target.resolve().is_relative_to(out.resolve());target.parent.mkdir(parents=True,exist_ok=True)
  if kind==ord('D'):target.mkdir(exist_ok=True)
  elif kind==ord('L'):assert isinstance(values.get('LNK'),str);target.symlink_to(values['LNK'])
  elif kind!=ord('F'):raise ValueError('Unsupported AppleArchive entry type: '+str(kind))
 digest=None;file_size=0
 for key,size in blobs:
  if key=='DAT' and target and kind==ord('F'):
   h=hashlib.sha256()
   with target.open('xb') as f:
    remaining=size
    while remaining:
     b=exact(s,min(remaining,1024*1024));f.write(b);h.update(b);remaining-=len(b)
   digest=h.hexdigest();file_size=size
  else:s.skip(size)
 if target:
  if not target.is_symlink():target.chmod(values.get('MOD',0o755 if kind==ord('D') else 0o644)&0o777)
  files.append(dict(path=name,type=chr(kind),size=file_size,sha256=digest,fields=values));print('EXTRACTED',name,file_size,flush=True)
report.write_text(json.dumps(dict(verified=True,source=str(src),source_size=src.stat().st_size,main_offset=offset,main_packed_length=length,expanded_bytes=s.total,files=files,seconds=time.monotonic()-started,Linux_only=True,full_goal_complete=False),indent=2)+'\n');print('EVIDENCE',report,flush=True)
