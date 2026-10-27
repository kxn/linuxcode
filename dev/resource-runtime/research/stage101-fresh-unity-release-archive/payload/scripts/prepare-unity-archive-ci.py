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
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
milestone=json.loads((r/a.milestone).read_text());assert milestone['verified']
source=r/a.build_run;setup=json.loads((source/'prepared.json').read_text())
guards={}
if milestone.get('end_to_end_report'):
    end_path=r/milestone['end_to_end_report'];end=json.loads(end_path.read_text())
    assert sha(end_path)==milestone['end_to_end_report_sha256'] and end['verified']
    assert end['prepared_run']==a.build_run and milestone['application']==end['application']
    native=r/milestone['native_build_result'];status=json.loads(native.read_text())
    assert sha(native)==milestone['native_build_result_sha256']
    assert status['native_exit_status']==status['outer_exit_status']==status['exit_status']==0
    arguments=list(end['xcodebuild_command']);assert arguments.pop(0)=='xcodebuild'
    original_ios=r/setup['export'];original_dd=source/'DerivedData'
    import plistlib
    app=r/end['application'];info=plistlib.loads((app/'Info.plist').read_bytes())
    guarded=[app/info['CFBundleExecutable'],app/'_CodeSignature/CodeResources',
             original_dd/'Build/Intermediates.noindex/XCBuildData/build.db',
             original_ios/'Unity-iPhone.xcodeproj/project.pbxproj']
    guards={str(p.relative_to(r)):sha(p) for p in guarded}
    setup=dict(arguments=arguments,application=end['application'],
               test_fixture_profile_requirement_disabled=True,
               source_bindings=[dict(source=str(original_dd.relative_to(r)),target=str(original_dd.relative_to(r))),
                                dict(source=str(original_ios.relative_to(r)),target=str(original_ios.relative_to(r)))])
else:
    assert milestone['native_build_status']==0 and milestone['application']==setup['application']
folder=Path(tempfile.mkdtemp(prefix='unity-original-archive-',dir=r/'runtime'));folder.chmod(0o700)
cache_setup=json.loads((r/a.reuse_archive_run/'prepared.json').read_text()) if a.reuse_archive_run else setup
bindings=cache_setup.get('source_bindings')
if bindings is None:bindings=json.loads((r/cache_setup['bindings']).read_text())
mapped=[]
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
            original_guards=guards,preparation_script_sha256=sha(Path(__file__)),
            test_certificate_only=True,test_profile_requirement_disabled=setup['test_fixture_profile_requirement_disabled'],
            original_products_preserved=True,native_execution_verified=False)
(folder/'prepared.json').write_text(json.dumps(record,indent=2)+'\n');print(folder.relative_to(r))
