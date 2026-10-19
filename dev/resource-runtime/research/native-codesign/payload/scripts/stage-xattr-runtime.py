#!/usr/bin/env python3
"""Freeze the complete xattr source kernel in coherent private signing roots."""
from pathlib import Path
import argparse,fcntl,hashlib,json,re,shutil,subprocess
r=Path(__file__).resolve().parent.parent;a=argparse.ArgumentParser();a.add_argument('--tag',required=True);a.add_argument('--derq-stage',required=True);a.add_argument('--kernel-build',required=True);args=a.parse_args();assert re.fullmatch('[a-z0-9-]+',args.tag)
w=r/('runtime/xattr-runtime-'+args.tag);assert not w.exists();w.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
parent=json.loads((r/args.derq_stage).read_text());kernel=json.loads((r/args.kernel_build).read_text());assert kernel['full_libsystem_kernel_source_build'] and kernel['complete_source_files']==879
library=r/kernel['variant_root']/'usr/lib/system/libsystem_kernel.dylib';assert sha(library)==kernel['binary_sha256'];records={}
with (r/'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for label,selected in parent['runtimes'].items():
        folder=w/label;folder.mkdir();base=(r/selected['system_version_binding']).parents[3];root=folder/'darling-root';subprocess.run(['cp','-a','--reflink=auto',str(base),str(root)],check=True)
        shutil.copy2(library,root/'usr/lib/system/libsystem_kernel.dylib');runtime={}
        for key,value in selected['source_runtime'].items():
            src=library if key=='LINUXCODE_LIBSYSTEM_KERNEL' else r/value['path'];assert key=='LINUXCODE_LIBSYSTEM_KERNEL' or sha(src)==value['sha256'];dest=folder/src.name;shutil.copy2(src,dest);runtime[key]=dict(path=str(dest.relative_to(r)),sha256=sha(dest))
        version=root/'System/Library/CoreServices/SystemVersion.plist';tool=root/'usr/bin/derq';records[label]=dict(source_runtime=runtime,system_version_binding=str(version.relative_to(r)),files={str(p.relative_to(r)):sha(p) for p in [version,tool,root/'usr/lib/system/libsystem_kernel.dylib']})
report=dict(derq_stage=args.derq_stage,derq_stage_sha256=sha(r/args.derq_stage),kernel_build=args.kernel_build,kernel_build_sha256=sha(r/args.kernel_build),runtimes=records,installed=False,persistent_prefix_modified=False)
(r/('artifacts/xattr-runtime-'+args.tag+'-stage.json')).write_text(json.dumps(report,indent=2)+'\n');print('Staged coherent xattr kernel roots')
