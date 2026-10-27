#!/usr/bin/env python3
"""Compose the existing server/kernel pair with a private source-built loader."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',required=True);p.add_argument('--loader-build',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.isalnum()
sha=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest();read=lambda n:json.loads((root/n).read_text())
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve'];data=read(a.parent_stage);build=read(a.loader_build);assert build['full_mldr_source_build']
for name,digest in data['files'].items():resolve(name,digest)
for name,digest in build['files'].items():assert sha(name)==digest,name
assert sha(build['loader'])==build['loader_sha256']
folder=root/('runtime/audit-session-runtime-'+a.tag);report=root/('artifacts/private-procfs-auditsession'+a.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir()
base=(root/data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent
subprocess.run(['cp','-a','--reflink=auto',str(base/'darling-root'),str(folder/'darling-root')],check=True)
selected={}
for key,row in data['source_runtime'].items():
 assert sha(row['path'])==row['sha256'];target=folder/Path(row['path']).name;shutil.copy2(root/row['path'],target);name=str(target.relative_to(root));selected[key]=dict(path=name,sha256=sha(name));data['files'][name]=sha(name)
loader=folder/'darling-root/usr/libexec/darling/mldr';previous=sha(str(loader.relative_to(root)));shutil.copy2(root/build['loader'],loader);name=str(loader.relative_to(root));data['files'][name]=sha(name)
for name in [a.parent_stage,a.loader_build,'scripts/stage-fixed-commpage-runtime.py']:data['files'][name]=sha(name)
data['source_runtime']=selected;data['source_builds']['loader']=a.loader_build;data['system_version_binding']=str((folder/'darling-root/System/Library/CoreServices/SystemVersion.plist').relative_to(root));data['files'][data['system_version_binding']]=sha(data['system_version_binding']);data['mtab']=str((folder/'darling-root/private/etc/mtab').relative_to(root));assert (root/data['mtab']).readlink()==Path(data['mtab_target']);data['runtime_execution_verified']=False;data['full_goal_complete']=False;data['fixed_commpage_loader']=dict(build=a.loader_build,previous_loader_sha256=previous,loader=str(loader.relative_to(root)),loader_sha256=sha(str(loader.relative_to(root))))
report.write_text(json.dumps(data,indent=2)+'\n');print(report.relative_to(root))
