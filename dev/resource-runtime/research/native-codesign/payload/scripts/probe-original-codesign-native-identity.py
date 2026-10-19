#!/usr/bin/env python3
"""Retry the unchanged Apple codesign binary with the current native identity stack."""
from pathlib import Path
import argparse,hashlib,json,os,plistlib,re,runpy,shlex,shutil,struct,subprocess,tempfile
parser=argparse.ArgumentParser();parser.add_argument('--native-codesign-stage');parser.add_argument('--closure-stage');parser.add_argument('--xattr-stage');parser.add_argument('--tamper-checks',action='store_true');parser.add_argument('--with-entitlements',action='store_true');args=parser.parse_args()
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='original-codesign-native-identity-',dir=r/'runtime'))
app=w/'iOSCocoaPodsSmoke.app';shutil.copytree(r/'runtime/ios-cocoapods-build/DerivedData/Build/Products/Debug-iphoneos/iOSCocoaPodsSmoke.app',app)
tool=r/'runtime/recovery/macOS Base System/usr/bin/codesign';guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r))
expected=None;sign_command=[guest(tool),'--force','--sign','-','--timestamp=none']
if args.with_entitlements:
    expected={'application-identifier':'org.linuxcode.iOSCocoaPodsSmoke','keychain-access-groups':['org.linuxcode.fixture'],'get-task-allow':True};entitlements=w/'entitlements.plist';entitlements.write_bytes(plistlib.dumps(expected));sign_command+=['--entitlements',guest(entitlements),'--generate-entitlement-der']
if args.tamper_checks:(app/'Sample.bin').write_bytes(bytes(range(256))*4)
script=w/'probe.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(sign_command+[guest(app)])+'\ns=$?\nprintf "ORIGINAL_CODESIGN_NATIVE_IDENTITY_SIGN_STATUS %s\\n" "$s"\nif [ "$s" -ne 0 ]; then exit "$s"; fi\n'+shlex.join([guest(tool),'--verify','--strict','--verbose=2',guest(app)])+'\ns=$?\nprintf "ORIGINAL_CODESIGN_NATIVE_IDENTITY_VERIFY_STATUS %s\\n" "$s"\nexit "$s"\n')
if args.native_codesign_stage:
    assert not (args.xattr_stage or args.closure_stage)
    m=runpy.run_path(str(r/'scripts/native-codesign-runtime-profile.py'));p=m['profile'](native_codesign_stage=args.native_codesign_stage,identity_store='runtime/local-identity-xcode-empty-v1/store.plist')
else:
    m=runpy.run_path(str(r/('scripts/xattr-runtime-profile.py' if args.xattr_stage else 'scripts/derq-runtime-profile.py')));p=m['profile'](**({'xattr_stage':args.xattr_stage} if args.xattr_stage else {}),derq_stage='artifacts/derq-original-v1-stage.json',identity_stage='artifacts/local-identity-store-readonly-v2-stage.json',identity_store='runtime/local-identity-xcode-empty-v1/store.plist',codesign_stage='artifacts/codesign-zsign-adhoc-v2-stage.json',trace=True)
command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='120';closure=None
if args.closure_stage:
    closure=json.loads((r/args.closure_stage).read_text())
    for name,digest in closure['files'].items():assert hashlib.sha256((r/name).read_bytes()).hexdigest()==digest,name
    for name,target in closure['links'].items():assert os.readlink(r/name)==target,name
    for prefix,leaf in [('DYLD_FRAMEWORK_PATH=','frameworks'),('DYLD_LIBRARY_PATH=','libraries')]:
        i=next(i for i,v in enumerate(command) if v.startswith(prefix));command[i]=prefix+'/Volumes/SystemRoot/workspace/'+closure['root']+'/'+leaf+':'+command[i].split('=',1)[1]
