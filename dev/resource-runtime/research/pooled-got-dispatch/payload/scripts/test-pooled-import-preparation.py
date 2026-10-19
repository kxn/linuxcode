#!/usr/bin/env python3
"""Check forged pooled-import audits cannot publish pins, using real original inputs."""
from pathlib import Path
import copy
import json
import shutil
import subprocess
import tempfile
import unittest

root = Path(__file__).resolve().parent.parent


class PooledImportPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='pooled-import-preparation-', dir=root/'runtime')
        cls.workspace = Path(cls.temporary.name)
        for directory in ['scripts', 'config', 'artifacts', 'runtime/source-input-history']:
            (cls.workspace/directory).mkdir(parents=True)
        for name in ['prepare-resource-image-candidate.py', 'dsc-image.py', 'inspect-dsc-constants.py',
                     'cache-patch-metadata.py', 'cache-tlv-optimization.py', 'verify-original-pooled-import.py']:
            shutil.copy2(root/'scripts'/name, cls.workspace/'scripts'/name)
        (cls.workspace/'vendor').symlink_to(root/'vendor', target_is_directory=True)
        for name in ['fullsystem', 'fullsystem-libraries', 'rebuilt-prodisplaylibrary-patch-got-v1']:
            (cls.workspace/'runtime'/name).symlink_to(root/'runtime'/name, target_is_directory=True)
        cls.original = (root/'config/coregraphics-image-pins.json').read_bytes()
        cls.audit = json.loads((root/'artifacts/prodisplaylibrary-original-import-audit-v3.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.manifest = self.workspace/'config/coregraphics-image-pins.json'
        self.history = self.workspace/'runtime/source-input-history/manifest.json'
        self.manifest.write_bytes(self.original)
        self.history.write_text('{}\n')

    def prepare(self, audit):
        label = self.id().rsplit('.', 1)[-1].replace('_', '-')
        target = 'pooled-import-'+label
        source = self.workspace/'artifacts'/(target+'-audit.json')
        source.write_text(json.dumps(audit, indent=2)+'\n')
        command = ['python3', str(self.workspace/'scripts/prepare-resource-image-candidate.py'),
            '--from-target', 'prodisplaylibrary-patch-got-v1', '--exact-import-audit', str(source),
            '--target', target]
        result = subprocess.run(command, cwd=self.workspace, capture_output=True, text=True)
        return result, target

    def reject(self, mutate):
        audit = copy.deepcopy(self.audit)
        row = next(row for row in audit['rows'] if row.get('original_GOT_import_proof'))
        mutate(audit, row)
        result, target = self.prepare(audit)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.manifest.read_bytes(), self.original)
        self.assertEqual(self.history.read_text(), '{}\n')
        self.assertFalse((self.workspace/'artifacts'/(target+'-input.json')).exists())

    def test_original_proof_publishes_exact_name(self):
        result, target = self.prepare(self.audit)
        self.assertEqual(result.returncode, 0, result.stderr)
        pin = json.loads(self.manifest.read_text())[target]
        self.assertEqual(pin['cache_imports']['_scalbn'], '/usr/lib/libSystem.B.dylib')
        report = json.loads((self.workspace/'artifacts'/(target+'-input.json')).read_text())
        self.assertEqual(report['typed_pooled_imports'][0]['records'][0]['symbol'], '_scalbn')
        self.assertFalse(report['reconstruction_attempted'])

    def test_same_address_math_alias_is_rejected(self):
        self.reject(lambda audit, row: row['selected'].__setitem__(0, '_ldexp'))

    def test_removed_proof_is_rejected(self):
        self.reject(lambda audit, row: row.pop('original_GOT_import_proof'))

    def test_changed_route_is_rejected(self):
        self.reject(lambda audit, row: row['original_GOT_import_proof']['route'][0].__setitem__('kind', 'ordinary-load'))

    def test_changed_original_file_hash_is_rejected(self):
        self.reject(lambda audit, row: row['original_GOT_import_proof']['original_file_sha256'].__setitem__('/usr/lib/libSystem.B.dylib', '0'*64))

    def test_changed_stub_bytes_are_rejected(self):
        self.reject(lambda audit, row: row['original_GOT_import_proof']['stubs'][0].__setitem__('bytes', '00'*6))

    def test_changed_patch_symbol_is_rejected(self):
        self.reject(lambda audit, row: row['original_GOT_import_proof']['records'][0].__setitem__('symbol', '_ldexp'))

    def test_changed_validator_source_hash_is_rejected(self):
        self.reject(lambda audit, row: audit['sources'].__setitem__('scripts/verify-original-pooled-import.py', '0'*64))

    def test_non_dependency_provider_is_rejected(self):
        self.reject(lambda audit, row: row['selected'].__setitem__(1, '/usr/lib/system/libsystem_m.dylib'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
