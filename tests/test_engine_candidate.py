import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('engine_cli', SOURCE / 'linuxcode/cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class EngineCandidateEvidenceTests(unittest.TestCase):
    def receipt(self, workspace):
        (workspace / 'build.json').write_text('{}')
        (workspace / 'verify.log').write_text('original verification')
        (workspace / 'App').write_bytes(b'verified executable')
        signed = dict(verified=True, ad_hoc_only=True, zsign_used=False, stage='stage80.json',
                      configuration='tools.json', outer_status=0,
                      native_statuses=[[str(i), '0'] for i in range(6)],
                      independent_checks={'App': {'verified': True}}, log='verify.log',
                      log_sha256=cli.sha(workspace / 'verify.log'))
        milestone = dict(verified=True, original_xcodebuild_full_build_and_original_codesign_success=True,
                         ad_hoc_signing_only=True, zsign_used=False, stage='stage80.json',
                         resource_environment='tools.json', build_report='build.json',
                         build_report_sha256=cli.sha(workspace / 'build.json'), signature_report='sign.json',
                         file_evidence={'App': {'sha256': cli.sha(workspace / 'App')}})
        return signed, milestone

    def save(self, workspace, signed, milestone):
        cli.save(workspace / 'sign.json', signed)
        milestone['signature_report_sha256'] = cli.sha(workspace / 'sign.json')
        cli.save(workspace / 'milestone.json', milestone)

    def test_rejects_other_runtime_even_with_valid_receipt_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            signed, milestone = self.receipt(workspace)
            signed['stage'] = 'another-runtime.json'
            self.save(workspace, signed, milestone)
            with self.assertRaisesRegex(RuntimeError, 'signatures do not match'):
                cli.candidate(workspace, dict(engine_milestone='milestone.json', build_report='build.json'))

    def test_rejects_changed_product_with_unchanged_success_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            signed, milestone = self.receipt(workspace)
            self.save(workspace, signed, milestone)
            (workspace / 'App').write_bytes(b'changed executable')
            with self.assertRaisesRegex(RuntimeError, 'Engine product changed'):
                cli.candidate(workspace, dict(engine_milestone='milestone.json', build_report='build.json'))
