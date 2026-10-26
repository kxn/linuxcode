#!/usr/bin/env python3
"""Inspect outer AppleArchive records without reading their large payloads."""
from pathlib import Path
import argparse,json,struct
cli=argparse.ArgumentParser(description=__doc__);cli.add_argument("--source",required=True);cli.add_argument("--report",required=True);args=cli.parse_args()
p=Path(args.source);f=p.open('rb');total=p.stat().st_size;records=[]
while f.tell()<total:
 pos=f.tell();first=f.read(6);assert first[:4] in [b'AA01',b'YAA1'],(pos,first)
 size=struct.unpack_from('<H',first,4)[0];assert size>=6;header=first+f.read(size-6);at=6;values={};blobs=[]
 while at<size:
  key=header[at:at+3].decode();typ=chr(header[at+3]);at+=4
  if typ=='P':length=struct.unpack_from('<H',header,at)[0];at+=2;v=header[at:at+length].decode();at+=length
  else:
   length={'*':0,'1':1,'2':2,'4':4,'8':8,'A':2,'B':4,'C':8,'F':4,'G':20,'H':32,'I':48,'J':64,'S':8,'T':12}[typ];v=int.from_bytes(header[at:at+length],'little');at+=length
   if typ in 'ABC':blobs.append((key,v))
  values[key]=v
 assert at==size;body=sum(v for k,v in blobs);assert pos+size+body<=total;(records.append(dict(offset=pos,header_size=size,fields=values,blobs=blobs)));print(pos,values)
 f.seek(body,1)
assert f.tell()==total
out=Path(args.report);assert not out.exists();out.write_text(json.dumps(dict(records=records,file_size=total,full_goal_complete=False),indent=2)+'\n')
