#!/usr/bin/env python3
"""Clone a verified private runtime and replace only its source launchctl."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-stage',required=True);p.add_argument('--build',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.isalnum()
sha=lambda n:hashlib.sha256((r/n).read_bytes()).hexdigest();data=json.loads((r/a.parent_stage).read_text());build=json.loads((r/a.build).read_text())
resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
assert build['full_launchctl_translation_unit']
for n,h in data['files'].items():resolve(n,h)
for n,h in build['files'].items():resolve(n,h)
assert sha(build['binary'])==build['binary_sha256']
folder=r/('runtime/audit-session-runtime-'+a.tag);report=r/('artifacts/private-procfs-auditsession'+a.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir()
base=(r/data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent/'darling-root'
subprocess.run(['cp','-a','--reflink=auto',str(base),str(folder/'darling-root')],check=True)
selected={}
for key,row in data['source_runtime'].items():
 assert sha(row['path'])==row['sha256'];target=folder/Path(row['path']).name;shutil.copy2(r/row['path'],target);name=str(target.relative_to(r));selected[key]=dict(path=name,sha256=sha(name));data['files'][name]=sha(name)
target=folder/'darling-root/bin/launchctl';target.unlink();shutil.copy2(r/build['binary'],target);name=str(target.relative_to(r));data['files'][name]=sha(name)
for n in [a.parent_stage,a.build,'scripts/stage-launchctl-runtime.py']:data['files'][n]=sha(n)
data['source_runtime']=selected;data['source_builds']['launchctl']=a.build
data['system_version_binding']=str((folder/'darling-root/System/Library/CoreServices/SystemVersion.plist').relative_to(r));data['files'][data['system_version_binding']]=sha(data['system_version_binding'])
data['mtab']=str((folder/'darling-root/private/etc/mtab').relative_to(r));assert (r/data['mtab']).readlink()==Path(data['mtab_target'])
data['source_launchctl']=dict(path=name,sha256=sha(name),build=a.build)
data['runtime_execution_verified']=False;data['full_goal_complete']=False
report.write_text(json.dumps(data,indent=2)+'\n');print(report.relative_to(r))
