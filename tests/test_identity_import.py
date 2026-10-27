import json
import os
from pathlib import Path
import plistlib
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from linuxcode.identities import import_p12


class IdentityImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.fixture=cls.root/'fixture'
        # The fixture generator lives in the source checkpoint as well as a research workspace.
        source=Path(os.environ['LINUXCODE_P12_FIXTURE_GENERATOR'])
        with patch.dict(os.environ,{'P12_TEST_PASSWORD':'temporary fixture password'}):
            runpy.run_path(str(source))['prepare'](cls.fixture,'P12_TEST_PASSWORD')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_import_preserves_one_matching_identity_and_public_chain(self):
        workspace=self.root/'successful';workspace.mkdir()
        with patch.dict(os.environ,{'P12_TEST_PASSWORD':'temporary fixture password'}):
            result=import_p12(workspace,self.fixture/'identity.p12',Path('runtime/private/store.plist'),'P12_TEST_PASSWORD')
        path=workspace/result['identity_store'];store=plistlib.loads(path.read_bytes())
        self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual(path.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(len(store['items']),1);self.assertEqual(len(store['certificates']),2)
        self.assertEqual(store['items'][0]['certificate'],(self.fixture/'leaf.der').read_bytes())
        self.assertEqual(set(store['certificates']),{(self.fixture/'root.der').read_bytes(),(self.fixture/'intermediate.der').read_bytes()})
        key=workspace/'runtime/private/converted.der';key.write_bytes(store['items'][0]['privateKey']);key.chmod(0o600)
        data=b'imported signer cryptographic check'
        signature=subprocess.check_output(['openssl','dgst','-sha256','-sign',str(key),'-keyform','DER'],input=data)
        public=workspace/'public.pem';public.write_bytes(subprocess.check_output(['openssl','x509','-in',str(self.fixture/'leaf.pem'),'-pubkey','-noout']))
        sig=workspace/'signature';sig.write_bytes(signature)
        checked=subprocess.run(['openssl','dgst','-sha256','-verify',str(public),'-signature',str(sig)],input=data,capture_output=True)
        self.assertEqual(checked.returncode,0);self.assertFalse(result['certificate_chain_trust_verified'])
        self.assertNotIn('temporary fixture password',json.dumps(result));self.assertFalse(list((workspace/'runtime').glob('identity-import-*')))
    def test_wrong_password_leaves_no_store_or_decrypted_temporary_files(self):
        workspace=self.root/'wrong-password';workspace.mkdir()
        with patch.dict(os.environ,{'P12_TEST_PASSWORD':'wrong'}),self.assertRaisesRegex(RuntimeError,'Cannot decode P12'):
            import_p12(workspace,self.fixture/'identity.p12',Path('runtime/private/store.plist'),'P12_TEST_PASSWORD')
        self.assertFalse((workspace/'runtime/private/store.plist').exists());self.assertFalse(list((workspace/'runtime').glob('identity-import-*')))
    def test_existing_output_is_preserved(self):
        workspace=self.root/'existing';path=workspace/'runtime/private/store.plist';path.parent.mkdir(parents=True);path.write_bytes(b'existing user material')
        with self.assertRaisesRegex(RuntimeError,'already exists'):
            import_p12(workspace,self.fixture/'identity.p12',path,'P12_TEST_PASSWORD')
        self.assertEqual(path.read_bytes(),b'existing user material')
    def test_unsupported_ec_key_does_not_publish_an_unusable_store(self):
        workspace=self.root/'ec';workspace.mkdir();key=workspace/'ec.key';cert=workspace/'ec.pem';p12=workspace/'ec.p12'
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes',
                        '-keyout',str(key),'-out',str(cert),'-subj','/CN=Linuxcode EC fixture','-days','1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with patch.dict(os.environ,{'P12_TEST_PASSWORD':'temporary fixture password'}):
            subprocess.run(['openssl','pkcs12','-export','-inkey',str(key),'-in',str(cert),'-out',str(p12),
                            '-passout','env:P12_TEST_PASSWORD'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            with self.assertRaisesRegex(RuntimeError,'RSA PKCS1'):
                import_p12(workspace,p12,Path('runtime/private/store.plist'),'P12_TEST_PASSWORD')
        self.assertFalse((workspace/'runtime/private/store.plist').exists());self.assertFalse(list((workspace/'runtime').glob('identity-import-*')))
    def test_missing_password_and_outside_output_are_rejected(self):
        workspace=self.root/'missing';workspace.mkdir()
        with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(RuntimeError,'must be set'):
            import_p12(workspace,self.fixture/'identity.p12',Path('runtime/private/store.plist'),'P12_TEST_PASSWORD')
        with self.assertRaisesRegex(RuntimeError,'runtime directory'):
            import_p12(workspace,self.fixture/'identity.p12',Path('../outside.plist'),'P12_TEST_PASSWORD')


if __name__=='__main__':unittest.main()
