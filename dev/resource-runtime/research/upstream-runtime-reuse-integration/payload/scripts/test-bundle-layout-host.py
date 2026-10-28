#!/usr/bin/env python3
"""Own zsign flat bundles transformed into Contents layout: host crypto controls.

This is not a native macOS codesign result. No signed code bytes, Info data or
sealed resource paths change during the layout transform. Existing verifiers
supply all Mach-O, resource and CMS parsing.
"""
from pathlib import Path
import copy,hashlib,json,plistlib,runpy,shutil,struct,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
w=Path(tempfile.mkdtemp(prefix='bundle-layout-host-',dir=r/'runtime'));w.chmod(0o700)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=r/'runtime/csops-metadata-probe-4ee509zq/unsigned';assert base.is_file()
module=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'));verify=module['verify'];layout=module['bundle_layout']
commands=[];log=w/'commands.log'
def command(args):
    commands.append(args)
    with log.open('a') as f:subprocess.run(args,cwd=r,stdout=f,stderr=subprocess.STDOUT,check=True)
command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN=LinuxcodeBundleLayoutHostCA','-days','1','-keyout',str(w/'ca-private.pem'),'-out',str(w/'ca.pem'),'-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign'])
command(['openssl','req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=LinuxcodeBundleLayoutHostControl','-keyout',str(w/'private.pem'),'-out',str(w/'request.pem')])
(w/'leaf-ext.cnf').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=codeSigning\n')
command(['openssl','x509','-req','-in',str(w/'request.pem'),'-CA',str(w/'ca.pem'),'-CAkey',str(w/'ca-private.pem'),'-CAcreateserial','-days','1','-extfile',str(w/'leaf-ext.cnf'),'-out',str(w/'certificate.pem')])
command(['openssl','pkcs12','-export','-inkey',str(w/'private.pem'),'-in',str(w/'certificate.pem'),'-certfile',str(w/'ca.pem'),'-passout','pass:','-out',str(w/'identity.p12')])
# zsign's certificate bundle mode requires signed team/app metadata. This is
# self-generated local test input, not Apple-issued provisioning or authorization.
(w/'owned-signer-metadata.plist').write_bytes(plistlib.dumps(dict(TeamIdentifier=['LAYOUTHOST'],Entitlements={'application-identifier':'LAYOUTHOST.org.linuxcode.bundle-layout.*','com.apple.developer.team-identifier':'LAYOUTHOST'})))
command(['openssl','cms','-sign','-binary','-nodetach','-in',str(w/'owned-signer-metadata.plist'),'-signer',str(w/'certificate.pem'),'-inkey',str(w/'private.pem'),'-outform','DER','-out',str(w/'owned-signer-metadata.cms')])
positive=[];apps=[]
for certificate in [False,True]:
 for fat in [False,True]:
    label=('certificate' if certificate else 'adhoc')+('-fat' if fat else '-thin')
    app=w/(label+'-flat.app');app.mkdir();(app/'Assets').mkdir();(app/'Assets/value.txt').write_bytes(b'owned sealed layout control\n')
    info=dict(CFBundleExecutable='LayoutSmoke',CFBundleIdentifier='org.linuxcode.bundle-layout.'+label,CFBundlePackageType='APPL',CFBundleName='OwnedLayoutFixture')
    (app/'Info.plist').write_bytes(plistlib.dumps(info));binary=base.read_bytes()
    if fat:
        cpu,subtype=struct.unpack_from('<II',binary,4);binary=struct.pack('>7I',0xcafebabe,1,cpu,subtype,0x4000,len(binary),14).ljust(0x4000,b'\0')+binary
    (app/'LayoutSmoke').write_bytes(binary);(app/'LayoutSmoke').chmod(0o755)
    sign=[str(r/'runtime/zsign-linux/zsign'),'-f','-b',info['CFBundleIdentifier']]
    sign+=['-k',str(w/'identity.p12'),'-c',str(w/'certificate.pem'),'-m',str(w/'owned-signer-metadata.cms')] if certificate else ['-a']
    command(sign+[str(app)])
    mac=w/(label+'-mac.app');shutil.copytree(app,mac);contents=mac/'Contents';contents.mkdir()
    for entry in list(mac.iterdir()):
        if entry!=contents:entry.rename(contents/entry.name)
    (contents/'MacOS').mkdir();(contents/'LayoutSmoke').rename(contents/'MacOS/LayoutSmoke')
    assert (app/'LayoutSmoke').read_bytes()==(contents/'MacOS/LayoutSmoke').read_bytes()
    assert (app/'Info.plist').read_bytes()==(contents/'Info.plist').read_bytes()
    assert (app/'_CodeSignature/CodeResources').read_bytes()==(contents/'_CodeSignature/CodeResources').read_bytes()
    if not certificate:
        positive += [dict(name=label+'-flat',signature=verify(app)),dict(name=label+'-mac',signature=verify(mac))]
    else:apps += [app,mac]
