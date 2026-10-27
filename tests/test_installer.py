"""Failure and isolation checks; no Darling session or Apple download is started."""
from pathlib import Path
import importlib.util
import hashlib
import json
import os
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from linuxcode import cli


class InstallerChecks(unittest.TestCase):
    def test_native_status_is_required_even_when_outer_succeeded(self):
        self.assertEqual(cli.checked_exit_status(None, 0), 125)
        self.assertEqual(cli.checked_exit_status(0, 124), 124)
        self.assertEqual(cli.checked_exit_status(65, 0), 65)
        self.assertEqual(cli.checked_exit_status(0, 0), 0)

    def test_long_build_timeout_is_configurable_and_validated(self):
        with patch.dict(os.environ, {'LINUXCODE_BUILD_TIMEOUT_SECONDS': '2400'}):
            self.assertEqual(cli.build_timeout(), 2400)
        for value in ['0', '-1', '86401', 'invalid']:
            with patch.dict(os.environ, {'LINUXCODE_BUILD_TIMEOUT_SECONDS': value}):
                with self.assertRaises(RuntimeError):
                    cli.build_timeout()

    def test_project_path_cannot_escape_the_mounted_workspace(self):
        self.assertEqual(cli.guest_path('/tmp/work/Project With Spaces', Path('/tmp/work')),
                         cli.GUEST + 'Project With Spaces')
        with self.assertRaises(RuntimeError):
            cli.guest_path('/tmp/foreign/project', Path('/tmp/work'))
        with self.assertRaises(RuntimeError):
            cli.guest_path('/tmp/work/../../foreign/project', Path('/tmp/work'))

    def test_rejects_non_macho_and_arm_only_xcode(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / 'Xcode.app'
            binary = app / 'Contents/Developer/usr/bin/xcodebuild'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'Not an executable')
            with self.assertRaisesRegex(RuntimeError, 'Mach-O'):
                cli.intel_xcode(app)
            binary.write_bytes(struct.pack('<II', 0xfeedfacf, 0x0100000c) + bytes(32))
            with self.assertRaisesRegex(RuntimeError, 'Intel'):
                cli.intel_xcode(app)

    def test_full_xip_digest_checked_before_extraction_or_prefix_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            xip = workspace / 'sample.xip'; xip.write_bytes(b'input mismatch')
            with patch.object(cli, 'verify_workspace', return_value=1), patch.object(cli, 'run') as execution:
                with self.assertRaisesRegex(RuntimeError, 'XIP SHA256 mismatch'):
                    cli.install_xcode(workspace, xip, '0' * 64)
                execution.assert_not_called()
            self.assertFalse((workspace / 'runtime').exists())

    def test_source_package_uses_allowlist_and_never_includes_private_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'source.tar.gz'
            cli.package(output, include_research_history=False)
            with tarfile.open(output) as archive:
                names = archive.getnames()
                self.assertIn('linuxcode/linuxcode/cli.py', names)
                self.assertIn('linuxcode/dev/resource-runtime/apply-overlay.py', names)
                self.assertIn('linuxcode/dev/resource-runtime/payload/scripts/rebuild-c-cache-image.py', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/native-resource-dependencies/payload/fixtures/SwiftInverseEnvironment/InverseKeyPath.swift', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/native-resource-dependencies/payload/vendor/darling/src/sandbox/CMakeLists.txt', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/unity-shared-remap/payload/fixtures/hello/proc-maps.cpp', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/unity-shared-remap/payload/vendor/darlingserver/internal-include/darlingserver/proc-maps.hpp', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/unity-exec-environment/payload/fixtures/hello/ManagedProcessEnvironment.cs', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/unity-private-procfs/payload/vendor/darling/src/include/darling-config.h.in', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/unity-full-app-cocoapods/payload/scripts/inspect-unity-pods-project.rb', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/cloudkit-standalone/payload/vendor/darling/src/external/objc4/runtime/objc-os.mm', names)
                self.assertIn('linuxcode/dev/resource-runtime/research/cloudkit-standalone/payload/vendor/darling/src/external/security/OSX/sec/Security/SecExports.exp-in', names)
                self.assertFalse(any('/.local/' in n or n.endswith(('.xip', '.dylib', '.p12')) for n in names))
                self.assertFalse(any('/reference/' in n for n in names))
                self.assertTrue(all(i.isfile() for i in archive.getmembers()))
            with self.assertRaisesRegex(RuntimeError, 'replace'):
                cli.package(output, include_research_history=False)

    def test_generated_service_jobs_have_launchctl_permissions_and_session(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state = workspace / 'launcher'; state.mkdir()
            report_path = workspace / cli.LOCK['candidate']['report']
            report_path.parent.mkdir(parents=True); report_path.write_text('{}')
            profile = {'source_runtime': {}, 'command': ['timeout', '-k', '5', '60', 'bin/darling-system-version', 'shell', '/usr/bin/env', '/bin/unused', '-version']}
            record = {'jobs': [{'name': 'cfprefsd-agent', 'job': {'Label': 'test.preference.agent', 'ProgramArguments': ['/bin/true'], 'EnvironmentVariables': {}}}]}
            cli.save(state / 'adopted.json', {'source_runtime': {}, 'evidence_report_sha256': cli.sha(report_path)})
            previous = os.umask(0o002)
            try:
                environment = {'DISPLAY': ':99', 'WAYLAND_DISPLAY': 'test', 'XAUTHORITY': '/tmp/test', 'KEEP': 'value'}
                with patch.object(cli, 'candidate', return_value=({'environment': lambda p: dict(environment)}, profile, record)), patch.object(Path, 'cwd', return_value=workspace):
                    _, invocation, execution = cli.prepare_invocation(workspace, state, ['-version'])
            finally:
                os.umask(previous)
            self.assertEqual((invocation / 'service-0.plist').stat().st_mode & 0o777, 0o644)
            text = (invocation / 'run.sh').read_text()
            self.assertIn('launchctl load -S Background ', text)
            self.assertLess(text.index('trap cleanup EXIT'), text.index('launchctl load '))
            self.assertIn('unset DISPLAY WAYLAND_DISPLAY XAUTHORITY', text)
            self.assertFalse(set(environment.keys()) - {'KEEP'} & execution[1].keys())
            self.assertEqual(execution[1]['KEEP'], 'value')

    def _native_receipt(self, workspace):
        native = {'stage': 'stage.json', 'identity_store': 'store.plist',
                  'build_report': 'build.json', 'product_report': 'product.json'}
        for name in ['stage.json', 'build.json']:
            (workspace / name).write_text('{}')
        (workspace / 'archive.a').write_bytes(b'archive payload')
        (workspace / 'verify.log').write_text('verification evidence')
        signed = {'verified': True, 'zsign_used': False, 'ad_hoc_only': True,
                  'build_report': 'build.json', 'build_report_sha256': cli.sha(workspace / 'build.json'),
                  'native_codesign_stage': 'stage.json', 'stage_sha256': cli.sha(workspace / 'stage.json'),
                  'native_product_statuses': [['0', '0'], ['1', '0'], ['2', '0']],
                  'files': {'archive.a': cli.sha(workspace / 'archive.a')},
                  'log': 'verify.log', 'log_sha256': cli.sha(workspace / 'verify.log'),
                  'archive_signature_attributes': {'archive.a': {'user.com.apple.cs.CodeDirectory': hashlib.sha256(b'original').hexdigest()}}}
        cli.save(workspace / 'product.json', signed)
        return native, signed

    def test_native_adoption_rejects_receipt_for_another_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            native, signed = self._native_receipt(workspace)
            signed['native_codesign_stage'] = 'another-stage.json'
            cli.save(workspace / 'product.json', signed)
            with patch.object(cli.runpy, 'run_path', return_value={'profile': lambda **kwargs: {}}):
                with self.assertRaisesRegex(RuntimeError, 'does not match'):
                    cli.candidate(workspace, native=native)

    def test_native_adoption_rejects_changed_signature_xattr_even_when_file_bytes_match(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            native, _ = self._native_receipt(workspace)
            with patch.object(cli.runpy, 'run_path', return_value={'profile': lambda **kwargs: {}}), patch.object(cli.os, 'getxattr', return_value=b'changed'):
                with self.assertRaisesRegex(RuntimeError, 'signature attribute changed'):
                    cli.candidate(workspace, native=native)

    def test_offline_xcode_import_does_not_suppress_darling_prefix_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prefix = workspace / 'runtime/state/prefix'
            app = prefix / 'Applications/Xcode.app'; app.mkdir(parents=True)
            (app / 'preserved-input').write_text('original')
            cli.save(workspace / 'artifacts/distribution-xcode-install.json', {})
            def initialize(*args, **kwargs):
                self.assertFalse(prefix.exists())
                account = prefix / 'private/etc/passwd'; account.parent.mkdir(parents=True)
                account.write_text('initialized')
            with patch.object(cli, 'intel_xcode'), patch.object(cli, 'run', side_effect=initialize):
                cli.initialize_prefix(workspace)
            self.assertEqual((app / 'preserved-input').read_text(), 'original')
            self.assertEqual((prefix / 'private/etc/passwd').read_text(), 'initialized')
            self.assertFalse((workspace / 'runtime/offline-xcode-prefix').exists())

    def test_unrecognized_partial_prefix_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prefix = workspace / 'runtime/state/prefix'; prefix.mkdir(parents=True)
            (prefix / 'unrelated-data').write_text('keep')
            with patch.object(cli, 'run') as execution:
                with self.assertRaisesRegex(RuntimeError, 'unrecognized'):
                    cli.initialize_prefix(workspace)
                execution.assert_not_called()
            self.assertEqual((prefix / 'unrelated-data').read_text(), 'keep')

    def test_locked_workspace_changed_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); manifest = workspace / 'checkpoint/workspace-files.json'
            manifest.parent.mkdir(); (workspace / 'script.py').write_text('changed')
            manifest.write_text(json.dumps({'script.py': '0' * 64}))
            lock = {'workspace': {'commit': 'base', 'manifest_sha256': cli.sha(manifest)}}
            with patch.object(cli, 'LOCK', lock), patch.object(cli, 'git', return_value='base'):
                with self.assertRaisesRegex(RuntimeError, 'script.py'):
                    cli.verify_workspace(workspace)


if __name__ == '__main__':
    unittest.main()
