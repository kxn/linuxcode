#!/usr/bin/env python3
"""Record a successful full Unity certificate CI without weakening its evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import re

r = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--run', required=True); p.add_argument('--build-report', required=True)
p.add_argument('--native-verify', required=True); p.add_argument('--independent', required=True)
p.add_argument('--report', required=True); p.add_argument('--source-security-commit', default='f50f940d254addfb74f80f5fb9edc4cda60beb6c'); a = p.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda name: json.loads((r / name).read_text())
prepared = read(a.run + '/prepared.json'); build = read(a.build_report)
native = read(a.native_verify); independent = read(a.independent)
assert build['exit_status'] == 0 and build['native_xcode_status'] == ['0']
assert build['xcode_arguments'] == prepared['arguments']
assert sha(r / build['log']) == build['log_sha256']
log = (r / build['log']).read_text(); assert '** BUILD SUCCEEDED **' in log
assert len(re.findall(r'^CodeSign ', log, re.M)) == 7
identity = read(prepared['identity_report'])
assert len(re.findall(r'^    /usr/bin/codesign --force --sign ' + identity['identity_SHA1'] + r' ', log, re.M)) == 7
assert native['verified'] and native['outer_status'] == 0
assert native['native_statuses'] == [[str(i), '0'] for i in range(7)]
assert sha(r / native['log']) == native['log_sha256']
assert independent['verified'] and len(independent['checks']) == 7
assert sorted(native['products']) == sorted(independent['checks'])
assert independent['public_certificate_SHA256'] == identity['public_certificate_SHA256']
guards = {name: sha(r / name) == digest for name, digest in prepared['original_guards'].items()}
assert all(guards.values())
bindings = read(prepared['bindings']); ios = r / next(row['source'] for row in bindings if row['target'].endswith('/ios'))
source_ios = r / next(row['target'] for row in bindings if row['target'].endswith('/ios'))
project_inputs = ['Unity-iPhone.xcodeproj/project.pbxproj', 'Unity-iPhone.xcworkspace/contents.xcworkspacedata',
                  'Pods/Pods.xcodeproj/project.pbxproj', 'Podfile', 'Podfile.lock', 'Pods/Manifest.lock']
projects = {}
for name in project_inputs:
    assert sha(ios / name) == sha(source_ios / name)
    projects[name] = sha(ios / name)
original = read(prepared['original_arguments'])
changes = dict(removed=[v for v in original if v not in prepared['arguments']],
               added=[v for v in prepared['arguments'] if v not in original])
record = dict(verified=True, host='Linux x86_64 Darling; no Mac', target='iPhoneOS arm64',
              original_xcodebuild_invoked=True, original_codesign=True, zsign_used=False,
              real_CMS_certificate_signature=True, ad_hoc_only=False,
              full_Unity_CocoaPods_certificate_CI_verified=True,
              self_generated_certificate_only=True, developer_provisioning_or_device_trust_verified=False,
              test_fixture_profile_requirement_disabled=prepared['test_fixture_profile_requirement_disabled'],
              original_project_and_Pod_inputs_unchanged=projects, test_argument_changes=changes,
              native_build_status=build['native_xcode_status'], outer_status=build['exit_status'],
              code_sign_tasks=7, native_strict_verified_products=7, independent_verified_products=7,
              CompileC_tasks_this_incremental_run=len(re.findall(r'^CompileC ',log,re.M)),
              incremental_cache_reuse=True, cold_build=False,
              previous_fresh_build='artifacts/unity-original-fresh-signed-app-v1.json',
              original_verified_build_preserved=guards, application=prepared['application'],
              original_codesign_sha256=sha(r / 'runtime/native-codesign-ci-v3/codesign-original'),
              original_xcodebuild_sha256=build['original_xcodebuild_sha256'],
              public_certificate_SHA256=identity['public_certificate_SHA256'],
              candidate=prepared['candidate'], source_security_commit=a.source_security_commit,
              references={name:sha(r/name) for name in [a.run+'/prepared.json',a.build_report,a.native_verify,a.independent]},
              log=build['log'], log_sha256=build['log_sha256'],
              remaining=['Apple developer identity/provisioning and device installation',
                         'Archive/export and UE', 'Cold Linux/XIP reconstruction and default installer integration'],
              full_goal_complete=False)
out = r / a.report; assert not out.exists(); out.write_text(json.dumps(record, indent=2) + '\n')
print(out)
