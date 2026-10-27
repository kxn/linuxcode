#!/usr/bin/env python3
"""Record the actual fresh Linux Unity export, CocoaPods build and signed iOS app."""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,struct
r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prepared-run',required=True);p.add_argument('--native-run',required=True);p.add_argument('--signature-report',required=True);p.add_argument('--report',required=True)
a=p.parse_args();sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
folder=r/a.prepared_run;end_path=folder/'end-to-end-result.json';end=json.loads(end_path.read_text())
assert all(end.get(k) is True for k in ['verified','Unity_export_verified','CocoaPods_verified','original_xcodebuild_verified','original_codesign_strict_verified','native_Pod_symbol_linked'])
export_path=r/end['export_report'];export=json.loads(export_path.read_text());assert export['verified'] and export['outer_status']==0 and export['native_Linux_Editor'] and export['headless'] and not export['mac_used']
assert sha(r/export['log'])==export['log_sha256'] and 'LINUXCODE_UNITY_IOS_EXPORT_SUCCEEDED' in (r/export['log']).read_text()
native=r/a.native_run;output=native/'output.log';text=output.read_text(errors='replace')
assert '** BUILD SUCCEEDED **' in text and re.findall(r'^LINUXCODE_NATIVE_XCODE_STATUS (\d+)$',text,re.M)==['0']
native_result=json.loads((native/'result.json').read_text())
assert native_result['native_exit_status']==native_result['outer_exit_status']==native_result['exit_status']==0
assert native_result['log_sha256']==sha(output)
plan=json.loads((native/'plan.json').read_text())
assert plan['original_argv']==end['xcodebuild_command'][1:]
if end.get('native_run'):
    assert end['native_run']==str(native.relative_to(r))
    assert end['native_result_sha256']==sha(native/'result.json')
signature_path=r/a.signature_report;signature=json.loads(signature_path.read_text());assert signature['verified'] and signature['outer_status']==0
assert signature['native_statuses']==[(str(i),'0') for i in range(len(signature['products']))] or signature['native_statuses']==[[str(i),'0'] for i in range(len(signature['products']))]
assert sha(r/signature['log'])==signature['log_sha256']
checks=end['independent_product_checks'];assert set(checks)==set(signature['products']) and all(c['verified'] for c in checks.values())
app=r/end['application'];info=plistlib.loads((app/'Info.plist').read_bytes());exe=app/info['CFBundleExecutable'];b=exe.read_bytes();assert struct.unpack_from('<II',b)==(0xfeedfacf,0x100000c)
cursor=32;platform=None
for _ in range(struct.unpack_from('<I',b,16)[0]):
    command,length=struct.unpack_from('<II',b,cursor);assert length>=8 and cursor+length<=len(b)
    if command==0x32:platform=struct.unpack_from('<III',b,cursor+8)
    cursor+=length
assert platform and platform[0]==2
assert info['CFBundleIdentifier']=='org.linuxcode.exportsmoke' and info['CFBundleSupportedPlatforms']==['iPhoneOS']
nibs={}
for path in app.rglob('*.nib'):
    data=path.read_bytes();assert data[:10]==b'NIBArchive';header=struct.unpack_from('<10I',data,10);assert all(50<=header[i]<=len(data) for i in [3,5,7,9]);nibs[str(path.relative_to(app))]=dict(size=len(data),sha256=sha(path))
assert len(nibs)==4 and (app/'Assets.car').stat().st_size>16
progress=re.findall(r'\*\*\* il2cpp build success[^\n]*?, (\d+) items updated, (\d+) evaluated',text);assert len(progress)==1
updated,evaluated=map(int,progress[0]);assert updated>0 and evaluated>=updated
products={}
for name in signature['products']:
    path=r/name;metadata=plistlib.loads((path/'Info.plist').read_bytes());binary=path/metadata['CFBundleExecutable'];products[name]=dict(identifier=metadata['CFBundleIdentifier'],binary_size=binary.stat().st_size,binary_sha256=sha(binary),resource_seal_sha256=sha(path/'_CodeSignature/CodeResources'),independent=checks[name])
record=dict(verified=True,milestone='Fresh Linux Unity project -> iOS export -> CocoaPods -> original xcodebuild -> original strict and independent signature checks',headless=True,Mac_used=False,Editor_version=export['editor_version'],Editor_sha256=export['editor_sha256'],generated_cpp_files=export['generated_cpp_files'],exported_project_before_CocoaPods_sha256=export['generated_project_sha256'],export_log_retained_privately=True,private_export_report=end['export_report'],private_export_log_sha256=export['log_sha256'],prepared_run=a.prepared_run,end_to_end_report=str(end_path.relative_to(r)),end_to_end_report_sha256=sha(end_path),native_build_output=str(output.relative_to(r)),native_build_output_sha256=sha(output),signature_report=a.signature_report,signature_report_sha256=sha(signature_path),application=end['application'],application_identifier=info['CFBundleIdentifier'],architecture='arm64',platform='iPhoneOS',build_version=platform,original_Xcode_CompileC_tasks=text.count('\nCompileC '),original_CodeSign_tasks=text.count('\nCodeSign '),IL2CPP_updated_tasks=updated,IL2CPP_evaluated_tasks=evaluated,native_Pod_symbol_linked=True,products=products,Storyboard_NIBs=nibs,Assets_car_sha256=sha(app/'Assets.car'),pod_lock_sha256=end['pod_lock_sha256'],original_CI_command=end['xcodebuild_command'],ad_hoc_signing_only=True,zsign_used=False,developer_provisioning_or_device_execution_verified=False,UE_project_verified=False,cold_reconstruction_verified=False,full_goal_complete=False,tool_sha256=sha(Path(__file__)))
record.update(ad_hoc_signing_only=end.get('ad_hoc_signing_only',True),
              signing_scope=end['signing_scope'],
              native_build_result=str((native/'result.json').relative_to(r)),
              native_build_result_sha256=sha(native/'result.json'),
              native_build_plan=str((native/'plan.json').relative_to(r)),
              native_build_plan_sha256=sha(native/'plan.json'),
              fresh_DerivedData=end.get('fresh_DerivedData',False),
              xcodebuild_invocations=end.get('xcodebuild_invocations'),
              single_invocation_fresh_DerivedData_complete_CI_verified=end.get('fresh_DerivedData') is True and end.get('xcodebuild_invocations')==1)
if not record['ad_hoc_signing_only']:
    independent_path=r/end['independent_signature_report'];independent=json.loads(independent_path.read_text())
    assert sha(independent_path)==end['independent_signature_report_sha256']
    assert independent['verified'] and independent['checks']==checks
    assert independent['public_certificate_SHA256']==end['public_certificate_SHA256']
    selected=plan['certificate_runtime'];assert selected['candidate']==signature['candidate']
    assert selected['candidate_sha256']==signature['candidate_sha256']==sha(r/selected['candidate'])
    selected_config=json.loads((r/selected['candidate']).read_text())
    record.update(public_certificate_SHA256=end['public_certificate_SHA256'],
                  self_generated_certificate_only=True,real_CMS_certificate_signature=True,
                  runtime_candidate=selected['candidate'],runtime_candidate_sha256=selected['candidate_sha256'],
                  stage=selected_config['inputs']['stage']['path'],
                  configuration=selected_config['inputs']['configuration']['path'],
                  independent_signature_report=end['independent_signature_report'],
                  independent_signature_report_sha256=sha(independent_path))
destination=r/a.report;assert not destination.exists();destination.write_text(json.dumps(record,indent=2)+'\n');print('FRESH_UNITY_END_TO_END_MILESTONE',destination)
