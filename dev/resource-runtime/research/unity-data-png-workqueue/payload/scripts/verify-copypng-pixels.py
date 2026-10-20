#!/usr/bin/env python3
"""Independently decode optimized PNG samples and compare every pixel."""
from pathlib import Path
import argparse,hashlib,json,struct,zlib
from PIL import Image,__version__ as pillow_version
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--probe-report',required=True);p.add_argument('--report',required=True);a=p.parse_args();dest=root/a.report;assert not dest.exists();probe=json.loads((root/a.probe_report).read_text());assert probe['verified'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def decode(path):
 data=path.read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n';at=8;chunks=[];compressed=b'';header=None
 while at<len(data):
  assert at+12<=len(data);size=struct.unpack_from('>I',data,at)[0];name=data[at+4:at+8];payload=data[at+8:at+8+size];assert at+12+size<=len(data);crc=struct.unpack_from('>I',data,at+8+size)[0];assert zlib.crc32(name+payload)&0xffffffff==crc;chunks.append(name.decode('ascii'))
  if name==b'IHDR':assert header is None;header=struct.unpack('>IIBBBBB',payload)
  if name==b'IDAT':compressed+=payload
  at+=12+size
 assert at==len(data) and chunks[-1]=='IEND' and header
 w,h,depth,color,compression,filtering,interlace=header;assert depth==8 and color in [2,6] and compression==filtering==interlace==0
 cgbi='CgBI' in chunks;bpp=4 if color==6 else 3;stride=w*bpp;raw=zlib.decompress(compressed,-15 if cgbi else 15);assert len(raw)==h*(stride+1);rows=[];prior=bytes(stride)
 for y in range(h):
  method=raw[y*(stride+1)];row=bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)]);assert method in range(5)
  for i in range(stride):
   left=row[i-bpp] if i>=bpp else 0;up=prior[i];corner=prior[i-bpp] if i>=bpp else 0
   if method==0:predict=0
   elif method==1:predict=left
   elif method==2:predict=up
   elif method==3:predict=(left+up)//2
   else:
    q=left+up-corner;dist=[abs(q-left),abs(q-up),abs(q-corner)];predict=[left,up,corner][dist.index(min(dist))]
   row[i]=(row[i]+predict)&255
  rows.append(bytes(row));prior=row
 pixels=[]
 for row in rows:
  for x in range(w):
   pixel=list(row[x*bpp:(x+1)*bpp]);alpha=pixel[3] if bpp==4 else 255;rgb=pixel[:3][::-1] if cgbi else pixel[:3];pixels.extend([*rgb,alpha])
 return (w,h),bytes(pixels),chunks,cgbi
cases=[]
for c in probe['cases']:
 source=root/c['source'];output=root/c['output'];assert sha(source)==c['source_sha256'] and sha(output)==c['output_sha256'];image=Image.open(source).convert('RGBA');expected=image.tobytes();size,pixels,chunks,cgbi=decode(output);assert size==image.size
 if cgbi:
  # Compare stored premultiplied RGB values without inventing colors for alpha0.
  expected=bytes(value if i%4==3 else (value*expected[i//4*4+3]+127)//255 for i,value in enumerate(expected))
 different=sum(x!=y for x,y in zip(expected,pixels));assert len(expected)==len(pixels);assert different==0,(c['source'],different,expected[:24],pixels[:24]);cases.append(dict(source=c['source'],output=c['output'],dimensions=size,pixels=len(pixels)//4,all_channels_equal=True,CgBI=cgbi,chunks=chunks,decoded_pixel_sha256=hashlib.sha256(pixels).hexdigest(),source_sha256=sha(source),output_sha256=sha(output)))
report=dict(verified=True,probe_report=a.probe_report,probe_report_sha256=sha(root/a.probe_report),cases=cases,total_pixels=sum(c['pixels'] for c in cases),Pillow_source_decoder_version=pillow_version,output_decoder='Independent bounded PNG chunk/CRC, deflate, filtering, channel-order decoder in this script',verifier_sha256=sha(Path(__file__)),all_tested_samples_opaque=True,full_UIKit_resource_correctness_proven=False,full_goal_complete=False);dest.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
