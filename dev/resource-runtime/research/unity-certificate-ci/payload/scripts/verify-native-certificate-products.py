#!/usr/bin/env python3
"""Independently verify certificate CMS, pages and seals of actual build products."""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import runpy
import subprocess
import tempfile

r = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--certificate', required=True)
p.add_argument('--product', action='append', required=True)
p.add_argument('--report', required=True)
a = p.parse_args()
out = r / a.report; assert not out.exists()
certificate = (r / a.certificate).resolve(strict=True)
der = subprocess.check_output(['openssl', 'x509', '-in', str(certificate), '-outform', 'DER'])
folder = Path(tempfile.mkdtemp(prefix='certificate-products-verification-', dir=r / 'runtime')); folder.chmod(0o700)
bundle = runpy.run_path(str(r / 'scripts/verify-adhoc-bundle.py'))['verify']
generic = runpy.run_path(str(r / 'scripts/verify-adhoc-generic-file.py'))['verify']
binding = runpy.run_path(str(r / 'scripts/verify-cms-code-directories.py'))['verify_binding']
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
calls = []

def cms_verifier(cd, cms, blobs):
    d = folder / str(len(calls)); d.mkdir()
    (d / 'cd').write_bytes(cd); (d / 'cms').write_bytes(cms)
    command = ['openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(d / 'cms'),
               '-content', str(d / 'cd'), '-binary', '-noverify', '-nointern',
               '-certfile', str(certificate), '-out', str(d / 'verified')]
    res = subprocess.run(command, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (d / 'verified').read_bytes() == cd
    agility = binding(cms, blobs)
    alternate_controls = []
    for slot in agility['bound_CodeDirectory_slots']:
        if slot == 0: continue
        modified = dict(blobs); altered_cd = bytearray(blobs[slot]); altered_cd[-1] ^= 1; modified[slot] = bytes(altered_cd)
        rejected = False
        try: binding(cms, modified)
        except AssertionError: rejected = True
        assert rejected, 'altered alternate CodeDirectory accepted'
        alternate_controls.append(dict(slot=slot, rejected=True))
    altered = bytearray(cd); altered[-1] ^= 1; (d / 'altered').write_bytes(altered)
    command[command.index('-content') + 1] = str(d / 'altered')
    res = subprocess.run(command, capture_output=True)
    assert res.returncode != 0, 'altered CodeDirectory accepted'
    result = dict(verified=True, **agility, alternate_CodeDirectory_tamper_controls=alternate_controls, CodeDirectory_SHA256=hashlib.sha256(cd).hexdigest(),
                  CMS_SHA256=hashlib.sha256(cms).hexdigest(), CMS_bytes=len(cms),
                  modified_CodeDirectory_rejected=True, certificate_chain_trust_verified=False)
    calls.append(result)
    return result

checks = {}
for name in a.product:
    path = (r / name).resolve(strict=True); assert path.is_relative_to(r / 'runtime')
    checks[name] = bundle(path, cms_verifier=cms_verifier) if path.is_dir() else generic(path, cms_verifier=cms_verifier)
controls = []
# Tamper with separate reflink copies. Keep every signed build product intact.
app = next((r / name for name in a.product if name.endswith('.app')), None)
if app:
    for case in ['code-page', 'Info.plist', 'CodeResources', 'embedded-framework']:
        target = folder / case / app.name; target.parent.mkdir()
        subprocess.run(['cp', '-a', '--reflink=auto', str(app), str(target)], check=True)
        info = plistlib.loads((target / 'Info.plist').read_bytes())
        if case == 'Info.plist':
            info['CFBundleName'] = 'tampered'; (target / 'Info.plist').write_bytes(plistlib.dumps(info))
        elif case == 'CodeResources':
            path = target / '_CodeSignature/CodeResources'; data = path.read_bytes(); path.write_bytes(data + b'\n')
        else:
            path = target / info['CFBundleExecutable']
            if case == 'embedded-framework':
                frameworks = sorted((target / 'Frameworks').glob('*.framework'))
                assert frameworks
                fw = frameworks[0]; fi = plistlib.loads((fw / 'Info.plist').read_bytes()); path = fw / fi['CFBundleExecutable']
            data = bytearray(path.read_bytes()); assert len(data) > 0x4000; data[0x4000] ^= 1; path.write_bytes(data)
        rejected = False
        try: bundle(target, cms_verifier=cms_verifier)
        except (AssertionError, ValueError): rejected = True
        assert rejected, case
        controls.append(dict(case=case, rejected=True))
record = dict(verified=True, checks=checks, CMS_checks=calls, tamper_controls=controls,
              public_certificate_SHA256=hashlib.sha256(der).hexdigest(),
              private_evidence_directory=str(folder.relative_to(r)),
              signing_scope='self-generated certificate; no developer provisioning or device trust',
              sources={name: sha(r / name) for name in ['scripts/verify-native-certificate-products.py',
                       'scripts/verify-adhoc-bundle.py', 'scripts/verify-adhoc-generic-file.py', 'scripts/verify-cms-code-directories.py']},
              full_goal_complete=False)
out.write_text(json.dumps(record, indent=2) + '\n'); print(out)
