"""Public source discovery/export checks; no native tools or vendor mutations."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('research_sources', ROOT / 'dev/research-sources.py')
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


class ResearchSourceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.distribution = self.base / 'distribution'
        self.resource = self.distribution / 'dev/resource-runtime'
        self.bundle = 'research/example'
        self.files = {
            self.bundle + '/README.md': '# Example\nSource checkpoint, not a cold runtime.\n',
            self.bundle + '/payload/vendor/component/source.c': 'int original_interface(void) { return 42; }\n',
            self.bundle + '/payload/scripts/check.py': 'print("host-only check")\n',
            self.bundle + '/payload/config/example-package.json': json.dumps({
                'name': 'example',
                'payload': ['vendor/component/source.c', 'scripts/check.py'],
                'reference': ['runtime/proof/result.json']})}
        self.write_fixture()
        self.workspace = self.base / 'workspace'
        (self.workspace / 'vendor/component').mkdir(parents=True)
        (self.workspace / 'vendor/component/source.c').write_text('developer changes remain\n')

    def write_fixture(self):
        pins = {}
        for name, text in self.files.items():
            path = self.resource / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.resource / 'overlay.json').write_text(json.dumps({'research_files': pins}))
        self.sources = research.ResearchSources(self.distribution)

    def test_minimal_package_needs_no_reference_map_or_historical_evidence(self):
        catalog = self.sources.catalog()
        self.assertEqual(list(catalog), ['example'])
        report = self.sources.inspect('example', self.workspace)
        self.assertTrue(report['payload_verified'])
        self.assertFalse(report['historical_evidence_complete'])
        self.assertEqual(report['sources'][0]['workspace_status'], 'different_review_required')
        self.assertEqual(report['sources'][1]['workspace_status'], 'absent')
        self.assertFalse(report['cold_candidate_rebuild_ready'])

    def test_export_is_review_only_and_refuses_existing_directory(self):
        source = self.workspace / 'vendor/component/source.c'
        previous = source.read_bytes()
        destination = self.base / 'review'
        report = self.sources.export('example', destination, self.workspace)
        self.assertEqual(source.read_bytes(), previous)
        self.assertEqual((destination / 'vendor/component/source.c').read_text(),
                         self.files[self.bundle + '/payload/vendor/component/source.c'])
        self.assertTrue(report['export_only'])
        self.assertFalse(report['workspace_files_modified'])
        self.assertTrue((destination / research.EXPORT_MANIFEST).is_file())
        with self.assertRaisesRegex(ValueError, 'must be new'):
            self.sources.export('example', destination, self.workspace)
        with self.assertRaisesRegex(ValueError, 'vendor sources'):
            self.sources.export('example', self.workspace / 'vendor/new', self.workspace)

    def test_bad_payload_digest_fails_before_export_directory_exists(self):
        path = self.resource / self.bundle / 'payload/scripts/check.py'
        path.write_text('changed after publication\n')
        destination = self.base / 'bad-export'
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.sources.export('example', destination)
        self.assertFalse(destination.exists())

    def test_untrusted_package_spec_digest_is_rejected(self):
        path = self.resource / self.bundle / 'payload/config/example-package.json'
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.sources.catalog()

    def test_source_symlinks_rejected_and_workspace_symlinks_not_followed(self):
        path = self.resource / self.bundle / 'payload/scripts/check.py'
        content = self.base / 'same-source.py'
        content.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(content)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.sources.inspect('example')
        path.unlink()
        path.write_bytes(content.read_bytes())
        target = self.workspace / 'vendor/component/source.c'
        target.unlink()
        target.symlink_to(content)
        report = self.sources.inspect('example', self.workspace)
        self.assertEqual(report['sources'][0]['workspace_status'], 'symlink_review_required')

    def test_parent_traversal_in_registered_spec_is_rejected(self):
        spec = self.bundle + '/payload/config/example-package.json'
        self.files[spec] = json.dumps({'name': 'example', 'payload': ['../escape'], 'reference': []})
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, 'Unsafe source path'):
            self.sources.inspect('example')

    def test_evidence_only_checkpoint_can_be_inspected_but_not_exported_as_source(self):
        spec = self.bundle + '/payload/config/example-package.json'
        self.files[spec] = json.dumps({'name': 'example', 'payload': [], 'reference': []})
        self.write_fixture()
        self.assertEqual(self.sources.inspect('example')['package_kind'], 'evidence_only')
        with self.assertRaisesRegex(ValueError, 'evidence only'):
            self.sources.export('example', self.base / 'not-source')


if __name__ == '__main__':
    unittest.main()
