#!/usr/bin/env python3
"""Compose a private kernel candidate while retaining the server/launchd/loader pair."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',required=True);p.add_argument('--build',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.isalnum()
sha=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest();data=json.loads((root/a.parent_stage).read_text());build=json.loads((root/a.build).read_text());resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
assert build['full_libsystem_kernel_source_build'];library=str(Path(build['variant_root'])/'usr/lib/system/libsystem_kernel.dylib');assert sha(library)==build['binary_sha256']
for n,d in data['files'].items():resolve(n,d)
folder=root/('runtime/audit-session-runtime-'+a.tag);report=root/('artifacts/private-procfs-auditsession'+a.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir();subprocess.run(['cp','-a','--reflink=auto',str(root/build['variant_root']),str(folder/'darling-root')],check=True);selected={}
for key,row in data['source_runtime'].items():
 source=library if key=='LINUXCODE_LIBSYSTEM_KERNEL' else row['path'];target=folder/Path(row['path']).name;shutil.copy2(root/source,target);n=str(target.relative_to(root));selected[key]=dict(path=n,sha256=sha(n));data['files'][n]=sha(n)
 if key=='LINUXCODE_DARLING_SERVER':continue
 dest=folder/'darling-root'/('sbin/launchd' if key=='LINUXCODE_LAUNCHD' else 'usr/lib/system/'+target.name);assert sha(str(dest.relative_to(root)))==sha(n)
for n in [a.parent_stage,a.build,'scripts/stage-kernel-backend.py']:data['files'][n]=sha(n)
data['source_runtime']=selected;data['source_builds']['libsystem_kernel']=a.build;data['system_version_binding']=str((folder/'darling-root/System/Library/CoreServices/SystemVersion.plist').relative_to(root));data['files'][data['system_version_binding']]=sha(data['system_version_binding']);data['mtab']=str((folder/'darling-root/private/etc/mtab').relative_to(root));assert (root/data['mtab']).readlink()==Path(data['mtab_target']);data['runtime_execution_verified']=False;data['full_goal_complete']=False;data['kernel_candidate']=a.build
report.write_text(json.dumps(data,indent=2)+'\n');print(report.relative_to(root))
