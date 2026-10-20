#!/usr/bin/env python3
"""Identify the original DVT plugin instantiating NSApplication as its principal class."""
from pathlib import Path
import argparse,hashlib,json,subprocess,time,struct
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--stem',required=True);a=p.parse_args();assert a.stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
log=root/('logs/'+a.stem+'-driver.log');raw=root/('logs/'+a.stem+'.gdb.log');report=root/('artifacts/'+a.stem+'.json');assert not any(p.exists() for p in [log,raw,report]);capture=None
command=['python3','scripts/probe-direct-resource-tools.py','--configuration',a.configuration,'--stage',a.stage,'--tool','ibtool','--dvt-raw-backtraces']
path='runtime/state/prefix/Applications/Xcode.app/Contents/SharedFrameworks/DVTFoundation.framework/Versions/A/DVTFoundation';binary=(root/path).read_bytes();assert binary[:4]==bytes.fromhex('cafebabe');slices=[struct.unpack_from('>IIIII',binary,8+20*i) for i in range(struct.unpack_from('>I',binary,4)[0])];slice_start=next(x[2] for x in slices if x[0]==0x1000007);entry=0x185bd7;expected=binary[slice_start+entry:slice_start+entry+8].hex();suffix='/Applications/Xcode.app/Contents/SharedFrameworks/DVTFoundation.framework/Versions/A/DVTFoundation'

with log.open('w') as out:
 child=subprocess.Popen(command,cwd=root,stdout=out,stderr=subprocess.STDOUT);deadline=time.monotonic()+180;pid=None;base=None
 while child.poll() is None and time.monotonic()<deadline and pid is None:
  for q in Path('/proc').iterdir():
   if not q.name.isdigit():continue
   try:
    argv=(q/'cmdline').read_bytes().split(b'\0');names=[v.split()[0] for v in argv if v.split()]
    tools={b'/Applications/Xcode.app/Contents/Developer/usr/bin/ibtoold'}
    if not names or (names[0] not in tools and not (names[0].endswith(b'/mldr') and tools.intersection(names))):continue
    current_maps=(q/'maps').read_text()
    for line in current_maps.splitlines():
     fields=line.split(maxsplit=5)
     if len(fields)==6 and fields[5].endswith(suffix) and 'x' in fields[1]:base=int(fields[0].split('-')[0],16)-int(fields[2],16)+slice_start;pid=int(q.name);break
   except (OSError,IndexError):pass
  if pid is None:time.sleep(.005)
 if pid is not None:
  maps=root/('logs/'+a.stem+'.maps.log')
  helpers=(root/'scripts/gdb-dvt-assertion-arguments.py').read_text().split('regs={n:')[0].replace("'Error' in name or 'Bundle' in name","'Error' in name or 'Bundle' in name or 'PlugIn' in name")
  code=helpers+'\nDVT_BASE='+str(base)+'\n'+"""
class PrincipalBreakpoint(gdb.Breakpoint):
 def stop(self):
  try:
   plugin=int(gdb.parse_and_eval('$rdi'));principal=u64(plugin+0x78)
   name=class_info(principal)[2] if principal else 'nil'
   print('DVT_PLUGIN_PRINCIPAL_CLASS',hex(plugin),hex(principal),name,flush=True)
   if name!='NSApplication':return False
   object_info(plugin,'application-plugin');object_info(principal,'principal-class')
   handled=0
   while queue and handled<128:
    ptr,label=queue.pop(0);object_info(ptr,label);handled+=1
   print('DVT_NSAPPLICATION_PRINCIPAL_BREAKPOINT_OK',flush=True)
   return True
  except Exception as e:
   print('DVT_PLUGIN_PRINCIPAL_OBSERVATION_FAILED',str(e),flush=True)
   return True
PrincipalBreakpoint('*'+hex(DVT_BASE+0x185bd7))
"""
  commands=['gdb','-q','-nx','-batch','-p',str(pid),'-ex','set pagination off','-ex','python assert gdb.selected_inferior().read_memory('+hex(base+entry)+',8).tobytes().hex()=='+repr(expected),'-ex','python exec('+repr(code)+')','-ex','continue','-ex','info registers','-ex',"python open("+repr(str(maps))+",'w').write(open('/proc/"+str(pid)+"/maps').read())",'-ex','delete breakpoints','-ex','detach']
  try:g=subprocess.run(commands,cwd=root,capture_output=True,text=True,timeout=100)
  except subprocess.TimeoutExpired as e:
   decode=lambda x:x.decode(errors='replace') if isinstance(x,bytes) else x or '';g=subprocess.CompletedProcess(commands,124,decode(e.stdout),decode(e.stderr)+'\nGDB_OBSERVATION_TIMEOUT\n')
  raw.write_text(g.stdout+g.stderr);capture=dict(pid=pid,gdb_status=g.returncode,breakpoint_hit='DVT_NSAPPLICATION_PRINCIPAL_BREAKPOINT_OK' in g.stdout,entry_runtime_address=hex(base+entry),original_entry_bytes=expected,gdb_log=str(raw.relative_to(root)),maps=str(maps.relative_to(root)) if maps.exists() else None)
 status=child.wait(timeout=240)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();report.write_text(json.dumps(dict(command=command,capture=capture,outer_status=status,log=str(log.relative_to(root)),log_sha256=sha(log),sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/path]}),indent=2)+'\n');print(report.relative_to(root));print(raw.read_text()[-7000:] if raw.exists() else 'No matching live DVT module')
