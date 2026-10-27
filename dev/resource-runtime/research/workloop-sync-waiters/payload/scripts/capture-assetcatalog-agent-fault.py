#!/usr/bin/env python3
"""Run only the original failed asset task and capture its simulator agent."""
from pathlib import Path
import argparse,hashlib,json,subprocess,time
r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for key in ['stage','configuration','build-log','stem']:p.add_argument('--'+key,required=True)
p.add_argument('--follow-spawn',action='store_true')
a=p.parse_args();assert all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
folder=r/'runtime'/a.stem;assert not folder.exists();folder.mkdir()
cmd=['python3','scripts/probe-original-assetcatalog.py','--stage',a.stage,'--configuration',a.configuration,'--build-log',a.build_log,'--timeout','180']
capture=None
with (folder/'probe.log').open('w') as out:
 probe=subprocess.Popen(cmd,cwd=r,stdout=out,stderr=subprocess.STDOUT);deadline=time.monotonic()+155
 while probe.poll() is None and time.monotonic()<deadline:
  pid=None
  for path in Path('/proc').glob('[0-9]*/cmdline'):
   try:argv=path.read_bytes().split(b'\0')
   except OSError:continue
   if (a.follow_spawn and argv[0].endswith(b'/ibtoold')) or (not a.follow_spawn and (argv[0].endswith(b'/AssetCatalogSimulatorAgent') or (argv[0].endswith(b'/mldr') and any(v.endswith(b'/AssetCatalogSimulatorAgent') for v in argv[1:])))):
    pid=int(path.parent.name);break
  if pid:
   stem=a.stem+'-agent';capture_cmd=['python3','scripts/capture-live-macho-fault.py','--pid',str(pid),'--stem',stem,'--timeout','100']
   if a.follow_spawn:
    selected=json.loads((r/a.stage).read_text())['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path'];kernel=r/selected
    nm=subprocess.check_output(['llvm-nm-19',str(kernel)],text=True);entry=int(next(l.split()[0] for l in nm.splitlines() if l.endswith(' _sys_posix_spawn')),16)
    while True:
     mappings=Path('/proc',str(pid),'maps').read_text().splitlines();region=next((l.split() for l in mappings if 'r-x' in l and l.endswith('/libsystem_kernel.dylib')),None)
     if region:break
     time.sleep(.005)
    address=int(region[0].split('-')[0],16)-int(region[2],16)+entry
    capture_cmd+=['--follow-spawn-suffix','/AssetCatalogSimulatorAgent','--spawn-entry',hex(address),'--spawn-entry-bytes',kernel.read_bytes()[entry:entry+16].hex()]
   capture=subprocess.run(capture_cmd,cwd=r,stdout=out,stderr=subprocess.STDOUT)
   capture=dict(pid=pid,driver_status=capture.returncode,report='runtime/'+stem+'/result.json');break
  time.sleep(.005)
 status=probe.wait(timeout=200)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
(folder/'result.json').write_text(json.dumps(dict(command=cmd,probe_status=status,capture=capture,tool_sha256=sha(Path(__file__)),files={str(f.relative_to(r)):sha(f) for f in folder.iterdir() if f.is_file()},full_goal_complete=False),indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
