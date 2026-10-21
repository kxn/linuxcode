#!/usr/bin/env python3
"""Select a newly built launchd without overwriting any mapped runtime."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',required=True);p.add_argument('--build',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.isalnum()
sha=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest();d=json.loads((root/a.parent_stage).read_text());b=json.loads((root/a.build).read_text());resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
assert b['full_launchd_source_build'] and b['complete_source_files']==16 and sha(b['binary'])==b['binary_sha256']
for n,h in d['files'].items():resolve(n,h)
for n,h in b['source_files'].items():resolve(n,h)
f=root/('runtime/audit-session-runtime-'+a.tag);out=root/('artifacts/private-procfs-auditsession'+a.tag+'-stage.json');assert not f.exists() and not out.exists();f.mkdir();subprocess.run(['cp','-a','--reflink=auto',str(root/b['variant_root']),str(f/'darling-root')],check=True);selected={}
for key,row in d['source_runtime'].items():
 source=b['binary'] if key=='LINUXCODE_LAUNCHD' else row['path'];target=f/Path(row['path']).name;shutil.copy2(root/source,target);n=str(target.relative_to(root));selected[key]=dict(path=n,sha256=sha(n));d['files'][n]=sha(n)
 if key=='LINUXCODE_DARLING_SERVER':continue
 path=f/'darling-root'/('sbin/launchd' if key=='LINUXCODE_LAUNCHD' else 'usr/lib/system/'+target.name);assert sha(str(path.relative_to(root)))==sha(n)
for n in [a.parent_stage,a.build,'scripts/stage-launchd-job-runtime.py']:d['files'][n]=sha(n)
d['source_runtime']=selected;d['source_builds']['launchd']=a.build;d['system_version_binding']=str((f/'darling-root/System/Library/CoreServices/SystemVersion.plist').relative_to(root));d['files'][d['system_version_binding']]=sha(d['system_version_binding']);d['mtab']=str((f/'darling-root/private/etc/mtab').relative_to(root));assert (root/d['mtab']).readlink()==Path(d['mtab_target']);d['runtime_execution_verified']=False;d['full_goal_complete']=False;d['launch_job_candidate']=a.build
out.write_text(json.dumps(d,indent=2)+'\n');print(out.relative_to(root))
