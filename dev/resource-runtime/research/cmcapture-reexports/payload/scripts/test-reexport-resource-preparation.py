#!/usr/bin/env python3
"""Recheck real original reexport proofs in an isolated candidate workspace."""
from pathlib import Path
import copy
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

root = Path(__file__).resolve().parent.parent


class OriginalReexportPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='original-reexport-test-', dir=root/'runtime')
        cls.workspace = Path(cls.temp.name)
        for folder in ['scripts', 'config', 'runtime/source-input-history', 'artifacts']:
            (cls.workspace/folder).mkdir(parents=True, exist_ok=True)
        for name in ['prepare-resource-image-candidate.py', 'exact-reexport-imports.py',
                     'dsc-image.py', 'inspect-dsc-constants.py']:
            shutil.copy2(root/'scripts'/name, cls.workspace/'scripts'/name)
        (cls.workspace/'vendor').symlink_to(root/'vendor', target_is_directory=True)
        for name in ['fullsystem', 'fullsystem-libraries', 'rebuilt-libsessionutility-resource-v1']:
            (cls.workspace/'runtime'/name).symlink_to(root/'runtime'/name, target_is_directory=True)
        cls.manifest = cls.workspace/'config/coregraphics-image-pins.json'
        cls.original = (root/'config/coregraphics-image-pins.json').read_bytes()
        cls.audit = json.loads((root/'artifacts/libsessionutility-original-reexport-audit-v2.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.manifest.write_bytes(self.original)
        (self.workspace/'runtime/source-input-history/manifest.json').write_text('{}\n')

    def prepare(self, audit, label, accepted=False, slow_publication=False):
        path = self.workspace/'artifacts'/(label+'.json')
        path.write_text(json.dumps(audit)+'\n')
        target = 'reexport-control-'+label
        command = ['python3', 'scripts/prepare-resource-image-candidate.py',
            '--from-target', 'libsessionutility-resource-v1', '--exact-import-audit', str(path),
            '--target', target]
        if slow_publication:
            # Widen the truncation window deterministically. With direct final
            # writes, a concurrent profile reader sees malformed JSON; temp
            # writes followed by rename keep both published files parseable.
            wrapper = '''import pathlib, runpy, sys, time
original = pathlib.Path.write_text
def slow(path, data, *args, **kwargs):
    if path.name in ('manifest.json', 'manifest.tmp', 'coregraphics-image-pins.json', 'coregraphics-image-pins.tmp'):
        with path.open('w') as stream:
            middle = len(data)//2
            stream.write(data[:middle]); stream.flush(); time.sleep(0.15)
            stream.write(data[middle:])
        return len(data)
    return original(path, data, *args, **kwargs)
pathlib.Path.write_text = slow
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
            command = ['python3', '-c', wrapper, *command[1:]]
        result = subprocess.run(command, cwd=self.workspace, capture_output=True, text=True)
        if accepted:
            self.assertEqual(result.returncode, 0, result.stderr)
            pin = json.loads(self.manifest.read_text())[target]
            self.assertEqual(len(pin['cache_imports']), 13)
            self.assertEqual(pin['cache_imports']['__ZTISt9exception'], '/usr/lib/libc++.1.dylib')
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.manifest.read_bytes(), self.original)
            self.assertFalse((self.workspace/'artifacts'/(target+'-input.json')).exists())
            self.assertEqual((self.workspace/'runtime/source-input-history/manifest.json').read_text(), '{}\n')

    def test_original_proof(self):
        self.prepare(self.audit, 'valid', accepted=True)

    def test_changed_transitive_provider_hash(self):
        audit = copy.deepcopy(self.audit)
        audit['explicit_reexports']['original_provider_sha256']['/usr/lib/libc++abi.dylib'] = '0'*64
        self.prepare(audit, 'provider-bytes')

    def test_changed_reexport_edge(self):
        audit = copy.deepcopy(self.audit)
        audit['explicit_reexports']['chains'][0]['chain'][0]['export'][1] = 99
        self.prepare(audit, 'edge')

    def test_changed_selected_symbol(self):
        audit = copy.deepcopy(self.audit)
        row = next(row for row in audit['rows'] if row['selected'][0].startswith('__ZTI'))
        row['selected'][0] = '__ZTISt12out_of_range'
        self.prepare(audit, 'symbol')

    def test_changed_helper_source_hash(self):
        audit = copy.deepcopy(self.audit)
        audit['sources']['scripts/exact-reexport-imports.py'] = '0'*64
        self.prepare(audit, 'helper-bytes')

    def test_concurrent_readers_never_see_partial_manifests(self):
        stop, failures, reads = threading.Event(), [], []
        def reader():
            while not stop.is_set():
                for path in [self.manifest, self.workspace/'runtime/source-input-history/manifest.json']:
                    try:
                        json.loads(path.read_text())
                        reads.append(1)
                    except Exception as error:
                        failures.append(str(error))
                time.sleep(0.001)
        thread = threading.Thread(target=reader)
        thread.start()
        try:
            self.prepare(self.audit, 'atomic', accepted=True, slow_publication=True)
        finally:
            stop.set()
            thread.join()
        self.assertGreater(len(reads), 50)
        self.assertEqual(failures, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
