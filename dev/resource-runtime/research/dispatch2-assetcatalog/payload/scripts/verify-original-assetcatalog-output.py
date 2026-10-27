#!/usr/bin/env python3
"""Independently bound-check the real CAR container and exported icon PNGs.

This validates container structure and PNG checksums, not CoreUI rendering.
"""
from pathlib import Path
import argparse, hashlib, json, plistlib, struct, zlib

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--probe-report',required=True)
p.add_argument('--report',required=True)
a=p.parse_args();destination=r/a.report;assert not destination.exists()
probe=r/a.probe_report;d=json.loads(probe.read_text())
assert d['verified'] and d['outer_status']==0 and d['native_statuses']==['0']
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((r/d['log']).read_bytes())==d['log_sha256']
car=next(r/n for n in d['products'] if n.endswith('/Assets.car'))
b=car.read_bytes();assert b[:8]==b'BOMStore'
version,used,index,index_size,variables,var_size=struct.unpack_from('>6I',b,8)
assert version==1 and index+index_size<=len(b) and variables+var_size<=len(b)
count=struct.unpack_from('>I',b,index)[0];assert 4+8*count<=index_size
blocks=[struct.unpack_from('>II',b,index+4+8*i) for i in range(count)]
assert sum(bool(size) for offset,size in blocks)==used
assert all(offset+size<=len(b) for offset,size in blocks)
def block(i):
 assert 0<i<count
 offset,size=blocks[i];assert size
 return b[offset:offset+size]
names={};n=struct.unpack_from('>I',b,variables)[0];cursor=variables+4
for i in range(n):
 ident,length=struct.unpack_from('>IB',b,cursor);cursor+=5
 assert cursor+length<=variables+var_size
 name=b[cursor:cursor+length].decode('ascii');cursor+=length
 assert name not in names;names[name]=ident;block(ident)
assert cursor==variables+var_size
assert {'CARHEADER','RENDITIONS','FACETKEYS','KEYFORMAT'}<=names.keys()
assert block(names['CARHEADER'])[:4]==b'RATC'
trees={}
for name,ident in names.items():
 data=block(ident)
 if data[:4]==b'tree':
  tree_version,root,node_size,entries=struct.unpack_from('>4I',data,4)
  assert tree_version==1 and node_size and entries and block(root)
  trees[name]=dict(root_block=root,node_size=node_size,entries=entries)
assert trees['RENDITIONS']['entries']>0
icons={}
for path in car.parent.glob('*.png'):
 data=path.read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
 at=8;types=[];dimensions=None
 while at<len(data):
  length=struct.unpack_from('>I',data,at)[0];kind=data[at+4:at+8];end=at+12+length
  assert end<=len(data) and zlib.crc32(data[at+4:at+8+length])==struct.unpack_from('>I',data,at+8+length)[0]
  if kind==b'IHDR':dimensions=struct.unpack_from('>II',data,at+8)
  types.append(kind.decode('ascii'));at=end
 assert at==len(data) and types[-1]=='IEND' and 'IDAT' in types
 assert types[0]=='IHDR' or types[:2]==['CgBI','IHDR']
 assert dimensions and all(dimensions)
 icons[path.name]=dict(dimensions=dimensions,size=len(data),sha256=sha(data),apple_CgBI=types[0]=='CgBI')
assert icons['AppIcon60x60@2x.png']['dimensions']==(120,120)
assert icons['AppIcon76x76@2x~ipad.png']['dimensions']==(152,152)
info=plistlib.loads((car.parent.parent/'partial-info.plist').read_bytes())
assert info['CFBundleIcons']['CFBundlePrimaryIcon']['CFBundleIconName']=='AppIcon'
record=dict(verified_container_and_exported_PNG_structure=True,original_actool_status=0,
 probe_report=a.probe_report,probe_report_sha256=sha(probe.read_bytes()),
 CAR=dict(path=str(car.relative_to(r)),size=len(b),sha256=sha(b),allocated_blocks=used,variables=names,trees=trees),
 exported_icons=icons,partial_info=info,independent_rendition_pixels_or_rendering_verified=False,
 full_App_build_verified=False,full_goal_complete=False,tool_sha256=sha(Path(__file__).read_bytes()))
destination.write_text(json.dumps(record,indent=2)+'\n');print('ORIGINAL_CAR_CONTAINER_AND_EXPORTED_ICONS_VERIFIED',destination)
