#!/usr/bin/env python3
"""Preserve the verified Unity build and prepare certificate CI on reflink copies."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile

r = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--identity-report', default='runtime/original-codesign-certificate-924gzxz5/result.json')
p.add_argument('--identity-setup', help='Fresh prepare-only test identity metadata; signing is verified by the resulting full build')
p.add_argument('--candidate', default='config/native-certificate-candidate-v1.json')
p.add_argument('--bind-stage', default='artifacts/workspace-bind-launcher-certificate-v1-stage.json')
p.add_argument('--without-provisioning-profile', action='store_true', help='Explicit self-generated certificate fixture only; cannot produce a provisioned device build')
a = p.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
identity_path = a.identity_setup or a.identity_report
identity = json.loads((r / identity_path).read_text())
if a.identity_setup:
    assert identity['temporary_self_generated_identity_only']
    directory = (r / identity['application']).parent
    assert sha(directory / 'certificate.der') == identity['public_certificate_SHA256']
    assert hashlib.sha1((directory / 'certificate.der').read_bytes()).hexdigest().upper() == identity['identity_SHA1']
else:
    assert identity['original_codesign_frontend_completed'] and identity['outer_status'] == 0
store = r / identity['application']; store = store.parent / 'identity-store.plist'
assert store.is_file() and (store.stat().st_mode & 0o077) == 0
folder = Path(tempfile.mkdtemp(prefix='unity-certificate-ci-', dir=r / 'runtime'))
folder.chmod(0o700)
candidate = json.loads((r / a.candidate).read_text())
for row in candidate['inputs'].values(): assert sha(r / row['path']) == row['sha256']
original_args = 'config/unity-ios-cocoapods-clean-dd83-v2-build-arguments.json'
argv = json.loads((r / original_args).read_text())
prefix = '/Volumes/SystemRoot/workspace/'
old_dd = r / argv[argv.index('-derivedDataPath') + 1].removeprefix(prefix)
original_ios = (r / argv[argv.index('-workspace') + 1].removeprefix(prefix)).parent
app = old_dd / 'Build/Products/Debug-iphoneos/uEmuera.app'
guarded = [app / 'uEmuera', app / '_CodeSignature/CodeResources',
           old_dd / 'Build/Intermediates.noindex/XCBuildData/build.db',
           original_ios / 'Unity-iPhone.xcodeproj/project.pbxproj']
before = {str(path.relative_to(r)): sha(path) for path in guarded}
mappings = []
for source, leaf in [(old_dd, 'DerivedData'), (original_ios, 'ios')]:
    destination = folder / leaf
    subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(destination)], check=True)
    mappings.append(dict(source=str(destination.relative_to(r)), target=str(source.relative_to(r))))
bindings = folder / 'workspace-bindings.json'; bindings.write_text(json.dumps(mappings, indent=2) + '\n')
argv[argv.index('CODE_SIGN_IDENTITY=-')] = 'CODE_SIGN_IDENTITY=' + identity['identity_SHA1']
if a.without_provisioning_profile:
    argv[-1:-1] = ['PROVISIONING_PROFILE_REQUIRED=NO', 'PROVISIONING_PROFILE_SUPPORTED=NO']
arguments = folder / 'xcode-arguments.json'; arguments.write_text(json.dumps(argv, indent=2) + '\n')
command = json.loads((r / 'config/unity-main-stack-clean-dd83-v2-command.json').read_text())
def option(key, value): command[command.index(key) + 1] = value
option('--identity-store', str(store.relative_to(r)))
option('--private-procfs-stage', candidate['inputs']['stage']['path'])
option('--direct-resource-environment', candidate['inputs']['configuration']['path'])
option('--xcode-arguments-file', str(arguments.relative_to(r)))
command += ['--certificate-candidate', a.candidate, '--workspace-bind-stage', a.bind_stage,
            '--workspace-bindings', str(bindings.relative_to(r)), '--skip-uti-diagnostic']
record = dict(command=command, arguments=argv, original_arguments=original_args,
              original_arguments_sha256=sha(r / original_args), original_guards=before,
              identity_report=identity_path, identity_report_sha256=sha(r / identity_path),
              candidate=a.candidate, candidate_sha256=sha(r / a.candidate),
              bindings=str(bindings.relative_to(r)), bindings_sha256=sha(bindings),
              application=str((folder / 'DerivedData/Build/Products/Debug-iphoneos/uEmuera.app').relative_to(r)),
              certificate_file=str((store.parent / 'certificate.pem').relative_to(r)),
              self_generated_certificate_only=True, cold_build=False,
              test_fixture_profile_requirement_disabled=a.without_provisioning_profile,
              original_project_and_CI_flow_retained=True, native_execution_verified=False)
(folder / 'prepared.json').write_text(json.dumps(record, indent=2) + '\n')
(folder / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
print(folder.relative_to(r))
