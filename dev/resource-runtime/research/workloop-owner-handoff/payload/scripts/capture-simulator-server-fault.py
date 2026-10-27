#!/usr/bin/env python3
"""Capture the selected native server while the original Storyboard tool starts its services."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for name in ['stage','configuration','stem']:p.add_argument('--'+name,required=True)
p.add_argument('--probe-command-file')
a=p.parse_args();folder=root/'runtime'/a.stem;assert not folder.exists();folder.mkdir()
stage=json.loads((root/a.stage).read_text());server=root/stage['source_runtime']['LINUXCODE_DARLING_SERVER']['path'];identity=server.stat()
command=['python3','scripts/probe-original-storyboard.py','--stage',a.stage,'--configuration',a.configuration,'--with-disk-services','--trace-launch-jobs','--timeout','90']
if a.probe_command_file:
 command=json.loads((root/a.probe_command_file).read_text());assert isinstance(command,list) and command and all(isinstance(v,str) for v in command)
with (folder/'probe.log').open('w') as out:
 probe=subprocess.Popen(command,cwd=root,stdout=out,stderr=subprocess.STDOUT);pid=None;deadline=time.monotonic()+60
 while probe.poll() is None and time.monotonic()<deadline:
  for path in Path('/proc').glob('[0-9]*/exe'):
   try: current=path.stat()
   except OSError:continue
   if current.st_dev==identity.st_dev and current.st_ino==identity.st_ino:pid=int(path.parent.name);break
  if pid:break
  time.sleep(.005)
 capture=None
 if pid:
  (folder/'server.maps').write_text(Path(f'/proc/{pid}/maps').read_text())
  script=folder/'capture.gdb';script.write_text("set pagination off\nset confirm off\nset print thread-events off\nhandle SIGUSR1 SIGUSR2 SIGCHLD nostop noprint pass\nhandle SIGABRT SIGSEGV SIGILL stop print pass\ncontinue\np $_siginfo\nbt 35\npython\nf=gdb.newest_frame()\nwhile f:\n if f.name() and 'ipc_kmsg_set_prealloc' in f.name():\n  f.select()\n  for expression in ['kmsg','kmsg->ikm_size','kmsg->ikm_u','kmsg->ikm_header','sizeof(struct ipc_kmsg)']:\n   try: print('PREALLOC',expression,gdb.parse_and_eval(expression))\n   except Exception as e: print('PREALLOC_UNAVAILABLE',expression,str(e))\n  break\n f=f.older()\nend\nthread apply all bt 12\ndetach\n")
  with (folder/'server.gdb.log').open('w') as log:
   debugger=subprocess.Popen(['sudo','-n','gdb','-q','-nx','-batch',str(server),'-p',str(pid),'-x',str(script)],cwd=root,stdout=log,stderr=subprocess.STDOUT)
   try:capture=dict(pid=pid,status=debugger.wait(timeout=70))
   except subprocess.TimeoutExpired:
    tracer=int(next(l for l in Path(f'/proc/{pid}/status').read_text().splitlines() if l.startswith('TracerPid:')).split()[1])
    if tracer:
     argv=Path('/proc',str(tracer),'cmdline').read_bytes().split(b'\0');assert str(script).encode() in argv
     subprocess.run(['sudo','-n','kill','-INT',str(tracer)],check=True)
    capture=dict(pid=pid,timed_out=True,status=debugger.wait(timeout=15))
 status=probe.wait(timeout=150)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(command=command,probe_status=status,server=str(server.relative_to(root)),server_sha256=sha(server),capture=capture,files={str(p.relative_to(root)):sha(p) for p in folder.iterdir() if p.is_file()},tool_sha256=sha(Path(__file__)),full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',folder/'result.json')
