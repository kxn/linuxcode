#!/usr/bin/env python3
"""Compose a rebuilt daemon with an immutable, complete private runtime root."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for n in ['parent-stage','build','tag']:p.add_argument('--'+n,required=True)
a=p.parse_args();assert a.tag.isalnum();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();parent=r/a.parent_stage;data=json.loads(parent.read_text());build=r/a.build;b=json.loads(build.read_text());assert b['full_iokitd_source_build'];source=r/b['binary'];assert sha(source)==b['binary_sha256'];resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
for n,d in data['files'].items():resolve(n,d)
folder=r/('runtime/audit-session-runtime-'+a.tag);report=r/('artifacts/private-procfs-auditsession'+a.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir();base=(r/data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent/'darling-root';subprocess.run(['cp','-a','--reflink=auto',str(base),str(folder/'darling-root')],check=True);dest=folder/'darling-root/usr/sbin/iokitd';previous=sha(dest);shutil.copy2(source,dest);data['files'][str(dest.relative_to(r))]=sha(dest)
selected={}
for key,row in data['source_runtime'].items():
 assert sha(r/row['path'])==row['sha256'];target=folder/Path(row['path']).name;shutil.copy2(r/row['path'],target);selected[key]=dict(path=str(target.relative_to(r)),sha256=sha(target));data['files'][str(target.relative_to(r))]=sha(target)
data['source_runtime']=selected
for key,suffix in [('system_version_binding','System/Library/CoreServices/SystemVersion.plist'),('mtab','private/etc/mtab')]:data[key]=str((folder/'darling-root'/suffix).relative_to(r))
data['files'][data['system_version_binding']]=sha(r/data['system_version_binding']);assert (r/data['mtab']).readlink()==Path(data['mtab_target'])
for file in [Path(__file__),parent,build]:data['files'][str(file.relative_to(r))]=sha(file)
data.update(iokitd_candidate=dict(build=a.build,binary=str(dest.relative_to(r)),sha256=sha(dest),previous_sha256=previous),runtime_execution_verified=False,full_goal_complete=False);report.write_text(json.dumps(data,indent=2)+'\n');print(report.relative_to(r))
