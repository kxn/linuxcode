"""Public-source build planning and provenance guards; no network or server execution."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('public_server_build', ROOT / 'dev/build-public-server.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class PublicServerBuildChecks(unittest.TestCase):
    def test_plan_selects_published_server_and_executes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / 'new-workspace'
            stream = io.StringIO()
            with patch('sys.argv', ['build-public-server.py', '--workspace', str(workspace), '--plan']), \
                    patch.object(build.subprocess, 'run') as execute, \
                    patch.object(build.subprocess, 'check_output') as inspect, contextlib.redirect_stdout(stream):
                build.main()
            result = json.loads(stream.getvalue())
            server = next(row for row in result['repositories'] if row['name'] == 'darlingserver')
            self.assertEqual(server['commit'], '4328b8010abad9ff1dbef2bd255da06b505c49ca')
            self.assertEqual(len(result['repositories']), 6)
            self.assertEqual(result['build_command'][-2:], ['--jobs', '2'])
            self.assertFalse(workspace.exists())
            execute.assert_not_called()
            inspect.assert_not_called()

    def test_existing_workspace_is_refused_before_any_fetch(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('sys.argv', ['build-public-server.py', '--workspace', folder]), \
                    patch.object(build.subprocess, 'run') as execute:
                with self.assertRaisesRegex(ValueError, 'must be new'):
                    build.main()
                execute.assert_not_called()

    def test_explicit_host_prefix_keeps_bison_and_data_together(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder)
            (prefix / 'bin').mkdir()
            (prefix / 'share/bison').mkdir(parents=True)
            for name in ('bison', 'flex', 'm4'):
                path = prefix / 'bin' / name
                path.write_text('host tool placeholder; this test never executes it\n')
                path.chmod(0o700)
            with patch.dict(os.environ, {'BISON_PKGDATADIR': '/wrong-version', 'DYLD_LIBRARY_PATH': '/wrong-runtime'}):
                env = build.environment(prefix)
            self.assertEqual(env['PATH'].split(os.pathsep)[0], str(prefix / 'bin'))
            self.assertEqual(env['BISON_PKGDATADIR'], str(prefix / 'share/bison'))
            self.assertEqual(env['M4'], str(prefix / 'bin/m4'))
            self.assertNotIn('DYLD_LIBRARY_PATH', env)

    def test_wrong_head_or_dirty_source_is_not_a_verified_checkpoint(self):
        row = {'name': 'example', 'path': '.', 'url': 'https://github.com/example/source.git', 'commit': '1' * 40}
        lock = {'repositories': [row], 'build_support_sha256': 'unused'}
        for head, dirty in (('0' * 40, ''), ('1' * 40, ' M source.c')):
            def git_output(command, cwd=None):
                if command[-1] == 'HEAD':
                    return head
                if 'status' in command:
                    return dirty
                if command[-1] == 'origin':
                    return row['url']
                return '.git/objects/info/alternates'
            with tempfile.TemporaryDirectory() as folder, patch.object(build, 'output', side_effect=git_output):
                with self.assertRaisesRegex(ValueError, 'Public checkout changed'):
                    build.source_snapshot(Path(folder), lock)

    def test_dependency_audit_includes_relative_build_and_source_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            lock = {'repositories': [{'name': 'public', 'path': '.'}]}
            deps = ('object.o: #deps 3, deps mtime 0 (VALID)\n'
                    '    generated.h\n    ../../../vendor/public.h\n    /usr/include/stddef.h\n')
            with patch.object(build, 'output', return_value=deps), \
                    patch.object(build.subprocess, 'check_output', return_value=b'vendor/public.h\0'):
                result = build.dependency_audit(workspace, lock)
            self.assertEqual(result['distinct_paths'], 3)
            self.assertEqual(result['categories'], {'public_source': 1, 'generated_build': 1, 'system_host': 1})

    def test_dependency_audit_rejects_untracked_or_external_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            lock = {'repositories': [{'name': 'public', 'path': '.'}]}
            for name, message in (('../../../vendor/hidden.h', 'untracked source'),
                                  ('/private-reference/AppleSDK/private.h', 'outside public checkout')):
                with patch.object(build, 'output', return_value='object.o: #deps 1\n    ' + name + '\n'), \
                        patch.object(build.subprocess, 'check_output', return_value=b'only-public.h\0'):
                    with self.assertRaisesRegex(ValueError, message):
                        build.dependency_audit(workspace, lock)


if __name__ == '__main__':
    unittest.main()
