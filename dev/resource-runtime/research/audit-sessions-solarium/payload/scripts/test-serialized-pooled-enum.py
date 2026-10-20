#!/usr/bin/env python3
from pathlib import Path
import argparse,json,runpy,struct
p=argparse.ArgumentParser();p.add_argument('--target',required=True);p.add_argument('--output',required=True);args=p.parse_args()
r=Path(__file__).resolve().parent.parent;ns=runpy.run_path(str(r/'scripts/inspect-preserved-patch-got.py'));candidate=r/('runtime/rebuilt-'+args.target+'/AppKit');data=candidate.read_bytes();report=json.load(open(candidate.with_name('reconstruction.json')));original=(r/'runtime/fullsystem-libraries/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit').read_bytes();ns['inspect'](original,data,report);segs,_,streams=ns['macho'](data);row=report['byte_preserving_patch_got']['original_pooled_enum_indices'][0];base=0x7ff806da1000;slot=int(row['slot'],16)-base;literal=int(row['literal_address'],16)-base

def position(vm):
 i,s=next((i,s) for i,s in enumerate(segs) if s[1]<=vm<s[1]+s[4]);return i,s,s[3]+vm-s[1]
def uleb(n):
 out=bytearray()
 while n>=128:out.append((n&127)|128);n>>=7
 out.append(n);return bytes(out)
_,_,literal_off=position(literal);index,segment,slot_off=position(slot);controls=[]
for mode in ['wrong-enum-value','null-slot','missing-required-rebase','writable-literal','misaligned-linkedit']:
 d=bytearray(data)
 if mode=='wrong-enum-value':d[literal_off]^=1
 elif mode=='null-slot':struct.pack_into('<Q',d,slot_off,0)
 elif mode=='missing-required-rebase':
  before=uleb(slot-segment[1]);after=uleb(slot-segment[1]+8);assert len(before)==len(after);pattern=bytes([0x20|index])+before+b'\x51';start,length=streams[:2];stream=d[start:start+length];assert stream.count(pattern)==1;at=start+stream.index(pattern)+1;d[at:at+len(before)]=after
 elif mode=='writable-literal':
  at=32;found=False
  for _ in range(struct.unpack_from('<I',d,16)[0]):
   cmd,size=struct.unpack_from('<II',d,at)
   if cmd==0x19 and d[at+8:at+24].rstrip(b'\0')==b'__ENUM_LITERALS':struct.pack_into('<ii',d,at+56,3,3);found=True;break
   at+=size
  assert found
 else:
  at=32;found=False
  for _ in range(struct.unpack_from('<I',d,16)[0]):
   cmd,size=struct.unpack_from('<II',d,at)
   if cmd==0x19 and d[at+8:at+24].rstrip(b'\0')==b'__LINKEDIT':
    struct.pack_into('<Q',d,at+40,struct.unpack_from('<Q',d,at+40)[0]+4);found=True;break
   at+=size
  assert found
 try:ns['inspect'](original,bytes(d),report)
 except AssertionError:controls.append(dict(mode=mode,rejected=True))
 else:raise AssertionError(mode)
old=r/'runtime/rebuilt-appkit-patch-got-v2/AppKit';ns['inspect'](original,old.read_bytes(),json.load(open(old.with_name('reconstruction.json'))));p=r/args.output;assert not p.exists();p.write_text(json.dumps(dict(verified=True,candidate_positive=True,parent_without_feature_positive=True,actual_binary_negative_controls=controls,source_only=True,target=args.target),indent=2)+'\n');print('candidate + parent pass; 5 actual corrupted candidates rejected')
