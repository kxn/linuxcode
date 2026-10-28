"""Targeted Recovery ICU import guards using synthetic data; no Apple input or native tool runs."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('recovery_icu', ROOT / 'dev/import-recovery-icu.py')
icu = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(icu)


class RecoveryIcuChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.image = self.base / 'BaseSystem.dmg'
        self.image.write_bytes(b'image-ok')
        self.output = self.base / 'new-private-output'
        self.data = {
            'usr/share/icu/icudt78l.dat': b'fixture ICU data only',
            'usr/share/icu/icutzformat.txt': b'44\n',
            'System/Library/CoreServices/SystemVersion.plist': plistlib.dumps({
                'ProductVersion': '26.6.2', 'ProductBuildVersion': '25G83'})}
        self.lock = dict(schema=1, scope='synthetic ICU input test', version='26.6.2', build='25G83',
                         archive_root='macOS Base System', image=dict(length=8, sha256=icu.sha(self.image)),
                         files={name: dict(length=len(data), sha256=hashlib.sha256(data).hexdigest())
                                for name, data in self.data.items()})
        self.lock_path = self.base / 'lock.json'
        self.lock_path.write_text(json.dumps(self.lock))
        self.pin = patch.object(icu, 'LOCK', self.lock_path)
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def extract_fixture(self, command, **kwargs):
        selected = command[6:]
        self.assertEqual(selected, [str(Path('macOS Base System') / name) for name in self.data])
        self.assertIn('-mmt=1', command)
        directory = Path(command[4][2:])
        for name, data in self.data.items():
            path = directory / self.lock['archive_root'] / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return subprocess.CompletedProcess(command, 0)

    def import_fixture(self):
        with patch.object(icu.subprocess, 'run', side_effect=self.extract_fixture):
            return icu.import_inputs(self.image, self.output, sys.executable, self.lock)

    def test_exact_selection_import_and_read_only_inspection(self):
        receipt = self.import_fixture()
        self.assertTrue(receipt['verified'])
        self.assertEqual(receipt['build'], '25G83')
        self.assertFalse(receipt['native_runtime_launched'])
        self.assertFalse(receipt['default_runtime_changed'])
        self.assertFalse(receipt['signed_chunklist_verified_this_run'])
        stream = io.StringIO()
        with patch('sys.argv', ['import-recovery-icu.py', '--output', str(self.output), '--inspect']), \
                patch.object(icu.subprocess, 'run') as run, contextlib.redirect_stdout(stream):
            icu.main()
        self.assertTrue(json.loads(stream.getvalue())['import_rechecked'])
        run.assert_not_called()

    def test_wrong_image_rejected_before_any_extraction_or_output(self):
        for content in (b'truncated', b'badImage'):
            self.image.write_bytes(content)
            with patch.object(icu.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'image (length|SHA256) mismatch'):
                    icu.import_inputs(self.image, self.output, sys.executable, self.lock)
                run.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_existing_output_cannot_be_overwritten(self):
        self.output.mkdir()
        marker = self.output / 'keep'
        marker.write_text('preserved')
        with patch.object(icu.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'must be new'):
                icu.import_inputs(self.image, self.output, sys.executable, self.lock)
            run.assert_not_called()
        self.assertEqual(marker.read_text(), 'preserved')

    def test_macho_extractor_is_refused_without_execution(self):
        tool = self.base / 'not-linux-7zip'
        tool.write_bytes(b'\xcf\xfa\xed\xfe' + b'fixture')
        tool.chmod(0o700)
        with patch.object(icu.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'actual Linux 7zip'):
                icu.import_inputs(self.image, self.output, tool, self.lock)
            run.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_tampering_symlinks_and_extra_files_are_rejected(self):
        self.import_fixture()
        data = self.output / self.lock['archive_root'] / 'usr/share/icu/icudt78l.dat'
        original = data.read_bytes()
        data.write_bytes(b'x' * len(original))
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            icu.inspect_files(self.output, self.lock)
        data.unlink()
        target = self.base / 'outside'
        target.write_bytes(original)
        data.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            icu.inspect_files(self.output, self.lock)
        data.unlink()
        data.write_bytes(original)
        (self.output / 'unexpected.dat').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'Unexpected file'):
            icu.inspect_files(self.output, self.lock, exact=True)
        # Later existing recovery preparation may add other inputs. Targeted
        # rechecking must neither traverse nor reject those unrelated files.
        (self.output / 'unrelated-symlink').symlink_to(self.base / 'not-read')
        self.assertEqual(icu.inspect_files(self.output, self.lock)['build'], '25G83')

    def test_plan_reads_no_image_and_starts_no_process(self):
        self.image.unlink()
        stream = io.StringIO()
        with patch('sys.argv', ['import-recovery-icu.py', '--image', str(self.image), '--output',
                                str(self.output), '--sevenzip', '/not-installed/7z', '--plan']), \
                patch.object(icu.subprocess, 'run') as run, contextlib.redirect_stdout(stream):
            icu.main()
        self.assertFalse(json.loads(stream.getvalue())['commands_executed'])
        self.assertFalse(self.output.exists())
        run.assert_not_called()

    def test_locked_paths_cannot_escape_new_output(self):
        self.lock['files']['../outside'] = {'length': 0, 'sha256': '0' * 64}
        self.lock_path.write_text(json.dumps(self.lock))
        with self.assertRaisesRegex(ValueError, 'Unsafe locked archive path'):
            icu.load_lock()


if __name__ == '__main__':
    unittest.main()
