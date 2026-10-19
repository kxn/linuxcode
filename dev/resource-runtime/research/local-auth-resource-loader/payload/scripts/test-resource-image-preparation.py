#!/usr/bin/env python3
"""Exercise candidate preparation guards in an isolated copy against real cache metadata.

No Darling process is started. Original cache/library inputs are read through
symlinks; manifests, history, audits and output reports belong to this test.
"""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest

root = Path(__file__).resolve().parent.parent


class CandidatePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='candidate-preparation-test-', dir=root/'runtime')
        cls.folder = Path(cls.temporary.name)
        cls.workspace = cls.folder/'workspace'
        for directory in ['scripts', 'config', 'runtime/source-input-history', 'artifacts']:
            (cls.workspace/directory).mkdir(parents=True, exist_ok=True)
        for name in ['prepare-resource-image-candidate.py', 'dsc-image.py', 'inspect-dsc-constants.py']:
            shutil.copy2(root/'scripts'/name, cls.workspace/'scripts'/name)
        (cls.workspace/'vendor').symlink_to(root/'vendor', target_is_directory=True)
        for name in ['fullsystem', 'fullsystem-libraries', 'rebuilt-rapport-resource-v1']:
            (cls.workspace/'runtime'/name).symlink_to(root/'runtime'/name, target_is_directory=True)
        cls.manifest = cls.workspace/'config/coregraphics-image-pins.json'
        cls.original_manifest = (root/'config/coregraphics-image-pins.json').read_bytes()
        cls.audit = json.loads((root/'artifacts/rapport-original-import-audit-v1.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.manifest.write_bytes(self.original_manifest)
        self.history = self.workspace/'runtime/source-input-history/manifest.json'
        self.history.write_text('{}\n')

    def prepare(self, audit, label):
        target = 'candidate-preparation-'+label
        source = self.workspace/'artifacts'/(label+'-audit.json')
        source.write_text(json.dumps(audit, indent=2)+'\n')
        command = ['python3', str(self.workspace/'scripts/prepare-resource-image-candidate.py'),
            '--from-target', 'rapport-resource-v1', '--exact-import-audit', str(source), '--target', target]
        result = subprocess.run(command, cwd=self.workspace, capture_output=True, text=True)
        return result, target

    def reject(self, audit, label):
        result, target = self.prepare(audit, label)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.manifest.read_bytes(), self.original_manifest)
        self.assertEqual(self.history.read_text(), '{}\n')
        self.assertFalse((self.workspace/'artifacts'/(target+'-input.json')).exists())
        self.assertFalse((self.workspace/'runtime'/('rebuilt-'+target)).exists())

    def test_exact_audit_and_typed_alias_create_new_frozen_pin(self):
        result, target = self.prepare(self.audit, 'positive')
        self.assertEqual(result.returncode, 0, result.stderr)
        pin = json.loads(self.manifest.read_text())[target]
        self.assertEqual(len(pin['cache_imports']), 228)
        report = json.loads((self.workspace/'artifacts'/(target+'-input.json')).read_text())
        self.assertEqual(report['typed_class_aliases'][0]['original_name'], '_TtCs20__StaticArrayStorage')
        self.assertFalse(report['reconstruction_attempted'])
        old_sha = hashlib.sha256(self.original_manifest).hexdigest()
        self.assertEqual((self.workspace/'runtime/source-input-history'/old_sha).read_bytes(), self.original_manifest)

    def test_wrong_original_hash_is_rejected(self):
        audit = copy.deepcopy(self.audit)
        audit['original_image_sha256'] = '0'*64
        self.reject(audit, 'wrong-image')

    def test_missing_original_location_is_rejected(self):
        audit = copy.deepcopy(self.audit)
        audit['rows'][0]['slots'] = []
        self.reject(audit, 'wrong-location')

    def test_forged_alias_is_rejected(self):
        audit = copy.deepcopy(self.audit)
        row = next(row for row in audit['rows'] if row['same_class_alias'])
        row['exports'].append(['_unrelated_function', '/usr/lib/swift/libswiftCore.dylib'])
        self.reject(audit, 'forged-alias')

    def test_wrong_selected_provider_is_rejected(self):
        audit = copy.deepcopy(self.audit)
        audit['rows'][0]['selected'][1] = '/usr/lib/libSystem.B.dylib'
        self.reject(audit, 'wrong-provider')

    def test_wrong_provider_bytes_are_rejected(self):
        audit = copy.deepcopy(self.audit)
        provider = next(iter(audit['original_dependency_sha256']))
        audit['original_dependency_sha256'][provider] = '0'*64
        self.reject(audit, 'wrong-provider-bytes')


if __name__ == '__main__':
    unittest.main(verbosity=2)
