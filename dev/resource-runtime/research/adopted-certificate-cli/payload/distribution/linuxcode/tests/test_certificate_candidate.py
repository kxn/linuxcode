import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from linuxcode import certificates

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('certificate_cli', SOURCE / 'linuxcode/cli.py')
cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)


class CertificateCandidateTests(unittest.TestCase):
    def receipt(self, root):
        write = lambda name, value: cli.save(root / name, value)
        row = lambda name: dict(path=name, sha256=cli.sha(root / name))
        inputs = {'stage': {'path': 'runtime.json', 'sha256': 'runtime'},
                  'configuration': {'path': 'tools.json', 'sha256': 'tools'}}
        write('original-candidate.json', dict(inputs=inputs))
        (root / 'prebuild.json').write_text('[]')
        (root / 'build.log').write_text('BUILD SUCCEEDED\nSERVICE_RUNTIME_XCODE_STATUS 0\n')
        (root / 'strict.log').write_text('seven native strict checks succeeded')
        build = dict(exit_status=0, native_xcode_status=['0'], source_runtime={'kernel': 'matching'},
                     native_codesign_stage='native.json', log='build.log', log_sha256=cli.sha(root / 'build.log'),
                     native_certificate_runtime={'candidate': 'original-candidate.json',
                         'candidate_sha256': cli.sha(root / 'original-candidate.json')})
        strict = dict(verified=True, outer_status=0, native_statuses=[[str(i), '0'] for i in range(7)],
                      products=[str(i) for i in range(7)], log='strict.log', log_sha256=cli.sha(root / 'strict.log'))
        independent = dict(verified=True, checks={str(i): {'verified': True} for i in range(7)}, public_certificate_SHA256='leaf')
        write('build.json', build); write('strict.json', strict); write('independent.json', independent)
        milestone = dict(verified=True, full_Unity_CocoaPods_certificate_CI_verified=True,
                         original_xcodebuild_invoked=True, original_codesign=True, zsign_used=False,
                         ad_hoc_only=False, real_CMS_certificate_signature=True, public_certificate_SHA256='leaf',
                         references={name: cli.sha(root / name) for name in ['build.json', 'strict.json', 'independent.json']})
        write('milestone.json', milestone)
        config = dict(inputs=inputs, verified_build={key: row(name) for key, name in
                      [('milestone', 'milestone.json'), ('build_report', 'build.json'),
                       ('native_product_report', 'strict.json'), ('independent_product_report', 'independent.json')]})
        write('candidate.json', config)
        native = dict(certificate_candidate='candidate.json', candidate_sha256=cli.sha(root / 'candidate.json'),
                      build_report='build.json', stage='native.json', prebuild_file='prebuild.json',
                      prebuild_sha256=cli.sha(root / 'prebuild.json'), identity_store='runtime/new-user/store.plist')
        return native, config

    def test_rejects_different_runtime_with_otherwise_valid_success_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); native, config = self.receipt(root)
            config['inputs'] = copy.deepcopy(config['inputs']); config['inputs']['stage']['path'] = 'different.json'
            cli.save(root / 'candidate.json', config); native['candidate_sha256'] = cli.sha(root / 'candidate.json')
            with self.assertRaisesRegex(RuntimeError, 'components differ'):
                certificates.candidate(root, native, cli.sha)

    def test_rejects_missing_verified_product_despite_success_flags(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); native, config = self.receipt(root)
            data = json.loads((root / 'independent.json').read_text()); data['checks'].pop('6')
            cli.save(root / 'independent.json', data)
            milestone = json.loads((root / 'milestone.json').read_text()); milestone['references']['independent.json'] = cli.sha(root / 'independent.json')
            cli.save(root / 'milestone.json', milestone)
            for key in ['milestone', 'independent_product_report']:
                row = config['verified_build'][key]; row['sha256'] = cli.sha(root / row['path'])
            cli.save(root / 'candidate.json', config); native['candidate_sha256'] = cli.sha(root / 'candidate.json')
            with self.assertRaisesRegex(RuntimeError, 'verification is incomplete'):
                certificates.candidate(root, native, cli.sha)

    def test_adoption_uses_new_identity_and_does_not_prepare_service_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); native, config = self.receipt(root)
            profile = {'source_runtime': {'kernel': 'matching'}}
            selected = []
            def selector(p, candidate, identity, **kwargs):
                selected.append((identity, kwargs)); return p
            def load(path):
                if str(path).endswith('direct-resource-tool-runtime-profile.py'):
                    return {'profile': lambda **kwargs: profile}
                return {'select': selector}
            with patch.object(certificates.runpy, 'run_path', side_effect=load):
                certificates.candidate(root, native, cli.sha)
            self.assertEqual(selected, [('runtime/new-user/store.plist', {'prepare': False})])
            self.assertFalse((root / 'runtime').exists())

    def test_service_environment_uses_current_identity_without_repeated_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = root / 'launcher'; state.mkdir()
            (root / 'build.json').write_text('{}'); (root / 'prebuild.json').write_text('["/bin/true"]')
            native = {'certificate_candidate': 'candidate.json', 'build_report': 'build.json', 'prebuild_file': 'prebuild.json'}
            cli.save(state / 'adopted.json', dict(source_runtime={}, evidence_report_sha256=cli.sha(root / 'build.json'),
                     native_candidate=native, signing_scope='certificate'))
            profile = dict(source_runtime={}, command=['timeout', '-k', '5', '60', 'launcher', 'shell', '/usr/bin/env',
                'DYLD_FRAMEWORK_PATH=current', 'DYLD_LIBRARY_PATH=current', 'LINUXCODE_IDENTITY_STORE=current-user', 'old', '-version'])
            record = {'jobs': [{'name': 'cfprefsd-daemon', 'job': {'Label': 'preference',
                'EnvironmentVariables': {'LINUXCODE_IDENTITY_STORE': 'historical-fixture'}}}]}
            def services(p, directory):
                return {**p, 'native_certificate_runtime': {'startup': '/bin/true\n', 'cleanup': '/bin/true', 'jobs': []}}
            with patch.object(cli, 'candidate', return_value=({'environment': lambda p: {}}, profile, record)), \
                 patch.object(cli.runpy, 'run_path', return_value={'prepare_services': services}), \
                 patch.object(Path, 'cwd', return_value=root), patch.dict(os.environ, {}, clear=True):
                plan, invocation, _ = cli.prepare_invocation(root, state, ['-version'])
            job = __import__('plistlib').loads((invocation / 'service-0.plist').read_bytes())
            self.assertEqual(job['EnvironmentVariables']['LINUXCODE_IDENTITY_STORE'], 'current-user')
            script = (invocation / 'run.sh').read_text()
            self.assertNotIn('UTI_PREFLIGHT', script); self.assertNotIn('launchctl list', script)
            self.assertTrue(plan['certificate_signing_ready'])
            self.assertLess(script.index('trap cleanup EXIT'), script.index('launchctl load'))


if __name__ == '__main__': unittest.main()
