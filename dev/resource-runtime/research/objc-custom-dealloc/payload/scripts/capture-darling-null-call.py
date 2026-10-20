#!/usr/bin/env python3
"""Capture live Mach-O frames and stack-top return addresses for null-call diagnosis."""
from pathlib import Path
import argparse,bisect,json,re,subprocess,posixpath
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--stem',default='foundation-coherent-xcode-stacks');parser.add_argument('--pid',type=int);parser.add_argument('--match',default='/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild');parser.add_argument('--wait-segv',action='store_true');parser.add_argument('--wait-signal',choices=['SIGSEGV','SIGILL','SIGABRT']);args=parser.parse_args();wait_signal=args.wait_signal or ('SIGSEGV' if args.wait_segv else None)
rows=subprocess.check_output(['ps','-eo','pid,args'],text=True).splitlines();pids=[row.split()[0] for row in rows if len(row.split(maxsplit=1))==2 and posixpath.normpath(row.split(maxsplit=1)[1].split()[0])==posixpath.normpath(args.match)]
if args.pid is not None:pids=[pid for pid in pids if int(pid)==args.pid]
if len(pids)!=1:raise SystemExit('Expected exactly one live process, found '+repr(pids))
pid=pids[0];maps=Path('/proc/'+pid+'/maps').read_text();code='''import gdb,struct
for t in gdb.selected_inferior().threads():
 t.switch();print('THREAD',t.ptid)
 print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 f=int(gdb.parse_and_eval('$rbp'))
 for i in range(45):
  try:n,pc=struct.unpack('<QQ',gdb.selected_inferior().read_memory(f,16).tobytes())
  except Exception:break
  print('FRAME',hex(f),hex(pc))
  if n<=f or n>f+0x100000:break
  f=n'''
gdb=['gdb','-q','-batch','-ex','set pagination off']
if wait_signal:gdb+=['-ex','handle '+wait_signal+' stop print nopass','-ex','continue','-ex','p $_siginfo','-ex','info registers','-ex','x/32gx $rsp','-ex','x/16i *(unsigned long*)$rsp-24','-ex','x/10i $rip','-ex',"python open("+repr(str(root/('logs/'+args.stem+'.maps.log')))+", 'w').write(open('/proc/"+pid+"/maps').read())"]
gdb+=['-ex','python exec('+repr(code)+')','-p',pid]
(root/('logs/'+args.stem+'.maps.log')).write_text(maps)
try:
 r=subprocess.run(gdb,capture_output=True,text=True,timeout=45 if wait_signal else 12)
except subprocess.TimeoutExpired as exc:
 def decode(v):return v.decode(errors='replace') if isinstance(v,bytes) else (v or '')
 r=subprocess.CompletedProcess(gdb,124,decode(exc.stdout),decode(exc.stderr)+'\nGDB_OBSERVATION_TIMEOUT; target state must be checked separately\n')
raw=r.stdout+r.stderr
if wait_signal:maps=(root/('logs/'+args.stem+'.maps.log')).read_text()
(root/('logs/'+args.stem+'.gdb.log')).write_text(raw);(root/('logs/'+args.stem+'.maps.log')).write_text(maps)
segments=[]
for line in maps.splitlines():
 parts=line.split(maxsplit=5)
 if len(parts)!=6:continue
 a,b=[int(x,16) for x in parts[0].split('-')];segments.append((a,b,int(parts[2],16),parts[5]))
def translate(path):
 for prefix,where in [('/workspace/',root),('/state/prefix/',root/'runtime/state/prefix'),('/usr/libexec/darling/',root/'runtime/rootfs/usr/libexec/darling')]:
  if path.startswith(prefix):return where/path[len(prefix):]
 return None
cache={};annotated=[]
for line in r.stdout.splitlines():
 if not line.startswith(('FRAME ','PC ')):annotated.append(line);continue
 address=int(line.split()[-1],16);segment=next((s for s in segments if s[0]<=address<s[1]),None)
 if not segment:annotated.append(line);continue
 a,b,off,path=segment;offset=address-a+off;file=translate(path);symbol=''
 if file and file.exists():
  key=str(file)
  if key not in cache:
   nm=subprocess.run(['llvm-nm-19','--numeric-sort',key],capture_output=True,text=True);symbols=[]
   for row in nm.stdout.splitlines():
    match=re.match(r'^([0-9a-fA-F]+)\s+\S\s+(.*)$',row)
    if match:symbols.append((int(match[1],16),match[2]))
   cache[key]=symbols
  symbols=cache[key];index=bisect.bisect_right([s[0] for s in symbols],offset)-1
  if index>=0:symbol=symbols[index][1]+'+'+hex(offset-symbols[index][0])
 annotated.append(line+' '+path+' fileoff='+hex(offset)+' '+symbol)
text='\n'.join(annotated)+'\n';(root/('logs/'+args.stem+'.annotated.log')).write_text(text);print(text[-18000:])
