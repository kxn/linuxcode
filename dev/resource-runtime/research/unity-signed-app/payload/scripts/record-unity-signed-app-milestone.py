#!/usr/bin/env python3
"""Record a successful original Unity/CocoaPods build and verified App."""
from pathlib import Path
import argparse,hashlib,json,plistlib,struct
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for k in ['build-report','signature-report','report']:p.add_argument('--'+k,required=True)
a=p.parse_args();sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
build=json.loads((r/a.build_report).read_text());sign=json.loads((r/a.signature_report).read_text())
assert build['exit_status']==0 and build['native_xcode_status']==['0']
assert sha(r/build['log'])==build['log_sha256']
assert '** BUILD SUCCEEDED **' in (r/build['log']).read_text()
assert sign['verified'] and sign['outer_status']==0 and len(sign['native_statuses'])==6
assert all(status=='0' for index,status in sign['native_statuses']) and not sign['zsign_used']
app=r/'runtime/unity-ios-cocoapods-v76-build/DerivedData/Build/Products/Debug-iphoneos/uEmuera.app';info=plistlib.loads((app/'Info.plist').read_bytes());exe=app/info['CFBundleExecutable'];b=exe.read_bytes();assert struct.unpack_from('<II',b)==(0xfeedfacf,0x100000c)
cursor=32;platform=None
for i in range(struct.unpack_from('<I',b,16)[0]):
 command,length=struct.unpack_from('<II',b,cursor);assert length>=8 and cursor+length<=len(b)
 if command==0x32:platform=struct.unpack_from('<III',b,cursor+8)
 cursor+=length
assert platform and platform[0]==2
nibs={}
for path in app.rglob('*.nib'):
 data=path.read_bytes();assert data[:10]==b'NIBArchive';header=struct.unpack_from('<10I',data,10);assert all(50<=header[i]<=len(data) for i in [3,5,7,9]);nibs[str(path.relative_to(app))]=dict(size=len(data),sha256=sha(path))
assert len(nibs)==4
files=[exe,app/'Info.plist',app/'_CodeSignature/CodeResources',app/'Assets.car',*app.glob('AppIcon*.png')]
frameworks={}
for path in (app/'Frameworks').glob('*.framework'):
 metadata=plistlib.loads((path/'Info.plist').read_bytes());binary=path/metadata['CFBundleExecutable'];frameworks[path.name]=dict(identifier=metadata['CFBundleIdentifier'],binary_size=binary.stat().st_size,binary_sha256=sha(binary),resource_seal_sha256=sha(path/'_CodeSignature/CodeResources'))
assert set(frameworks)=={'UnityFramework.framework','libHarfBuzzSharp.framework','libSkiaSharp.framework'}
fixture=json.loads((r/'artifacts/unity-ios26-header-fixture-v1.json').read_text())
record=dict(verified=True,original_xcodebuild_full_build_and_original_codesign_success=True,
 application=str(app.relative_to(r)),application_identifier=info['CFBundleIdentifier'],architecture='arm64',platform='iPhoneOS',build_version=platform,
 build_report=a.build_report,build_report_sha256=sha(r/a.build_report),signature_report=a.signature_report,signature_report_sha256=sha(r/a.signature_report),
 stage=build['private_procfs_stage'],resource_environment=build['direct_resource_environment']['configuration'],
 original_CI_arguments=build['xcode_arguments'],GUI_used=False,zsign_used=False,
 ad_hoc_signing_only=True,developer_certificate_provisioning_or_device_install_verified=False,
 Unity_IL2CPP_and_CocoaPods=True,embedded_frameworks=frameworks,Storyboard_NIBs=nibs,
 file_evidence={str(path.relative_to(r)):dict(size=path.stat().st_size,sha256=sha(path)) for path in files},
 fixture_SDK_compatibility_patch='artifacts/unity-ios26-header-fixture-v1.json',fixture_patch_count=len(fixture['patches']),
 project_and_CocoaPods_configuration_unchanged=True,visual_rendering_or_device_execution_verified=False,
 clean_machine_runtime_reconstruction_verified=False,UE_project_verified=False,full_goal_complete=False,
 tool_sha256=sha(Path(__file__)))
destination=r/a.report;assert not destination.exists();destination.write_text(json.dumps(record,indent=2)+'\n');print('SIGNED_UNITY_APP_MILESTONE',destination)
