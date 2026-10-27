#!/usr/bin/env python3
"""Capture a named Mach-O process during one explicit diagnostic command."""
from pathlib import Path
import argparse,hashlib,json,subprocess,time
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--command-file',required=True);p.add_argument('--match-suffix',required=True);p.add_argument('--stem',required=True);p.add_argument('--follow-spawn-suffix');p.add_argument('--stage');a=p.parse_args()
folder=r/'runtime'/a.stem;assert not folder.exists();folder.mkdir();cmd=json.loads((r/a.command_file).read_text());capture=None
with (folder/'probe.log').open('w') as out:
 probe=subprocess.Popen(cmd,cwd=r,stdout=out,stderr=subprocess.STDOUT);deadline=time.monotonic()+60
 while probe.poll() is None and time.monotonic()<deadline:
  pid=None
  for path in Path('/proc').glob('[0-9]*/cmdline'):
   try:argv=path.read_bytes().split(b'\0')
   except OSError:continue
   if argv[0].endswith(a.match_suffix.encode()) or (argv[0].endswith(b'/mldr') and any(v.endswith(a.match_suffix.encode()) for v in argv[1:])):
    pid=int(path.parent.name);break
  if pid:
   stem=a.stem+'-process';capture_cmd=['python3','scripts/capture-live-macho-fault.py','--pid',str(pid),'--stem',stem,'--timeout','100']
   if a.follow_spawn_suffix:
    assert a.stage
    kernel=r/json.loads((r/a.stage).read_text())['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path'];nm=subprocess.check_output(['llvm-nm-19',str(kernel)],text=True);entry=int(next(l.split()[0] for l in nm.splitlines() if l.endswith(' _sys_posix_spawn')),16)
    region=None;map_deadline=time.monotonic()+3
    while region is None and time.monotonic()<map_deadline:
     region=next((l.split() for l in Path('/proc',str(pid),'maps').read_text().splitlines() if 'r-x' in l and l.endswith('/libsystem_kernel.dylib')),None)
     if region is None:time.sleep(.005)
    assert region
    address=int(region[0].split('-')[0],16)-int(region[2],16)+entry
    capture_cmd+=['--follow-spawn-suffix',a.follow_spawn_suffix,'--spawn-entry',hex(address),'--spawn-entry-bytes',kernel.read_bytes()[entry:entry+16].hex(),'--follow-first-spawn-only']
   res=subprocess.run(capture_cmd,cwd=r,stdout=out,stderr=subprocess.STDOUT)
   capture=dict(pid=pid,driver_status=res.returncode,report='runtime/'+stem+'/result.json');break
  time.sleep(.002)
 status=probe.wait(timeout=660)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();(folder/'result.json').write_text(json.dumps(dict(command=cmd,probe_status=status,capture=capture,tool_sha256=sha(Path(__file__)),files={str(f.relative_to(r)):sha(f) for f in folder.iterdir() if f.is_file()},full_goal_complete=False),indent=2)+'\n');print('EVIDENCE',folder/'result.json')
