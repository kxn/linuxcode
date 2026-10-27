#!/usr/bin/env python3
"""Capture a selected live Mach-O process's next fault or final exit syscall."""
from pathlib import Path
import argparse,json,hashlib,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True);p.add_argument('--stem',required=True);p.add_argument('--timeout',type=int,default=60);p.add_argument('--catch-exit',action='store_true',help='Expensive: ptrace syscall tracing; off for normal startup')
a=p.parse_args();assert a.pid>0 and 1<=a.timeout<=180 and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
folder=root/'runtime'/a.stem;assert not folder.exists();folder.mkdir()
maps=folder/'process.maps';log=folder/'process.gdb.log'
code='''import gdb,struct
inf=gdb.selected_inferior()
for thread in inf.threads():
 thread.switch();print('THREAD',thread.ptid);print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 frame=int(gdb.parse_and_eval('$rbp'))
 for i in range(60):
  try:following,pc=struct.unpack('<QQ',inf.read_memory(frame,16).tobytes())
  except Exception:break
  print('FRAME',hex(frame),hex(pc))
  if following<=frame or following>frame+0x100000:break
  frame=following
'''
script=folder/'capture.gdb';script.write_text('set pagination off\nset confirm off\nset print thread-events off\nhandle SIGUSR1 SIGUSR2 SIGPWR nostop noprint pass\nhandle SIGSEGV SIGILL SIGABRT stop print pass\n'+('catch syscall exit_group\n' if a.catch_exit else '')+'continue\np $_siginfo\ninfo registers\nx/12i $rip\nx/20gx $rsp\npython open('+repr(str(maps))+",'w').write(open('/proc/"+str(a.pid)+"/maps').read())\npython exec("+repr(code)+')\ndetach\n')
timed_out=False
with log.open('w') as out:
 debugger=subprocess.Popen(['sudo','-n','gdb','-q','-nx','-batch','-p',str(a.pid),'-x',str(script)],stdout=out,stderr=subprocess.STDOUT)
 try:status=debugger.wait(timeout=a.timeout)
 except subprocess.TimeoutExpired:
  timed_out=True
  # Killing only sudo can orphan root gdb and leave its inferior stopped.
  # Interrupt the exact tracer so the remaining script saves and detaches.
  target=Path('/proc')/str(a.pid)/'status'
  if target.exists():
   tracer=int(next(l for l in target.read_text().splitlines() if l.startswith('TracerPid:')).split()[1])
   if tracer:
    tracer_cmd=(Path('/proc')/str(tracer)/'cmdline').read_bytes().split(b'\0')
    assert tracer_cmd[0].endswith(b'/gdb') or tracer_cmd[0]==b'gdb'
    assert str(script).encode() in tracer_cmd
    subprocess.run(['sudo','-n','kill','-INT',str(tracer)],check=True)
  status=debugger.wait(timeout=15)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
(folder/'result.json').write_text(json.dumps(dict(pid=a.pid,gdb_status=status,timed_out=timed_out,files={str(f.relative_to(root)):sha(f) for f in folder.iterdir() if f.is_file()},tool_sha256=sha(Path(__file__)),full_goal_complete=False),indent=2)+'\n')
print('EVIDENCE',folder/'result.json');print(log.read_text()[-1500:])
