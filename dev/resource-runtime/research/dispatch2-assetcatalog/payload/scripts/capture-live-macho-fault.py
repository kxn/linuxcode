#!/usr/bin/env python3
"""Capture a selected live Mach-O process's next fault or final exit syscall."""
from pathlib import Path
import argparse,json,hashlib,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True);p.add_argument('--stem',required=True);p.add_argument('--timeout',type=int,default=60);p.add_argument('--catch-exit',action='store_true',help='Expensive: ptrace syscall tracing; off for normal startup');p.add_argument('--follow-spawn-suffix');p.add_argument('--spawn-entry',type=lambda v:int(v,0));p.add_argument('--spawn-entry-bytes')
a=p.parse_args();assert a.pid>0 and 1<=a.timeout<=180 and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
folder=root/'runtime'/a.stem;assert not folder.exists();folder.mkdir()
maps=folder/'process.maps';log=folder/'process.gdb.log'
code='''import gdb,struct,json
inf=gdb.selected_inferior()
start=int(gdb.parse_and_eval('$rsp'));chunks=[]
for offset in range(0,16384,256):
 try:chunks.append({'address':start+offset,'hex':inf.read_memory(start+offset,256).tobytes().hex()})
 except Exception:break
open(STACK_PATH,'w').write(json.dumps(chunks))
for thread in inf.threads():
 thread.switch();print('THREAD',thread.ptid);print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 frame=int(gdb.parse_and_eval('$rbp'))
 for i in range(60):
  try:following,pc=struct.unpack('<QQ',inf.read_memory(frame,16).tobytes())
  except Exception:break
  print('FRAME',hex(frame),hex(pc))
  if following<=frame or following>frame+0x100000:break
  frame=following
'''.replace('STACK_PATH',repr(str(folder/'fault-stack.json')))
setup=''
if a.follow_spawn_suffix:
 assert a.spawn_entry and a.spawn_entry_bytes
 bpcode='''import gdb
assert gdb.selected_inferior().read_memory(ENTRY,16).tobytes()==bytes.fromhex(EXPECTED)
class TargetSpawn(gdb.Breakpoint):
 def stop(self):
  try:path=gdb.selected_inferior().read_memory(int(gdb.parse_and_eval('$rsi')),1024).tobytes().split(b'\\0',1)[0]
  except Exception:return False
  print('OBSERVED_SPAWN',path)
  if path.endswith(SUFFIX):
   print('FOLLOWING_TARGET_SPAWN',path)
   gdb.execute('set follow-fork-mode child')
   self.enabled=False
  return False
TargetSpawn('*'+hex(ENTRY))
'''.replace('ENTRY',str(a.spawn_entry)).replace('EXPECTED',repr(a.spawn_entry_bytes)).replace('SUFFIX',repr(a.follow_spawn_suffix.encode()))
 setup='python exec('+repr(bpcode)+')\n'
script=folder/'capture.gdb';script.write_text('set pagination off\nset confirm off\nset print thread-events off\nhandle SIGUSR1 SIGUSR2 SIGPWR nostop noprint pass\nhandle SIGSEGV SIGILL SIGABRT stop print pass\n'+setup+('catch syscall exit_group\n' if a.catch_exit else '')+'continue\np $_siginfo\ninfo registers\nx/12i $rip\nx/20gx $rsp\npython print("CAPTURED_HOST_PID",gdb.selected_inferior().pid)\npython open('+repr(str(maps))+",'w').write(open('/proc/'+str(gdb.selected_inferior().pid)+'/maps').read())\npython exec("+repr(code)+')\ndetach\n')
timed_out=False
with log.open('w') as out:
 debugger=subprocess.Popen(['sudo','-n','gdb','-q','-nx','-batch','-p',str(a.pid),'-x',str(script)],stdout=out,stderr=subprocess.STDOUT)
 try:status=debugger.wait(timeout=a.timeout)
 except subprocess.TimeoutExpired:
  timed_out=True
  # Killing only sudo can orphan root gdb and leave its inferior stopped.
  # Interrupt the exact tracer so the remaining script saves and detaches.
  for target in Path('/proc').glob('[0-9]*/cmdline'):
   try:tracer_cmd=target.read_bytes().split(b'\0')
   except OSError:continue
   if (tracer_cmd[0].endswith(b'/gdb') or tracer_cmd[0]==b'gdb') and str(script).encode() in tracer_cmd:
    subprocess.run(['sudo','-n','kill','-INT',target.parent.name],check=True)
  status=debugger.wait(timeout=15)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
(folder/'result.json').write_text(json.dumps(dict(pid=a.pid,gdb_status=status,timed_out=timed_out,files={str(f.relative_to(root)):sha(f) for f in folder.iterdir() if f.is_file()},tool_sha256=sha(Path(__file__)),full_goal_complete=False),indent=2)+'\n')
print('EVIDENCE',folder/'result.json');print(log.read_text()[-1500:])
