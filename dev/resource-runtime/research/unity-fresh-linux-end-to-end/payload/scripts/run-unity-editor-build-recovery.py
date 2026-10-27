#!/usr/bin/env python3
"""Retry only the failed build boundary on private copies of a real Unity export."""
from pathlib import Path
import argparse,hashlib,json,os,plistlib,re,runpy,shutil,struct,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prepared-run',required=True);p.add_argument('--failed-native-run',required=True)
p.add_argument('--candidate',required=True);p.add_argument('--identity-store',required=True)
a=p.parse_args();original=r/a.prepared_run;prior=json.loads((original/'end-to-end-result.json').read_text())
assert prior['Unity_export_verified'] and prior['CocoaPods_verified'] and not prior['verified']
failed=r/a.failed_native_run;failure=json.loads((failed/'result.json').read_text());assert failure['native_exit_status']==0 and failure['outer_exit_status']!=0
assert '** BUILD SUCCEEDED **' in (failed/'output.log').read_text()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
prepared=json.loads((original/'prepared.json').read_text());ios=r/prepared['export'];dd=original/'DerivedData'
assert (ios/'Podfile.lock').read_bytes()==(ios/'Pods/Manifest.lock').read_bytes()
assert sha(ios/'Podfile.lock')==prior['pod_lock_sha256']
apps=list((dd/'Build/Products/Debug-iphoneos').glob('*.app'));assert len(apps)==1;old_app=apps[0]
info=plistlib.loads((old_app/'Info.plist').read_bytes())
guarded=[old_app/info['CFBundleExecutable'],old_app/'_CodeSignature/CodeResources',dd/'Build/Intermediates.noindex/XCBuildData/build.db',ios/'Unity-iPhone.xcodeproj/project.pbxproj']
guards={str(path.relative_to(r)):sha(path) for path in guarded}
folder=Path(tempfile.mkdtemp(prefix='unity-editor-build-recovery-',dir=r/'runtime'));folder.chmod(0o700)
mappings=[]
for source,leaf in [(ios,'ios'),(dd,'DerivedData')]:
    destination=folder/leaf;subprocess.run(['cp','-a','--reflink=auto',str(source),str(destination)],check=True)
    mappings.append(dict(source=str(destination.relative_to(r)),target=str(source.relative_to(r))))
bindings=folder/'workspace-bindings.json';bindings.write_text(json.dumps(mappings,indent=2)+'\n')
argv=json.loads((original/'xcodebuild-command.json').read_text());assert argv.pop(0)=='xcodebuild'
argv=[v.replace(str(r)+'/', '/Volumes/SystemRoot/workspace/') for v in argv]
arguments=folder/'xcode-arguments.json';arguments.write_text(json.dumps(argv,indent=2)+'\n')
candidate=json.loads((r/a.candidate).read_text());command=json.loads((r/'config/unity-main-stack-clean-dd83-v2-command.json').read_text())
def option(key,value):command[command.index(key)+1]=value
option('--private-procfs-stage',candidate['inputs']['stage']['path']);option('--direct-resource-environment',candidate['inputs']['configuration']['path']);option('--identity-store',a.identity_store);option('--xcode-arguments-file',str(arguments.relative_to(r)));option('--timeout-seconds','900')
command+=['--certificate-candidate',a.candidate,'--workspace-bind-stage','artifacts/workspace-bind-launcher-certificate-v1-stage.json','--workspace-bindings',str(bindings.relative_to(r)),'--skip-uti-diagnostic']
(folder/'command.json').write_text(json.dumps(command,indent=2)+'\n')
state=dict(verified=False,prepared_run=a.prepared_run,original_export_report=prior['export_report'],original_export_and_CocoaPods_verified=True,failed_first_native_run=a.failed_native_run,first_native_build_succeeded_but_cleanup_failed=True,compilation_cache_reused=True,original_guards=guards,candidate=a.candidate,command=command,Mac_used=False,headless=True,ad_hoc_signing_only=True,developer_provisioning_or_device_execution_verified=False,full_goal_complete=False)
report=folder/'result.json'
def save():report.write_text(json.dumps(state,indent=2)+'\n')
def run(cmd,log):
    with log.open('w') as out:result=subprocess.run(cmd,cwd=r,stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Status '+str(result.returncode)+': '+str(log.relative_to(r)))
    return log.read_text(errors='replace')
save();print('RUNNING',folder.relative_to(r),flush=True)
try:
    before={f for f in (r/'artifacts').glob('xcode-service-runtime-*.json')}
    run(command,folder/'build-driver.log')
    after={f for f in (r/'artifacts').glob('xcode-service-runtime-*.json')};proof=[]
    for path in after-before:
        d=json.loads(path.read_text())
        if d.get('xcode_arguments')==argv and d.get('native_xcode_status')==['0'] and d.get('exit_status')==0:proof.append(path)
    assert len(proof)==1;build=json.loads(proof[0].read_text());assert sha(r/build['log'])==build['log_sha256'] and '** BUILD SUCCEEDED **' in (r/build['log']).read_text()
    state.update(original_xcodebuild_and_outer_cleanup_verified=True,build_report=str(proof[0].relative_to(r)));save()
    app=folder/'DerivedData/Build/Products/Debug-iphoneos'/old_app.name;products=[app,*list((app/'Frameworks').glob('*.framework'))]
    native_command=['python3','scripts/probe-native-certificate-products.py','--candidate',a.candidate,'--identity-store',a.identity_store]
    for product in products:native_command+=['--product',str(product.relative_to(r))]
    output=run(native_command,folder/'native-signature-check.log');match=re.findall(r'^EVIDENCE (.+/result.json)$',output,re.M);assert len(match)==1
    strict=Path(match[0]);strict_data=json.loads(strict.read_text());assert strict_data['verified'] and strict_data['outer_status']==0 and len(strict_data['products'])==len(products)
    verify=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify'];checks={str(path.relative_to(r)):verify(path) for path in products}
    framework=app/'Frameworks/UnityFramework.framework/UnityFramework';symbols=subprocess.check_output(['llvm-nm-19','--defined-only',str(framework)],text=True);assert re.search(r'\b_LinuxcodePodAnswer$',symbols,re.M)
    metadata=plistlib.loads((app/'Info.plist').read_bytes());binary=app/metadata['CFBundleExecutable'];data=binary.read_bytes();assert struct.unpack_from('<II',data)==(0xfeedfacf,0x100000c)
    cursor=32;platform=None
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        kind,length=struct.unpack_from('<II',data,cursor)
        if kind==0x32:platform=struct.unpack_from('<III',data,cursor+8)
        cursor+=length
    assert platform and platform[0]==2 and metadata['CFBundleSupportedPlatforms']==['iPhoneOS']
    assert all(sha(r/path)==digest for path,digest in guards.items())
    state.update(verified=True,original_guards_preserved=True,original_codesign_strict_verified=True,native_signature_report=str(strict.relative_to(r)),native_signature_report_sha256=sha(strict),independent_product_checks=checks,native_Pod_symbol_linked=True,application=str(app.relative_to(r)),application_identifier=metadata['CFBundleIdentifier'],application_sha256=sha(binary),architecture='arm64',platform='iPhoneOS',build_version=platform,original_CI_arguments=argv)
    save();print('UNITY_EDITOR_RECOVERED_END_TO_END_VERIFIED',report)
except Exception as error:
    state['failure']=str(error);state['original_guards_preserved']=all(sha(r/path)==digest for path,digest in guards.items());save();raise