env=m['environment'](p)
command[-2:-2]=['LINUXCODE_CODE_SIGNER_TRACE=1']
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();sign=re.findall(r'^ORIGINAL_CODESIGN_NATIVE_IDENTITY_SIGN_STATUS (\d+)$',text,re.M);verify=re.findall(r'^ORIGINAL_CODESIGN_NATIVE_IDENTITY_VERIFY_STATUS (\d+)$',text,re.M);independent=None;independent_error=None;entitlements_verified=False;tamper=[]
verifier=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify']
if sign==['0'] and verify==['0']:
    try:
        independent=verifier(app)
        if expected is not None:
            info=plistlib.loads((app/'Info.plist').read_bytes());binary=(app/info['CFBundleExecutable']).read_bytes();at=32
            for _ in range(struct.unpack_from('<I',binary,16)[0]):
                cmd,size=struct.unpack_from('<II',binary,at)
                if cmd==0x1d:off,length=struct.unpack_from('<II',binary,at+8)
                at+=size
            signature=binary[off:off+length];blobs={}
            for i in range(struct.unpack_from('>I',signature,8)[0]):
                slot,offset=struct.unpack_from('>II',signature,12+8*i);size=struct.unpack_from('>I',signature,offset+4)[0];blobs[slot]=signature[offset:offset+size]
            assert struct.unpack_from('>I',blobs[5])[0]==0xfade7171 and struct.unpack_from('>I',blobs[7])[0]==0xfade7172
            xml=plistlib.loads(blobs[5][8:]);payload=blobs[7][8:];decoder='verify-apple-legacy-entitlements.py' if payload[:1]==b'1' else 'verify-entitlements-der.py';der=runpy.run_path(str(r/'scripts'/decoder))['decode'](payload);assert xml==der==expected and type(der['get-task-allow']) is bool;entitlements_verified=True
    except (AssertionError,ValueError,KeyError,struct.error) as error:independent_error=str(error) or type(error).__name__;independent=None
if independent and args.tamper_checks:
    for case in ['code-page','Info.plist','sealed-resource','added-resource']:
        target=w/case/'iOSCocoaPodsSmoke.app';target.parent.mkdir();shutil.copytree(app,target);info=plistlib.loads((target/'Info.plist').read_bytes())
        if case=='code-page':
            path=target/info['CFBundleExecutable'];b=bytearray(path.read_bytes());b[0x4000]^=1;path.write_bytes(b)
        elif case=='Info.plist':info['CFBundleName']='modified';(target/'Info.plist').write_bytes(plistlib.dumps(info))
        elif case=='sealed-resource':(target/'Sample.bin').write_bytes(b'modified')
        else:(target/'Added.bin').write_bytes(b'new unsealed file')
        rejected=False
        try:verifier(target)
        except (AssertionError,ValueError):rejected=True
        child_script=w/(case+'.sh');child_script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(tool),'--verify','--strict','--verbose=2',guest(target)])+'\ns=$?\nprintf "NATIVE_TAMPER_STATUS %s\\n" "$s"\nexit "$s"\n');child_log=w/(case+'.log');child_command=command[:-2]+['/bin/bash',guest(child_script)]
        with child_log.open('w') as out:child=subprocess.run(child_command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
        status=re.findall(r'^NATIVE_TAMPER_STATUS (\d+)$',child_log.read_text(),re.M);tamper.append(dict(case=case,independent_rejected=rejected,native_status=status,outer_status=child.returncode,log=str(child_log.relative_to(r)),log_sha256=hashlib.sha256(child_log.read_bytes()).hexdigest(),verified=rejected and status==['1'] and child.returncode==1))
ok=res.returncode==0 and sign==['0'] and verify==['0'] and bool(independent) and (expected is None or entitlements_verified) and (not args.tamper_checks or len(tamper)==4 and all(v['verified'] for v in tamper)) and 'REMOTE_SIGNING_UNIMPLEMENTED_CALLED' not in text
sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();report=dict(verified=ok,outer_status=res.returncode,native_sign_status=sign,native_verify_status=verify,independent_signature_verification=independent,original_binary=str(tool.relative_to(r)),original_binary_sha256=sha(tool),log=str(log.relative_to(r)),log_sha256=sha(log),script_sha256=sha(script),test_driver_sha256=sha(__file__),zsign_invoked=False,original_binary_invoked_by_absolute_path=True,graphical_environment_removed=True,certificate_or_device_trust_verified=False)
report['native_codesign_stage']=args.native_codesign_stage;report['xattr_stage']=args.xattr_stage;report['closure_stage']=args.closure_stage;report['closure']=closure
report.update(independent_error=independent_error,entitlements_verified=entitlements_verified,tamper_checks=tamper,remote_signing_unavailable_api_invoked='REMOTE_SIGNING_UNIMPLEMENTED_CALLED' in text,application=str(app.relative_to(r)))
(w/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(text[-3500:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
