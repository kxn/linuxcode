#!/usr/bin/env python3
"""Capture the original nil NSData filename before exception handling."""
from pathlib import Path
import argparse,hashlib,json,subprocess,time,struct
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--stem',required=True);a=p.parse_args();assert a.stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
log=root/('logs/'+a.stem+'-driver.log');raw=root/('logs/'+a.stem+'.gdb.log');report=root/('artifacts/'+a.stem+'.json');assert not any(p.exists() for p in [log,raw,report]);capture=None
command=['python3','scripts/probe-direct-resource-tools.py','--configuration',a.configuration,'--stage',a.stage,'--tool','ibtool','--dvt-raw-backtraces']
path='runtime/foundation-native-framework-stage/Foundation.framework/Versions/C/Foundation';binary=(root/path).read_bytes();assert binary[:8]==bytes.fromhex('cffaedfe07000001');slice_start=0;entry=0x23d04;expected=binary[entry:entry+8].hex();suffix='/Foundation.framework/Versions/C/Foundation'

with log.open('w') as out:
 child=subprocess.Popen(command,cwd=root,stdout=out,stderr=subprocess.STDOUT);deadline=time.monotonic()+180;pid=None;base=None
 while child.poll() is None and time.monotonic()<deadline and pid is None:
  for q in Path('/proc').iterdir():
   if not q.name.isdigit():continue
   try:
    argv=(q/'cmdline').read_bytes().split(b'\0');names=[v.split()[0] for v in argv if v.split()]
    tools={b'/Applications/Xcode.app/Contents/Developer/usr/bin/ibtool',b'/Applications/Xcode.app/Contents/Developer/usr/bin/ibtoold'}
    if not names or (names[0] not in tools and not (names[0].endswith(b'/mldr') and tools.intersection(names))):continue
    current_maps=(q/'maps').read_text()
    if '/DVTFoundation.framework/Versions/A/DVTFoundation' not in current_maps:continue
    for line in current_maps.splitlines():
     fields=line.split(maxsplit=5)
     if len(fields)==6 and fields[5].endswith(suffix) and 'x' in fields[1]:base=int(fields[0].split('-')[0],16)-int(fields[2],16)+slice_start;pid=int(q.name);break
   except (OSError,IndexError):pass
  if pid is None:time.sleep(.005)
 if pid is not None:
  maps=root/('logs/'+a.stem+'.maps.log');code="import gdb\nassert int(gdb.parse_and_eval('$rip'))=="+str(base+entry)+" and int(gdb.parse_and_eval('$rdx'))==0\nprint('NIL_DATA_BREAKPOINT_OK')\n"+"""import gdb,struct
for thread in gdb.selected_inferior().threads():
 thread.switch();print('THREAD',thread.ptid);print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 frame=int(gdb.parse_and_eval('$rbp'))
 for i in range(60):
  try:following,pc=struct.unpack('<QQ',gdb.selected_inferior().read_memory(frame,16).tobytes())
  except Exception:break
  print('FRAME',hex(frame),hex(pc))
  if following<=frame or following>frame+0x100000:break
  frame=following
""";commands=['gdb','-q','-nx','-batch','-p',str(pid),'-ex','set pagination off','-ex','python assert gdb.selected_inferior().read_memory('+hex(base+entry)+',8).tobytes().hex()=='+repr(expected),'-ex','break *'+hex(base+entry),'-ex','condition 1 $rdx==0','-ex','continue','-ex','info registers','-ex','x/16gx $rsp','-ex','python exec('+repr(code)+')','-ex',"python open("+repr(str(maps))+",'w').write(open('/proc/"+str(pid)+"/maps').read())",'-ex','delete breakpoints','-ex','detach']
  try:g=subprocess.run(commands,cwd=root,capture_output=True,text=True,timeout=100)
  except subprocess.TimeoutExpired as e:
   decode=lambda x:x.decode(errors='replace') if isinstance(x,bytes) else x or '';g=subprocess.CompletedProcess(commands,124,decode(e.stdout),decode(e.stderr)+'\nGDB_OBSERVATION_TIMEOUT\n')
  raw.write_text(g.stdout+g.stderr);capture=dict(pid=pid,gdb_status=g.returncode,breakpoint_hit='NIL_DATA_BREAKPOINT_OK' in g.stdout,entry_runtime_address=hex(base+entry),original_entry_bytes=expected,gdb_log=str(raw.relative_to(root)),maps=str(maps.relative_to(root)) if maps.exists() else None)
 status=child.wait(timeout=240)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();report.write_text(json.dumps(dict(command=command,capture=capture,outer_status=status,log=str(log.relative_to(root)),log_sha256=sha(log),sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/path]}),indent=2)+'\n');print(report.relative_to(root));print(raw.read_text()[-7000:] if raw.exists() else 'No matching live DVT module')
