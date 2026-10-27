#!/usr/bin/env python3
"""Create a private synthetic root/intermediate/signing-leaf P12 for compatibility tests."""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile


def prepare(folder, password_env):
    folder=Path(folder);folder.mkdir(mode=0o700,parents=True,exist_ok=True);folder.chmod(0o700)
    def run(*args):subprocess.run(['openssl',*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    run('req','-x509','-newkey','rsa:2048','-nodes','-keyout',folder/'root.key','-out',folder/'root.pem',
        '-subj','/CN=Linuxcode Test Root','-days','2','-addext','basicConstraints=critical,CA:TRUE,pathlen:1',
        '-addext','keyUsage=critical,keyCertSign,cRLSign')
    for name,subject,issuer,extensions in [
        ('intermediate','Linuxcode Test Intermediate','root','basicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\n'),
        ('leaf','Linuxcode Imported Signing Fixture','intermediate','basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=codeSigning\n')]:
        run('req','-new','-newkey','rsa:2048','-nodes','-keyout',folder/(name+'.key'),'-out',folder/(name+'.csr'),'-subj','/CN='+subject)
        ext=folder/(name+'.ext');ext.write_text(extensions+'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
        run('x509','-req','-in',folder/(name+'.csr'),'-CA',folder/(issuer+'.pem'),'-CAkey',folder/(issuer+'.key'),
            '-CAcreateserial','-out',folder/(name+'.pem'),'-days','2','-extfile',ext)
    chain=folder/'chain.pem';chain.write_bytes((folder/'intermediate.pem').read_bytes()+(folder/'root.pem').read_bytes())
    run('pkcs12','-export','-inkey',folder/'leaf.key','-in',folder/'leaf.pem','-certfile',chain,
        '-name','Linuxcode P12 fixture','-passout','env:'+password_env,'-out',folder/'identity.p12')
    for name in ['root','intermediate','leaf']:run('x509','-in',folder/(name+'.pem'),'-outform','DER','-out',folder/(name+'.der'))
    for path in folder.iterdir():path.chmod(0o600)
    return folder


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--password-env',required=True);a=p.parse_args()
    assert a.password_env in os.environ
    r=Path(__file__).resolve().parent.parent
    f=Path(tempfile.mkdtemp(prefix='p12-chain-fixture-',dir=r/'runtime'));prepare(f,a.password_env);print(f.relative_to(r))
