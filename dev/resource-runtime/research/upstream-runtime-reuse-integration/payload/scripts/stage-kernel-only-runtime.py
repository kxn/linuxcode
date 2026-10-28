#!/usr/bin/env python3
"""Clone a coherent private runtime and replace only its complete source kernel."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shutil
import subprocess

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',required=True);p.add_argument('--kernel-build',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert re.fullmatch('[a-z0-9]+',a.tag)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
data=json.loads((r/a.parent_stage).read_text());build=json.loads((r/a.kernel_build).read_text())
assert build['full_libsystem_kernel_source_build'] and build['complete_source_files']==len(build['sources'])>=879
resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in data['files'].items():resolve(name,digest)
for name,row in data['source_runtime'].items():assert sha(r/row['path'])==row['sha256']
binary=r/build['variant_root']/'usr/lib/system/libsystem_kernel.dylib';assert sha(binary)==build['binary_sha256']
folder=r/('runtime/audit-session-runtime-'+a.tag);report=r/('artifacts/private-procfs-auditsession'+a.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir()
base=(r/data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent/'darling-root'
root=folder/'darling-root';subprocess.run(['cp','-a','--reflink=auto',str(base),str(root)],check=True)
selected={}
for key,row in data['source_runtime'].items():
    target=folder/Path(row['path']).name;shutil.copy2(binary if key=='LINUXCODE_LIBSYSTEM_KERNEL' else r/row['path'],target)
    name=str(target.relative_to(r));selected[key]=dict(path=name,sha256=sha(target));data['files'][name]=sha(target)
target=root/'usr/lib/system/libsystem_kernel.dylib';target.unlink();shutil.copy2(binary,target);data['files'][str(target.relative_to(r))]=sha(target)
data['source_runtime']=selected
data['source_builds']['kernel']=a.kernel_build
data['source_builds']['libsystem_kernel']=a.kernel_build
data['kernel_candidate']=a.kernel_build
for name in [a.parent_stage,a.kernel_build,'scripts/stage-kernel-only-runtime.py']:data['files'][name]=sha(r/name)
data['system_version_binding']=str((root/'System/Library/CoreServices/SystemVersion.plist').relative_to(r));data['files'][data['system_version_binding']]=sha(r/data['system_version_binding'])
data['mtab']=str((root/'private/etc/mtab').relative_to(r));assert (r/data['mtab']).readlink()==Path(data['mtab_target'])
data['runtime_execution_verified']=False;data['full_goal_complete']=False;data['kernel_only_parent_stage']=a.parent_stage
report.write_text(json.dumps(data,indent=2)+'\n');print(report.relative_to(r))
