#!/usr/bin/env python3
"""Extract original full-system PlugInKit data with Apple aa under Darling."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,plistlib,runpy,shlex,subprocess,zipfile,zlib
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True);p.add_argument('--tag',required=True);a=p.parse_args()
assert a.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.tag)
folder=root/('runtime/fullsystem/pluginkit-resources-'+a.tag);report=root/('artifacts/fullsystem-pluginkit-resources-'+a.tag+'.json');assert not folder.exists() and not report.exists();folder.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
config=json.loads((root/'config/apple-installer-25G83.json').read_text());archive=next((root/'runtime/fullsystem/sharedsupport').rglob(config['mobileasset_zip_name']))
with archive.open('rb') as f:asset_sha=hashlib.file_digest(f,'sha256').hexdigest()
assert asset_sha==config['mobileasset_zip_sha256'];print('ASSET_SHA256_VERIFIED',asset_sha,flush=True)
prefix='System/Library/PrivateFrameworks/PlugInKit.framework/'
selected=lambda n:n.startswith(prefix)
links=[];current=None;chunks=[]
with zipfile.ZipFile(archive) as source:
 for line in source.read('AssetData/payloadv2/links.txt').decode().splitlines():
  if line.startswith('='):current=line[1:]
  elif line.startswith('+'):
   if selected(line[1:]):assert current is not None;links.append((current,line[1:]))
  else:raise ValueError('Unknown archive link record')
 for item in sorted(source.infolist(),key=lambda n:n.filename):
  if not item.filename.startswith('AssetData/payloadv2/payload.0'):continue
  name=Path(item.filename).name
  if len(name)!=11 or not name[-3:].isdigit():continue
  local=root/'runtime/fullsystem/payload-chunks'/name;assert local.stat().st_size==item.file_size
  crc=0
  with local.open('rb') as f:
   while block:=f.read(8*1024*1024):crc=zlib.crc32(block,crc)
  assert crc==item.CRC;chunks.append(dict(path=str(local.relative_to(root)),length=item.file_size,crc32=hex(crc)));print('PAYLOAD_CRC_VERIFIED',name,flush=True)
assert len(chunks)==53
extra=sorted({src for src,dst in links if not selected(src)})
for name in [prefix,*extra,*[x for pair in links for x in pair]]:assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
portable=folder/'archives';data=folder/'resources';portable.mkdir();data.mkdir()
aa=root/'runtime/recovery-tools/macOS Base System/usr/bin/aa';script=folder/'extract.sh'
library_paths=[root/('runtime/rebuilt-'+n) for n in ['apple-archive-original','parallel-compression','compression','der']]
lines=['#!/bin/bash','set -euo pipefail','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY','export DYLD_LIBRARY_PATH='+shlex.quote(':'.join(guest(n) for n in library_paths))+':"${DYLD_LIBRARY_PATH:-}"']
for item in chunks:
 path=root/item['path'];name=path.name;converted=portable/(name+'.aar')
 convert=[guest(aa),'convert','-i',guest(path),'-o',guest(converted)]
 for selected_path in [prefix.rstrip('/'),*extra]:convert+=['-include-path',selected_path]
 convert+=['-exclude-field','uid,gid,mod,flg,mtm,btm,ctm,atm','-a','raw','-t','2']
 lines += [shlex.join(convert)+' > '+shlex.quote(guest(portable/(name+'.convert.log')))+' 2>&1',
  'if [[ -s '+shlex.quote(guest(converted))+' ]]; then '+shlex.join([guest(aa),'extract','-i',guest(converted),'-d',guest(data),'-afsc','none','-t','2'])+' > '+shlex.quote(guest(portable/(name+'.extract.log')))+' 2>&1; fi',
  'printf "FULLSYSTEM_RESOURCE_CHUNK '+name+' OK\\n"']
script.write_text('\n'.join(lines)+'\n')
module=runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'));profile=module['profile'](stage=a.stage);env=module['environment'](profile)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='900';log=folder/'native.log'
record=dict(complete=False,source_asset_sha256=asset_sha,source_asset_sha256_verified=True,source_build=config['build'],payload_chunks=chunks,selected_prefix=prefix,auxiliary_link_sources=extra,hard_links=links,stage=a.stage,command=command,log=str(log.relative_to(root)),resource_directory=str(data.relative_to(root)),source_sha256=sha(Path(__file__)),aa_sha256=sha(aa),original_Apple_data=True,full_goal_complete=False)
report.write_text(json.dumps(record,indent=2)+'\n');print('NATIVE_EXTRACTION_START',report.relative_to(root),flush=True)
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
record.update(outer_status=result.returncode,log_sha256=sha(log));report.write_text(json.dumps(record,indent=2)+'\n');assert result.returncode==0,log
def safe(name):
 target=data/name;assert target.resolve().is_relative_to(data.resolve());return target
for src,dst in links:
 source,destination=safe(src),safe(dst);assert source.is_file() and not source.is_symlink();destination.parent.mkdir(parents=True,exist_ok=True)
 if destination.exists():assert destination.read_bytes()==source.read_bytes()
 else:os.link(source,destination)
files={};symlinks={}
for path in (data/prefix).rglob('*'):
 if path.is_symlink():assert path.resolve().is_relative_to(data.resolve());symlinks[str(path.relative_to(data))]=os.readlink(path)
 elif path.is_file():files[str(path.relative_to(data))]=dict(length=path.stat().st_size,sha256=sha(path))
info=safe(prefix+'Versions/A/Resources/Info.plist');metadata=plistlib.loads(info.read_bytes());assert metadata['CFBundleIdentifier']=='com.apple.pluginkit.framework'
record.update(complete=True,files=files,symlinks=symlinks,Info_plist=metadata,original_info_sha256=sha(info),scope='Original resource bytes only; no binary compatibility or signing claim.')
report.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(report=str(report.relative_to(root)),files=len(files),Info_plist=metadata),indent=2))
