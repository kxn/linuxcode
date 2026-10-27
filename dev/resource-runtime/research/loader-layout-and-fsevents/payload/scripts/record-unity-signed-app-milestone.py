#!/usr/bin/env python3
"""Record a successful original Unity/CocoaPods build and verified App."""
from pathlib import Path
import argparse,hashlib,json,plistlib,struct,re
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for k in ['build-report','signature-report','report']:p.add_argument('--'+k,required=True)
p.add_argument('--application',default='runtime/unity-ios-cocoapods-v76-build/DerivedData/Build/Products/Debug-iphoneos/uEmuera.app')
p.add_argument('--fresh-build-result')
a=p.parse_args();sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
build=json.loads((r/a.build_report).read_text());sign=json.loads((r/a.signature_report).read_text())
assert build['exit_status']==0 and build['native_xcode_status']==['0']
assert sha(r/build['log'])==build['log_sha256']
assert '** BUILD SUCCEEDED **' in (r/build['log']).read_text()
assert sign['verified'] and sign['outer_status']==0 and len(sign['native_statuses'])==6
assert all(status=='0' for index,status in sign['native_statuses']) and not sign['zsign_used']
app=r/a.application;assert app.resolve().is_relative_to(r/'runtime');info=plistlib.loads((app/'Info.plist').read_bytes());exe=app/info['CFBundleExecutable'];b=exe.read_bytes();assert struct.unpack_from('<II',b)==(0xfeedfacf,0x100000c)
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
if a.fresh_build_result:
 fresh=json.loads((r/a.fresh_build_result).read_text())
 assert fresh['DerivedData_absent_at_start'] and fresh['Unity_Bee_cache_entry_absent_at_start'] and fresh['outer_status']==0
 assert fresh['actual_arguments']==build['xcode_arguments'] and fresh['stage']==build['private_procfs_stage']
 derived=r/fresh['DerivedData'];assert app.is_relative_to(derived)
 cache=fresh['observed_Unity_Bee_cache_target'];assert '/'+fresh['DerivedData']+'/' in cache
 text=(r/build['log']).read_text();progress=re.search(r'\*\*\* il2cpp build success[^\n]*?, (\d+) items updated, (\d+) evaluated',text);assert progress
 updated,evaluated=map(int,progress.groups());assert updated>=400 and evaluated>=updated
 compile_tasks=text.count('\nCompileC ');assert compile_tasks>=50
 archives={}
 for path in [app.parent/'libGameAssembly.a',app.parent/'il2cpp.a']:
  data=path.read_bytes();assert data[:8]==b'!<arch>\n';offset=8;objects=[]
  while offset<len(data):
   header=data[offset:offset+60];assert len(header)==60 and header[58:]==b'`\n';size=int(header[48:58]);start=offset+60;end=start+size;assert end<=len(data)
   name=header[:16].decode().strip();payload=data[start:end]
   if name.startswith('#1/'):
    count=int(name[3:]);name=payload[:count].rstrip(b'\0 ').decode();payload=payload[count:]
   else:name=name.rstrip('/')
   if name and not name.startswith('__.SYMDEF'):
    assert len(payload)>=32 and struct.unpack_from('<II',payload)==(0xfeedfacf,0x100000c)
    assert struct.unpack_from('<I',payload,12)[0]==1
    objects.append(dict(name=name,size=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
   offset=end+(size&1)
  assert offset==len(data) and objects
  archives[str(path.relative_to(r))]=dict(size=len(data),sha256=hashlib.sha256(data).hexdigest(),arm64_MH_OBJECT_members=len(objects),objects=objects)
 assert sum(v['arm64_MH_OBJECT_members'] for v in archives.values())>=350
 record.update(single_invocation_fresh_DerivedData_verified=True,clean_DerivedData_verified=True,
  fresh_build_result=a.fresh_build_result,fresh_build_result_sha256=sha(r/a.fresh_build_result),
  Unity_Bee_cache_target=cache,IL2CPP_updated_tasks=updated,IL2CPP_evaluated_tasks=evaluated,
  original_Xcode_CompileC_tasks=compile_tasks,independent_Unity_archives=archives)
destination=r/a.report;assert not destination.exists();destination.write_text(json.dumps(record,indent=2)+'\n');print('SIGNED_UNITY_APP_MILESTONE',destination)
