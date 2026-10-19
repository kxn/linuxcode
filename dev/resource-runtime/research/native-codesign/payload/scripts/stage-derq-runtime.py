#!/usr/bin/env python3
"""Add original derq and reconstructed CoreEntitlements to private runtime roots."""
from pathlib import Path
import argparse,fcntl,hashlib,json,runpy,shutil,subprocess
r=Path(__file__).resolve().parent.parent
a=argparse.ArgumentParser();a.add_argument('--tag',required=True);g=a.add_mutually_exclusive_group(required=True);g.add_argument('--codesign-stage');g.add_argument('--dispatch-stage');args=a.parse_args()
import re
assert re.fullmatch('[a-z0-9-]+',args.tag);w=r/('runtime/derq-'+args.tag);assert not w.exists();w.mkdir()
parent=runpy.run_path(str(r/('scripts/codesign-zsign-runtime-profile.py' if args.codesign_stage else 'scripts/resource-tool-dispatch-profile.py')));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
derq=r/'runtime/recovery/macOS Base System/usr/bin/derq';library=r/'runtime/rebuilt-coreentitlements-signing-native/libCoreEntitlements.dylib';reconstruction=library.parent/'reconstruction.json'
rec=json.loads(reconstruction.read_text());assert sha(library)==rec['staged_image_sha256']
target=w/'libraries'/library.name;target.parent.mkdir();shutil.copy2(library,target)
records={}
with (r/'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for diagnostic in [False,True]:
        p=parent['profile'](diagnostic=diagnostic,**({'codesign_stage':args.codesign_stage} if args.codesign_stage else {'dispatch_stage':args.dispatch_stage}));label='diagnostic' if diagnostic else 'normal';folder=w/label;folder.mkdir()
        base=r/p['resource_tool_dispatch_selected_runtime']['variant_root'];root=folder/'darling-root'
        subprocess.run(['cp','-a','--reflink=auto',str(base),str(root)],check=True)
        tool=root/'usr/bin/derq';assert not tool.exists();shutil.copy2(derq,tool);tool.chmod(0o755)
        selected={}
        for key,value in p['source_runtime'].items():
            dest=folder/Path(value['path']).name;shutil.copy2(r/value['path'],dest);assert sha(dest)==value['sha256'];selected[key]={'path':str(dest.relative_to(r)),'sha256':sha(dest)}
        version=root/'System/Library/CoreServices/SystemVersion.plist'
        records[label]=dict(source_runtime=selected,system_version_binding=str(version.relative_to(r)),files={str(x.relative_to(r)):sha(x) for x in [tool,version]})
data=dict(codesign_stage=args.codesign_stage,codesign_stage_sha256=sha(r/args.codesign_stage) if args.codesign_stage else None,dispatch_stage=args.dispatch_stage,dispatch_stage_sha256=sha(r/args.dispatch_stage) if args.dispatch_stage else None,root=str(w.relative_to(r)),runtimes=records,files={str(x.relative_to(r)):sha(x) for x in [derq,library,target,reconstruction]},original_derq_unmodified=True,persistent_prefix_modified=False)
report=r/('artifacts/derq-'+args.tag+'-stage.json');assert not report.exists();report.write_text(json.dumps(data,indent=2)+'\n');print(report)
