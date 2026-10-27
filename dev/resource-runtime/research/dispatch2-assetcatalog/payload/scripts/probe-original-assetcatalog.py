#!/usr/bin/env python3
"""Reproduce the exact Unity asset-catalog task with fresh private outputs."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--stage',required=True);p.add_argument('--configuration',required=True)
p.add_argument('--build-log',required=True);p.add_argument('--timeout',type=int,default=180)
a=p.parse_args();assert 30<=a.timeout<=600
folder=Path(tempfile.mkdtemp(prefix='original-assetcatalog-',dir=root/'runtime'))
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
guest=lambda f:'/Volumes/SystemRoot/workspace/'+str(f.relative_to(root))
lines=(root/a.build_log).read_text().splitlines()
matches=[lines[i+2].strip() for i,l in enumerate(lines) if l.startswith('CompileAssetCatalogVariant thinned ')]
assert len(matches)==1
argv=shlex.split(matches[0]);original_argv=list(argv)
assert argv[0]=='/Applications/Xcode.app/Contents/Developer/usr/bin/actool'
for flag,name in [('--compile','compiled'),('--export-dependency-info','dependencies'),('--output-partial-info-plist','partial-info.plist')]:
 argv[argv.index(flag)+1]=guest(folder/name)
(folder/'compiled').mkdir()
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
# Use the already verified disk-service prelude and fresh log destinations.
base=root/'runtime/unity-storyboard-passed-dd76-v1'
stem=Path(a.build_log).stem
jobs=[]
for source in sorted((root/'runtime/xcode-service-runtime').glob(stem+'-*.plist')):
 name=source.name.removeprefix(stem+'-')
 text=source.read_text().replace('logs/'+stem,str(folder.relative_to(root))+'/service')
 target=folder/name;target.write_text(text);target.chmod(0o644);jobs.append(target)
assert len(jobs)>=7
import shutil
shutil.copy2(base/'da-client',folder/'da-client')
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
 ''.join('launchctl load '+shlex.quote(guest(job))+' || exit $?\n' for job in jobs)+
 shlex.quote(guest(folder/'da-client'))+' || exit $?\n'+shlex.join(argv)+'\nstatus=$?\nprintf "ORIGINAL_ASSETCATALOG_STATUS %s\\n" "$status"\nexit "$status"\n')
cmd=list(profile['command'][:-2])+['/bin/bash',guest(script)];cmd[3]=str(a.timeout)
(folder/'invocation.json').write_text(json.dumps(dict(command=cmd,original_arguments=original_argv,arguments=argv),indent=2)+'\n')
print('RUNNING',folder.relative_to(root),flush=True)
log=folder/'run.log'
with log.open('w') as out:r=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ORIGINAL_ASSETCATALOG_STATUS ([0-9]+)$',t,re.M)
products={str(f.relative_to(root)):dict(size=f.stat().st_size,sha256=sha(f)) for f in (folder/'compiled').rglob('*') if f.is_file()}
verified=r.returncode==0 and statuses==['0'] and bool(products)
record=dict(verified=verified,stage=a.stage,configuration=a.configuration,outer_status=r.returncode,native_statuses=statuses,original_build_log=a.build_log,original_build_log_sha256=sha(root/a.build_log),original_arguments=original_argv,arguments=argv,products=products,source_runtime=profile['source_runtime'],log=str(log.relative_to(root)),log_sha256=sha(log),files={str(f.relative_to(root)):sha(f) for f in [Path(__file__),script,root/a.stage,root/a.configuration]},independent_asset_semantics_verified=False,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(t[-6000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
