#!/usr/bin/env python3
"""Actual Linux Unity export -> Darwin CocoaPods -> original xcodebuild -> signature checks."""
from pathlib import Path
import argparse,hashlib,json,os,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prepared-run',required=True);p.add_argument('--editor');p.add_argument('--identity-store',required=True)
p.add_argument('--candidate',default='config/native-certificate-candidate-v6.json')
p.add_argument('--ad-hoc-test-signing',action='store_true',required=True,help='Explicit generated smoke fixture only; no provisioning/device trust claim')
a=p.parse_args();folder=(r/a.prepared_run).resolve();assert folder.is_relative_to(r/'runtime');prepared=json.loads((folder/'prepared.json').read_text());project=r/prepared['export'];report=folder/'end-to-end-result.json';assert not report.exists()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest();state=dict(verified=False,host='Linux x86_64',Mac_used=False,headless=True,prepared_run=a.prepared_run,Unity_export_verified=False,CocoaPods_verified=False,original_xcodebuild_verified=False,signing_scope='explicit ad-hoc test fixture',developer_provisioning_or_device_trust_verified=False)
def save():report.write_text(json.dumps(state,indent=2)+'\n')
def run(command,log,cwd=r,env=None):
    with log.open('w') as out:result=subprocess.run(command,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Stage failed with status '+str(result.returncode)+': '+str(log.relative_to(r)))
    return log.read_text(errors='replace')
save()
try:
    previous=[]
    for path in folder.glob('attempt-*/result.json'):
        record=json.loads(path.read_text())
        if record.get('verified') and record['generated_project_sha256']==sha(project/'Unity-iPhone.xcodeproj/project.pbxproj'):previous.append(path)
    if not previous:
        cmd=['python3','scripts/run-unity-editor-export.py','--prepared-run',a.prepared_run]+(['--editor',a.editor] if a.editor else [])
        run(cmd,folder/'export-driver.log')
        previous=[path for path in folder.glob('attempt-*/result.json') if json.loads(path.read_text()).get('verified')]
    assert previous;state.update(Unity_export_verified=True,export_report=str(previous[-1].relative_to(r)));save()
    assert not (project/'Pods').exists(),'Use a fresh prepared export; never reinstall over preserved Pods'
    pod=folder/'pod-install';pod.mkdir();script=pod/'run.sh';guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
    script.write_text('#!/bin/bash\nset -e\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\ncd '+shlex.quote(guest(project))+'\nset +e\npod install --no-repo-update\ns=$?\nprintf "UNITY_EDITOR_POD_INSTALL_STATUS %s\\n" "$s"\nexit "$s"\n')
    candidate=json.loads((r/a.candidate).read_text());module=runpy.run_path(str(r/'scripts/private-procfs-runtime-profile.py'));profile=module['profile'](stage=candidate['inputs']['stage']['path'])
    cmd=[v for v in profile['command'][:-2] if not v.startswith(('DYLD_LIBRARY_PATH=','DYLD_FRAMEWORK_PATH='))]+['/bin/bash',guest(script)];cmd[3]='300'
    text=run(cmd,pod/'run.log',env=module['environment'](profile));assert re.search(r'^UNITY_EDITOR_POD_INSTALL_STATUS 0$',text,re.M)
    assert (project/'Podfile.lock').read_bytes()==(project/'Pods/Manifest.lock').read_bytes();assert 'LinuxcodeSmoke (1.0.0)' in (project/'Podfile.lock').read_text();assert (project/'Unity-iPhone.xcworkspace/contents.xcworkspacedata').is_file()
    state.update(CocoaPods_verified=True,pod_log=str((pod/'run.log').relative_to(r)),pod_lock_sha256=sha(project/'Podfile.lock'));save()
    launcher=folder/'launcher';cli=r/'distribution/linuxcode/linuxcode.py'
    run(['python3',str(cli),'--workspace',str(r),'--state',str(launcher),'adopt','--certificate-candidate',a.candidate,'--identity-store',a.identity_store],folder/'adopt.log')
    env=os.environ.copy();env['PATH']=str(launcher/'bin')+':'+env['PATH'];env['LINUXCODE_BUILD_TIMEOUT_SECONDS']='7200'
    for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
    dd=folder/'DerivedData';command=['xcodebuild','-workspace',str(project/'Unity-iPhone.xcworkspace'),'-scheme','Unity-iPhone','-configuration','Debug','-sdk','iphoneos','-destination','generic/platform=iOS','-derivedDataPath',str(dd),'CODE_SIGNING_ALLOWED=YES','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY=-','AD_HOC_CODE_SIGNING_ALLOWED=YES','DEVELOPMENT_TEAM=','CODE_SIGN_STYLE=Manual','PROVISIONING_PROFILE_REQUIRED=NO','PROVISIONING_PROFILE_SUPPORTED=NO','build']
    (folder/'xcodebuild-command.json').write_text(json.dumps(command,indent=2)+'\n');text=run(command,folder/'xcodebuild.log',cwd=project,env=env);assert '** BUILD SUCCEEDED **' in text
    apps=list((dd/'Build/Products/Debug-iphoneos').glob('*.app'));assert len(apps)==1;app=apps[0];frameworks=list((app/'Frameworks').glob('*.framework'));products=[app,*frameworks]
    state.update(original_xcodebuild_verified=True,xcodebuild_log=str((folder/'xcodebuild.log').relative_to(r)),application=str(app.relative_to(r)),xcodebuild_command=command);save()
    cmd=['python3','scripts/probe-native-certificate-products.py','--candidate',a.candidate,'--identity-store',a.identity_store]
    for product in products:cmd+=['--product',str(product.relative_to(r))]
    run(cmd,folder/'native-signature-check.log')
    independent=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify'];checks={str(product.relative_to(r)):independent(product) for product in products}
    unity=app/'Frameworks/UnityFramework.framework/UnityFramework';symbols=subprocess.check_output(['llvm-nm-19','--defined-only',str(unity)],text=True)
    assert re.search(r'\b_LinuxcodePodAnswer$',symbols,re.M),'The local Pod must actually link into the Unity framework'
    state.update(verified=True,original_codesign_strict_verified=True,independent_product_checks=checks,native_Pod_symbol_linked=True,device_execution_verified=False);save();print('UNITY_EDITOR_END_TO_END_VERIFIED',report)
except Exception as error:
    state['failure']=str(error);save();raise
