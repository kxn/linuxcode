#!/usr/bin/env python3
"""Run only the original failed asset task and capture its simulator agent."""
from pathlib import Path
import argparse,hashlib,json,subprocess,time
r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for key in ['stage','configuration','build-log','stem']:p.add_argument('--'+key,required=True)
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
   if argv[0].endswith(b'/AssetCatalogSimulatorAgent') or (argv[0].endswith(b'/mldr') and any(v.endswith(b'/AssetCatalogSimulatorAgent') for v in argv[1:])):
    pid=int(path.parent.name);break
  if pid:
   stem=a.stem+'-agent';capture=subprocess.run(['python3','scripts/capture-live-macho-fault.py','--pid',str(pid),'--stem',stem,'--timeout','60'],cwd=r,stdout=out,stderr=subprocess.STDOUT)
   capture=dict(pid=pid,driver_status=capture.returncode,report='runtime/'+stem+'/result.json');break
  time.sleep(.005)
 status=probe.wait(timeout=200)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
(folder/'result.json').write_text(json.dumps(dict(command=cmd,probe_status=status,capture=capture,tool_sha256=sha(Path(__file__)),files={str(f.relative_to(r)):sha(f) for f in folder.iterdir() if f.is_file()},full_goal_complete=False),indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
