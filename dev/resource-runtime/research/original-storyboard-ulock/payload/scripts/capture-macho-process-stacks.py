#!/usr/bin/env python3
"""Passively sample a live host PID's Mach-O registers,frame pointers and mappings."""
from pathlib import Path
import argparse,subprocess,json,hashlib
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True);p.add_argument('--stem',required=True);a=p.parse_args();assert a.pid>0 and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
f=root/'runtime'/a.stem;assert not f.exists();f.mkdir();maps=f/'process.maps'
code='''import gdb,struct
inf=gdb.selected_inferior()
for thread in inf.threads():
 thread.switch();print('THREAD',thread.ptid);print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 frame=int(gdb.parse_and_eval('$rbp'))
 for i in range(48):
  try: following,pc=struct.unpack('<QQ',inf.read_memory(frame,16).tobytes())
  except Exception:break
  print('FRAME',hex(frame),hex(pc))
  if following<=frame or following>frame+0x100000:break
  frame=following
'''
script=f/'sample.gdb';script.write_text('set pagination off\nset confirm off\nset print thread-events off\npython open('+repr(str(maps))+",'w').write(open('/proc/"+str(a.pid)+"/maps').read())\npython exec("+repr(code)+')\ndetach\n')
with (f/'process.gdb.log').open('w') as out:r=subprocess.run(['sudo','-n','gdb','-q','-nx','-batch','-p',str(a.pid),'-x',str(script)],stdout=out,stderr=subprocess.STDOUT,timeout=30)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();(f/'result.json').write_text(json.dumps(dict(pid=a.pid,gdb_status=r.returncode,passive_stack_sample=True,files={str(p.relative_to(root)):sha(p) for p in f.iterdir() if p.is_file()},tool_sha256=sha(Path(__file__)),full_goal_complete=False),indent=2)+'\n');print('SAMPLED',a.pid)
