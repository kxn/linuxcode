"""Import caller-provided PKCS#12 into the native read-only RSA identity store."""
from pathlib import Path
import hashlib
import os
import plistlib
import re
import subprocess
import tempfile


def import_p12(workspace, source, output, password_env, label='CI signing identity',
               certificate_sha256=None, legacy=False):
    workspace=Path(workspace).resolve();source=Path(source).expanduser().resolve(strict=True)
    output=(workspace/output).resolve();runtime=workspace/'runtime'
    if not output.is_relative_to(runtime) or output==runtime:
        raise RuntimeError('Identity store output must be inside the workspace runtime directory.')
    if output.exists():raise RuntimeError('Identity store already exists; choose a new output file.')
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',password_env) or password_env not in os.environ:
        raise RuntimeError('The named password environment variable must be set; an empty value is allowed.')
    if not label:raise RuntimeError('Identity label must not be empty.')
    if certificate_sha256 and not re.fullmatch('[0-9a-fA-F]{64}',certificate_sha256):
        raise RuntimeError('Certificate SHA256 must contain 64 hexadecimal characters.')
    runtime.mkdir(parents=True,exist_ok=True)
    def openssl(args, data=None, message='Cannot decode certificate material.'):
        result=subprocess.run(['openssl',*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if result.returncode:raise RuntimeError(message)
        return result.stdout
    with tempfile.TemporaryDirectory(prefix='identity-import-',dir=runtime) as name:
        private=Path(name);private.chmod(0o700);bundle=private/'bundle.pem'
        # OpenSSL opens this already-private file; no decrypted key reaches stdout.
        bundle.touch(mode=0o600)
        openssl(['pkcs12','-in',str(source),'-passin','env:'+password_env,'-nodes','-out',str(bundle),
                 *(['-legacy'] if legacy else [])],message='Cannot decode P12; check the password and cipher support.')
        data=bundle.read_bytes()
        keys=re.findall(rb'-----BEGIN ((?:RSA |EC )?PRIVATE KEY)-----.*?-----END \1-----',data,re.S)
        blocks=re.findall(rb'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----.*?-----END (?:RSA |EC )?PRIVATE KEY-----',data,re.S)
        if len(keys)!=1 or len(blocks)!=1:raise RuntimeError('P12 must contain exactly one private key.')
        key=private/'key.pem';key.touch(mode=0o600);key.write_bytes(blocks[0]+b'\n')
        raw=private/'key.der';raw.touch(mode=0o600)
        openssl(['rsa','-in',str(key),'-traditional','-outform','DER','-out',str(raw)],
                message='The current native identity store supports RSA PKCS1 private keys only.')
        public=openssl(['rsa','-inform','DER','-in',str(raw),'-pubout','-outform','DER'])
        certs=[]
        for pem in re.findall(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',data,re.S):
            der=openssl(['x509','-outform','DER'],pem)
            if any(row['der']==der for row in certs):continue
            pub=openssl(['x509','-pubkey','-noout'],pem)
            spki=openssl(['pkey','-pubin','-outform','DER'],pub)
            certs.append(dict(der=der,sha256=hashlib.sha256(der).hexdigest(),matches=spki==public))
        matches=[row for row in certs if row['matches'] and
                 (not certificate_sha256 or row['sha256']==certificate_sha256.lower())]
        if len(matches)!=1:
            raise RuntimeError('Expected one certificate matching the private key; use --certificate-sha256 for an ambiguous P12.')
        leaf=matches[0];additional=[row['der'] for row in certs if row is not leaf]
        store=dict(version=1,locked=False,items=[dict(label=label,certificate=leaf['der'],privateKey=raw.read_bytes())])
        if additional:store['certificates']=additional
        payload=plistlib.dumps(store,fmt=plistlib.FMT_BINARY)
        if len(payload)>16*1024*1024:raise RuntimeError('Identity store exceeds the native 16 MiB limit.')
        output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,pending=tempfile.mkstemp(prefix='.identity-',dir=output.parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
            # Atomic creation without replacing an existing or concurrently created store.
            os.link(pending,output)
        finally:Path(pending).unlink(missing_ok=True)
    return dict(identity_store=str(output.relative_to(workspace)),signing_identity_SHA1=hashlib.sha1(leaf['der']).hexdigest().upper(),
                certificate_SHA256=leaf['sha256'],additional_public_certificates=len(additional),
                key_type='RSA PKCS1 DER',read_only_store=True,encrypted_store=False,
                certificate_chain_trust_verified=False,developer_provisioning_or_device_trust_verified=False)
