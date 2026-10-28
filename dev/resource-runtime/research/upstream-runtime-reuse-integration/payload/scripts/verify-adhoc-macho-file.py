#!/usr/bin/env python3
"""Independently verify embedded ad-hoc Mach-O signatures, including FAT slices."""
from pathlib import Path
import hashlib,struct
def verify(path):
 data=Path(path).read_bytes();slices=[(0,0,0,len(data))]
 if data[:4]==bytes.fromhex('cafebabe'):
  count=struct.unpack_from('>I',data,4)[0];assert 0<count<32 and 8+20*count<=len(data)
  slices=[struct.unpack_from('>IIIII',data,8+20*i)[:4] for i in range(count)]
 results=[]
 for cpu,sub,base,size in slices:
  assert base<=len(data) and size<=len(data)-base;binary=data[base:base+size];assert binary[:4]==bytes.fromhex('cffaedfe');at=32;signature=None;info=None
  for i in range(struct.unpack_from('<I',binary,16)[0]):
   kind,length=struct.unpack_from('<II',binary,at);assert length>=8 and length<=len(binary)-at
   if kind==29:
    assert signature is None;start,length2=struct.unpack_from('<II',binary,at+8);assert start<=len(binary) and length2<=len(binary)-start;signature=binary[start:start+length2]
   if kind==25:
    count=struct.unpack_from('<I',binary,at+64)[0];assert 72+80*count<=length
    for j in range(count):
     sec=struct.unpack_from('<16s16sQQIIIIIIII',binary,at+72+80*j)
     if sec[0].rstrip(b'\0')==b'__info_plist' and sec[1].rstrip(b'\0')==b'__TEXT':
      assert info is None and sec[4]<=len(binary) and sec[3]<=len(binary)-sec[4];info=binary[sec[4]:sec[4]+sec[3]]
   at+=length
  assert signature is not None;magic,length,count=struct.unpack_from('>III',signature);assert magic==0xfade0cc0 and 12+8*count<=length<=len(signature);blobs={};ranges=[]
  for i in range(count):
   slot,offset=struct.unpack_from('>II',signature,12+i*8);assert slot not in blobs and offset>=12+8*count and offset+8<=length
   n=struct.unpack_from('>I',signature,offset+4)[0];assert n>=8 and n<=length-offset
   assert all(offset>=b or offset+n<=a for a,b in ranges);ranges.append((offset,offset+n));blobs[slot]=signature[offset:offset+n]
  assert blobs.get(65536,b'') in [b'',bytes.fromhex('fade0b0100000008')]
  directories=[(slot,b) for slot,b in blobs.items() if slot==0 or 4096<=slot<4101];assert directories
  for slot,cd in directories:
   magic,length,version,flags,hashat,identifier,special,pages,limit=struct.unpack_from('>9I',cd);hs,ht,platform,power=struct.unpack_from('>4B',cd,36)
   assert magic==0xfade0c02 and length==len(cd) and flags&2 and version<=0x20600 and limit==start and 1<=power<=20
   algorithm={1:'sha1',2:'sha256',3:'sha256',4:'sha384'}[ht];assert hs==({1:20,2:32,3:20,4:48}[ht]);page=1<<power;assert pages==(limit+page-1)//page and special*hs<=hashat and pages*hs<=len(cd)-hashat
   digest=lambda b:hashlib.new(algorithm,b).digest()[:hs]
   for i in range(pages):assert digest(binary[i*page:min((i+1)*page,limit)])==cd[hashat+i*hs:hashat+(i+1)*hs],'code page mismatch'
   for i in range(1,special+1):
    expected=cd[hashat-i*hs:hashat-(i-1)*hs]
    if not any(expected):continue
    if i==1:assert info is not None and digest(info)==expected,'embedded Info.plist mismatch'
    else:
     assert i in [2,5,7] and i in blobs,'unsupported external special slot'
     assert digest(blobs[i])==expected,'special slot mismatch'
   label=cd[identifier:cd.index(0,identifier)].decode();results.append(dict(cpu=cpu,subtype=sub,slot=slot,identifier=label,code_pages=pages,special_slots=special,hash_algorithm=algorithm))
 return dict(verified=True,directories=results,ad_hoc_only=True,platform_identity_verified=False)
if __name__=='__main__':
 import argparse,json
 p=argparse.ArgumentParser();p.add_argument('path');a=p.parse_args();print(json.dumps(verify(a.path),indent=2))
