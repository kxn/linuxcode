#!/usr/bin/env python3
"""Exercise the actual source CF2launch_data converter in native Darling."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);a=p.parse_args()
data=json.loads((r/a.build).read_text());sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
for n,h in data['files'].items():resolve(n,h)
assert sha(r/data['native_test'])==data['native_test_sha256']
w=Path(tempfile.mkdtemp(prefix='launchctl-long-strings-',dir=r/'runtime'))
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage='artifacts/private-procfs-auditsession83-stage.json',configuration='config/direct-resource-tool-environment-v150.json')
cmd=profile['command'][:-2]+['/Volumes/SystemRoot/workspace/'+data['native_test']];cmd[3]='60'
with (w/'run.log').open('w') as out:res=subprocess.run(cmd,cwd=r,env=m['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=(w/'run.log').read_text();counts=re.findall(r'^LAUNCHCTL_LONG_STRINGS_OK (\d+)$',text,re.M);ok=res.returncode==0 and len(counts)==1
record=dict(verified=ok,outer_status=res.returncode,native_checks=counts,build=a.build,build_sha256=sha(r/a.build),log=str((w/'run.log').relative_to(r)),log_sha256=sha(w/'run.log'),driver_sha256=sha(Path(__file__)),actual_full_source_CF2launch_data_called=True)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3000:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