report=w/'certificate-checks.json'
args=['python3',str(r/'scripts/verify-native-certificate-products.py'),'--certificate',str(w/'certificate.pem'),'--report',str(report),'--skip-tamper-controls']
for app in apps:args+=['--product',str(app)]
command(args);cert=json.loads(report.read_text());assert cert['verified'] and not cert['tamper_controls_executed'];assert len(cert['checks'])==4
negative=[]
for case in ['Info.plist','code','resource','CodeResources','ambiguous-layout','outside-Contents']:
    target=w/('bad-'+case+'.app');shutil.copytree(w/'adhoc-thin-mac.app',target);chosen=layout(target)
    if case=='Info.plist':
        info=chosen['info'];info['CFBundleName']='changed';chosen['info_path'].write_bytes(plistlib.dumps(info))
    elif case=='ambiguous-layout':shutil.copy2(chosen['info_path'],target/'Info.plist')
    elif case=='outside-Contents':(target/'outside.txt').write_bytes(b'unsealed')
    else:
        path=chosen['executable'] if case=='code' else chosen['root']/'Assets/value.txt' if case=='resource' else chosen['resources']
        data=bytearray(path.read_bytes());at=4096 if case=='code' else 0;data[at]^=1;path.write_bytes(data)
    rejected=False
    try:verify(target)
    except (AssertionError,ValueError,plistlib.InvalidFileException):rejected=True
    assert rejected,case
    negative.append(dict(case=case,rejected=True))
# Exercise the existing real CMS callback on targeted Mac-layout negatives too.
for case in ['Info.plist','code','resource']:
    target=w/('bad-certificate-'+case+'.app');shutil.copytree(w/'certificate-thin-mac.app',target);chosen=layout(target)
    if case=='Info.plist':
        info=chosen['info'];info['CFBundleName']='changed';chosen['info_path'].write_bytes(plistlib.dumps(info))
    else:
        path=chosen['executable'] if case=='code' else chosen['root']/'Assets/value.txt'
        data=bytearray(path.read_bytes());data[4096 if case=='code' else 0]^=1;path.write_bytes(data)
    cmd=['python3',str(r/'scripts/verify-native-certificate-products.py'),'--certificate',str(w/'certificate.pem'),'--product',str(target),'--report',str(w/('rejected-'+case+'.json')),'--skip-tamper-controls']
    commands.append(cmd)
    with log.open('a') as stream:status=subprocess.run(cmd,cwd=r,stdout=stream,stderr=subprocess.STDOUT).returncode
    assert status!=0 and not (w/('rejected-'+case+'.json')).exists(),case
    negative.append(dict(case='certificate-mac-'+case,rejected=True,real_CMS_callback_path=True))
result=dict(verified=True,host_only=True,native_macOS_signature_claimed=False,fixtures='Own Mach-O signed as flat apps using Linux zsign, then unchanged cryptographic payload transformed into Contents/MacOS layout',code_Info_CodeResources_bytes_unchanged_by_transform=True,existing_parsers_reused=True,ad_hoc_positive=positive,certificate_positive=cert['checks'],certificate_CMS_checks=cert['CMS_checks'],Apple_provisioning_or_identity_trust_claimed=False,negative_controls=negative,commands=commands,private_generated_identity_not_for_publication=True,files={str(p.relative_to(r)):sha(p) for p in [Path(__file__),r/'scripts/verify-adhoc-bundle.py',r/'scripts/verify-native-certificate-products.py',base,report,log]},full_native_App_codesign_success=False)
(w/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(w/'result.json')
