#!/usr/bin/env python3
"""Run two real preparation publishers with an overlapping manifest-read window."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import unittest

root = Path(__file__).resolve().parent.parent

wrapper = '''import pathlib, runpy, sys, time
manifest, marker, other = map(pathlib.Path, sys.argv[1:4])
original = pathlib.Path.read_bytes
seen = False
def delayed(path):
    global seen
    content = original(path)
    if path == manifest and not seen:
        seen = True
        marker.write_text('read\\n')
        deadline = time.monotonic()+2
        while not other.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    return content
pathlib.Path.read_bytes = delayed
sys.argv = sys.argv[4:]
runpy.run_path(sys.argv[0], run_name='__main__')
'''


class ConcurrentPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='concurrent-preparation-test-', dir=root/'runtime')
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        for folder in ['scripts', 'config', 'runtime/source-input-history', 'artifacts']:
            (self.workspace/folder).mkdir(parents=True, exist_ok=True)
        for name in ['prepare-resource-image-candidate.py', 'dsc-image.py',
                     'inspect-dsc-constants.py', 'exact-reexport-imports.py']:
            shutil.copy2(root/'scripts'/name, self.workspace/'scripts'/name)
        (self.workspace/'vendor').symlink_to(root/'vendor', target_is_directory=True)
        for name in ['fullsystem', 'fullsystem-libraries', 'rebuilt-libsessionutility-resource-v1']:
            (self.workspace/'runtime'/name).symlink_to(root/'runtime'/name, target_is_directory=True)
        self.manifest = self.workspace/'config/coregraphics-image-pins.json'
        self.manifest.write_bytes((root/'config/coregraphics-image-pins.json').read_bytes())
        (self.workspace/'runtime/source-input-history/manifest.json').write_text('{}\n')
        self.audit = self.workspace/'artifacts/audit.json'
        shutil.copy2(root/'artifacts/libsessionutility-original-reexport-audit-v2.json', self.audit)

    def publishers(self):
        processes = []
        for label, other in [('a', 'b'), ('b', 'a')]:
            command = ['python3', '-c', wrapper, str(self.manifest),
                str(self.workspace/(label+'.read')), str(self.workspace/(other+'.read')),
                'scripts/prepare-resource-image-candidate.py', '--from-target', 'libsessionutility-resource-v1',
                '--exact-import-audit', str(self.audit), '--target', 'concurrent-control-'+label]
            processes.append(subprocess.Popen(command, cwd=self.workspace, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, text=True))
            if label == 'a':
                deadline = time.monotonic()+5
                while not (self.workspace/'a.read').exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((self.workspace/'a.read').exists())
        results = []
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                results.append((process.returncode, stdout, stderr))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        return results

    def test_serialized_publication_preserves_both_targets_and_intermediate_history(self):
        results = self.publishers()
        self.assertTrue(all(code == 0 for code, _, _ in results), results)
        pins = json.loads(self.manifest.read_text())
        self.assertTrue({'concurrent-control-a', 'concurrent-control-b'} <= pins.keys())
        history = json.loads((self.workspace/'runtime/source-input-history/manifest.json').read_text())
        previous = history['config/coregraphics-image-pins.json']
        snapshot = self.workspace/previous['snapshot']
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), previous['sha256'])
        self.assertIn('concurrent-control-a', json.loads(snapshot.read_text()))
        self.assertNotIn('concurrent-control-b', json.loads(snapshot.read_text()))

    def test_saved_unlocked_source_fails_the_same_overlapping_publisher_control(self):
        evidence = json.loads((root/'artifacts/messagesecurity-patch-got-v3-input.json').read_text())
        digest = evidence['preparation_source_sha256']
        source = (root/'runtime/source-input-history'/digest).read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), digest)
        self.assertNotIn(b'fcntl.flock', source)
        (self.workspace/'scripts/prepare-resource-image-candidate.py').write_bytes(source)
        results = self.publishers()
        pins = json.loads(self.manifest.read_text())
        both = {'concurrent-control-a', 'concurrent-control-b'} <= pins.keys()
        self.assertTrue(any(code != 0 for code, _, _ in results) or not both,
                        'The old unlocked source unexpectedly passed the lost-update control')


if __name__ == '__main__':
    unittest.main(verbosity=2)
