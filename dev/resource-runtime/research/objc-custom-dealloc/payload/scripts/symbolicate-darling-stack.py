#!/usr/bin/env python3
"""Symbolicate a saved Linux Mach-O map, accounting for fat slices and segments."""
from pathlib import Path
import argparse,bisect,hashlib,json,re,struct,subprocess
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--stem',required=True);parser.add_argument('--runtime-report');args=parser.parse_args()
selected=json.loads((root/args.runtime_report).read_text()).get('source_runtime',{}) if args.runtime_report else {}
overrides={}
for key,name in [('LINUXCODE_LIBSYSTEM_KERNEL','libsystem_kernel.dylib'),('LINUXCODE_LIBXPC','libxpc.dylib'),('LINUXCODE_LIBDYLD','libdyld.dylib'),('LINUXCODE_SANDBOX','libsystem_sandbox.dylib')]:
 if key in selected:overrides['/state/prefix/usr/lib/system/'+name]=root/selected[key]['path']
raw=root/('logs/'+args.stem+'.gdb.log');maps=root/('logs/'+args.stem+'.maps.log');segments=[];cache={};evidence={}
for line in maps.read_text().splitlines():
 parts=line.split(maxsplit=5)
 if len(parts)!=6:continue
 a,b=[int(v,16) for v in parts[0].split('-')];segments.append((a,b,int(parts[2],16),parts[5]))
def translate(path):
 if path in overrides:return overrides[path]
 for prefix,base in [('/workspace/',root),('/state/prefix/',root/'runtime/state/prefix'),('/usr/libexec/darling/',root/'runtime/rootfs/usr/libexec/darling')]:
  if path.startswith(prefix):return base/path[len(prefix):]
 return None
def image(path):
 if str(path) in cache:return cache[str(path)]
 data=path.read_bytes();offset=0
 if data[:4]==b'\xca\xfe\xba\xbe':
  slices=[struct.unpack_from('>IIIII',data,8+20*i) for i in range(struct.unpack_from('>I',data,4)[0])]
  offset=next(a[2] for a in slices if a[0]==0x1000007)
 if data[offset:offset+4]!=b'\xcf\xfa\xed\xfe':raise ValueError('Not Mach-O')
 cursor=offset+32;load=[]
 for _ in range(struct.unpack_from('<I',data,offset+16)[0]):
  cmd,size=struct.unpack_from('<II',data,cursor)
  if cmd==0x19:
   addr,_,fileoff,filesize=struct.unpack_from('<QQQQ',data,cursor+24);load.append((offset+fileoff,filesize,addr))
  cursor+=size
 nm=subprocess.check_output(['llvm-nm-19',*(['--arch=x86_64'] if offset else []),'--numeric-sort',str(path)],text=True);symbols=[]
 for line in nm.splitlines():
  m=re.match(r'^([a-fA-F0-9]+)\s+\S\s+(.*)$',line)
  if m:symbols.append((int(m[1],16),m[2]))
 symbols.sort();result=(offset,load,symbols);cache[str(path)]=result;evidence[str(path.relative_to(root))]=hashlib.sha256(data).hexdigest();return result
out=[]
for line in raw.read_text().splitlines():
 if not line.startswith(('PC ','FRAME ')):out.append(line);continue
 pc=int(line.split()[-1],16);segment=next((s for s in segments if s[0]<=pc<s[1]),None)
 if not segment:out.append(line);continue
 a,b,off,name=segment;fileoff=pc-a+off;path=translate(name);note=''
 if path and path.is_file():
  try:
   sliceoff,loads,symbols=image(path);region=next((s for s in loads if s[0]<=fileoff<s[0]+s[1]),None)
   if region:
    vmaddr=fileoff-region[0]+region[2];index=bisect.bisect_right([x[0] for x in symbols],vmaddr)-1
    note=f' slice={sliceoff:#x} vmaddr={vmaddr:#x}'
    if index>=0:note+=' '+symbols[index][1]+'+'+hex(vmaddr-symbols[index][0])
  except (ValueError,StopIteration):pass
 out.append(line+' '+name+f' fileoff={fileoff:#x}'+note)
output=root/('logs/'+args.stem+'.macho-symbolicated.log');output.write_text('\n'.join(out)+'\n');digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(root/('artifacts/'+args.stem+'-symbolication.json')).write_text(json.dumps(dict(raw=str(raw.relative_to(root)),raw_sha256=digest(raw),maps=str(maps.relative_to(root)),maps_sha256=digest(maps),output=str(output.relative_to(root)),output_sha256=digest(output),images=evidence,original_execution=False,description='Saved real PC/frame addresses; correct x86_64 fat slice and Mach-O segment file-offset translation; symbol names locate functions, not causality.'),indent=2)+'\n');print(output)
