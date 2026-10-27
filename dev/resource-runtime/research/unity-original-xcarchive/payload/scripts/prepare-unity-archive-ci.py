#!/usr/bin/env python3
"""Prepare original xcodebuild archive on private copies of a verified Unity build."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-run',required=True);p.add_argument('--milestone',required=True);p.add_argument('--reuse-archive-run',help='Reuse a preserved partial archive cache through another private copy');p.add_argument('--configuration',help='Select an actual Xcode build configuration without changing its project settings');a=p.parse_args()
milestone=json.loads((r/a.milestone).read_text());assert milestone['verified'] and milestone['native_build_status']==0
source=r/a.build_run;setup=json.loads((source/'prepared.json').read_text());assert milestone['application']==setup['application']
folder=Path(tempfile.mkdtemp(prefix='unity-original-archive-',dir=r/'runtime'));folder.chmod(0o700)
cache_setup=json.loads((r/a.reuse_archive_run/'prepared.json').read_text()) if a.reuse_archive_run else setup
bindings=json.loads((r/cache_setup['bindings']).read_text());mapped=[]
for row in bindings:
    old=r/row['source'];new=folder/old.name
    subprocess.run(['cp','-a','--reflink=auto',str(old),str(new)],check=True)
    mapped.append(dict(source=str(new.relative_to(r)),target=row['target']))
binding=folder/'workspace-bindings.json';binding.write_text(json.dumps(mapped,indent=2)+'\n')
args=list(setup['arguments']);assert args[-1]=='build';args[-1:] = ['-archivePath',str(folder/'Unity-iPhone.xcarchive'),'archive']
if a.configuration:args[args.index('-configuration')+1]=a.configuration
prefix='/Volumes/SystemRoot/workspace/'
args=[str(r/v[len(prefix):]) if v.startswith(prefix) else v for v in args]
record=dict(arguments=args,bindings=str(binding.relative_to(r)),source_build_run=a.build_run,
            source_milestone=a.milestone,source_milestone_sha256=hashlib.sha256((r/a.milestone).read_bytes()).hexdigest(),
            archive=str((folder/'Unity-iPhone.xcarchive').relative_to(r)),
            reused_partial_archive_run=a.reuse_archive_run,
            test_certificate_only=True,test_profile_requirement_disabled=setup['test_fixture_profile_requirement_disabled'],
            original_products_preserved=True,native_execution_verified=False)
(folder/'prepared.json').write_text(json.dumps(record,indent=2)+'\n');print(folder.relative_to(r))
