#!/usr/bin/env python3
"""Verify native bundle seals and real CMS using only the supplied leaf key."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,struct,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native-report',required=True);p.add_argument('--report',required=True);a=p.parse_args()
native=json.loads((r/a.native_report).read_text());assert native['original_codesign_frontend_completed'] and native['outer_status']==0
assert native['native_sign_status']==native['native_verify_status']==['0']
app=r/native['application'];source=app.parent;certificate=source/'certificate.pem';w=Path(tempfile.mkdtemp(prefix='native-certificate-verification-',dir=r/'runtime'));w.chmod(0o700)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();verify=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify']
der=subprocess.check_output(['openssl','x509','-in',str(certificate),'-outform','DER']);assert hashlib.sha256(der).hexdigest()==native['public_certificate_SHA256']
calls=[]
def cms_verifier(cd,cms,blobs):
    # No alternate CodeDirectory may go unchecked by this independent path.
    assert [k for k,v in blobs.items() if v[:4]==bytes.fromhex('fade0c02')]==[0], 'alternate CodeDirectories need a separate binding check'
    n=len(calls);directory=w/str(n);directory.mkdir();(directory/'CodeDirectory.bin').write_bytes(cd);(directory/'CMS.der').write_bytes(cms)
    base=['openssl','cms','-verify','-inform','DER','-in',str(directory/'CMS.der'),'-content',str(directory/'CodeDirectory.bin'),'-binary','-noverify','-nointern','-certfile',str(certificate),'-out',str(directory/'verified.bin')]
    res=subprocess.run(base,capture_output=True,text=True);(directory/'verify.log').write_text(res.stderr);assert res.returncode==0,res.stderr;assert (directory/'verified.bin').read_bytes()==cd
    altered=bytearray(cd);altered[-1]^=1;(directory/'CodeDirectory-tampered.bin').write_bytes(altered)
    bad=list(base);bad[bad.index('-content')+1]=str(directory/'CodeDirectory-tampered.bin');bad[bad.index('-out')+1]=str(directory/'tampered-output.bin');resbad=subprocess.run(bad,capture_output=True,text=True);(directory/'tampered.log').write_text(resbad.stderr);assert resbad.returncode!=0
    record=dict(verified=True,ad_hoc_flag=False,CodeDirectory_SHA256=hashlib.sha256(cd).hexdigest(),CMS_SHA256=hashlib.sha256(cms).hexdigest(),CMS_bytes=len(cms),tampered_CodeDirectory_rejected=True,certificate_chain_trust_verified=False)
    calls.append(record);return record
result=verify(app,cms_verifier=cms_verifier);assert calls
# These controls prove the independent seal verifier rejects actual changes.
controls=[]
for case in ['code-page','Info.plist','CodeResources']:
    target=w/case/app.name;target.parent.mkdir();shutil.copytree(app,target)
    import plistlib
    info=plistlib.loads((target/'Info.plist').read_bytes())
    if case=='code-page':
        path=target/info['CFBundleExecutable'];data=bytearray(path.read_bytes());data[0x4000]^=1;path.write_bytes(data)
    elif case=='Info.plist':info['CFBundleName']='modified';(target/'Info.plist').write_bytes(plistlib.dumps(info))
    else:
        path=target/'_CodeSignature/CodeResources';resources=plistlib.loads(path.read_bytes());resources['files2']['Injected.bin']={'hash2':bytes(32)};path.write_bytes(plistlib.dumps(resources))
    rejected=False
    try:verify(target,cms_verifier=cms_verifier)
    except (AssertionError,ValueError):rejected=True
    assert rejected,case;controls.append(dict(case=case,rejected=True))
record=dict(verified=True,native_report=a.native_report,native_report_sha256=sha(r/a.native_report),application=native['application'],original_codesign_and_strict_verify_completed=True,independent_bundle_verification=result,independent_tamper_controls=controls,public_certificate_SHA256=hashlib.sha256(der).hexdigest(),signing_scope='self-generated fixture certificate; no Apple developer provisioning or device trust',private_evidence_directory=str(w.relative_to(r)),verifier_sources={n:sha(r/n) for n in ['scripts/verify-adhoc-bundle.py','scripts/verify-certificate-bundle.py']},full_goal_complete=False)
out=r/a.report;assert not out.exists();out.write_text(json.dumps(record,indent=2)+'\n');print(out)
