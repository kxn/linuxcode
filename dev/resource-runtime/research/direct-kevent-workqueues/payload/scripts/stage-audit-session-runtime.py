#!/usr/bin/env python3
"""Compose a coherent private root with a paired audit-session server/kernel."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',required=True);p.add_argument('--server-build',required=True);p.add_argument('--kernel-build',required=True);p.add_argument('--tag',required=True);args=p.parse_args();assert args.tag.isalnum()
read=lambda n:json.loads((root/n).read_text());sha=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest();resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
a=read(args.parent_stage);server=read(args.server_build);kernel=read(args.kernel_build);assert server['full_server_source_build'] and kernel['full_libsystem_kernel_source_build'] and kernel['complete_source_files']==len(kernel['sources']) and kernel['complete_source_files']>=879
assert sha(server['server'])==server['server_sha256'];candidate=str(Path(kernel['variant_root'])/'usr/lib/system/libsystem_kernel.dylib');assert sha(candidate)==kernel['binary_sha256']
for name,digest in a['files'].items():resolve(name,digest)
folder=root/('runtime/audit-session-runtime-'+args.tag);report=root/('artifacts/private-procfs-auditsession'+args.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir();guest=folder/'darling-root'
subprocess.run(['cp','-a','--reflink=auto',str(root/kernel['variant_root']),str(guest)],check=True)
selected={}
for key,row in a['source_runtime'].items():
 source=server['server'] if key=='LINUXCODE_DARLING_SERVER' else candidate if key=='LINUXCODE_LIBSYSTEM_KERNEL' else row['path'];target=folder/Path(row['path']).name;assert not target.exists();shutil.copy2(root/source,target);name=str(target.relative_to(root));selected[key]=dict(path=name,sha256=sha(name));a['files'][name]=sha(name)
 if target.name.endswith('.dylib'):dest=guest/'usr/lib/system'/target.name
 elif key=='LINUXCODE_LAUNCHD':dest=guest/'sbin/launchd'
 else:continue
 shutil.copyfile(target,dest);name=str(dest.relative_to(root));a['files'][name]=sha(name)
for name in [args.server_build,args.kernel_build,'scripts/stage-audit-session-runtime.py']:a['files'][name]=sha(name)
a['source_runtime']=selected;a['source_builds']['server']=args.server_build;a['source_builds']['kernel']=args.kernel_build;a['system_version_binding']=str((guest/'System/Library/CoreServices/SystemVersion.plist').relative_to(root));a['mtab']=str((guest/'private/etc/mtab').relative_to(root));assert (root/a['mtab']).is_symlink() and (root/a['mtab']).readlink()==Path(a['mtab_target']);a['files'][a['system_version_binding']]=sha(a['system_version_binding']);a['runtime_execution_verified']=False;a['full_goal_complete']=False;a['audit_session_backend']='Server-owned headless process sessions, with fork/exec inheritance and synchronized Mach audit tokens.'
report.write_text(json.dumps(a,indent=2)+'\n');print(report.relative_to(root))
