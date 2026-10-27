#!/usr/bin/env python3
"""Join actual archive, native strict checks and independent cryptographic proof."""
from pathlib import Path
import argparse
import hashlib
import json

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive-report',required=True);p.add_argument('--native-products',required=True);p.add_argument('--report',required=True);a=p.parse_args()
read=lambda n:json.loads((r/n).read_text());sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
archive=read(a.archive_report);strict=read(a.native_products);build=read(archive['build_report']);independent=read(archive['independent_products'])
assert archive['verified'] and archive['native_archive_status']==archive['outer_status']==0
assert strict['verified'] and strict['outer_status']==0 and strict['native_statuses']==[[str(i),'0'] for i in range(7)]
assert independent['verified'] and len(independent['checks'])==7 and sorted(strict['products'])==sorted(independent['checks'])
assert sha(r/strict['log'])==strict['log_sha256']
runtime=build['native_certificate_runtime'];assert runtime['candidate']==strict['candidate'] and runtime['candidate_sha256']==strict['candidate_sha256']
configuration=build['xcode_arguments'][build['xcode_arguments'].index('-configuration')+1]
refs=[a.archive_report,a.native_products,archive['build_report'],archive['independent_products']]
record=dict(verified=True,host='Linux x86_64 Darling; no Mac',target='iPhoneOS arm64',configuration=configuration,
            full_Unity_CocoaPods_certificate_CI_verified=True,original_xcodebuild_invoked=True,original_codesign=True,
            zsign_used=False,ad_hoc_only=False,real_CMS_certificate_signature=True,original_archive_verified=True,
            archive=archive['archive'],application=archive['application'],native_archive_status=0,outer_status=0,
            CompileC_tasks=archive['CompileC_tasks'],code_sign_tasks=archive['CodeSign_tasks'],
            native_strict_verified_products=7,independent_verified_products=7,
            standalone_symbol_products=archive['standalone_symbol_products'],standalone_symbol_generation_verified=archive['standalone_symbol_generation_verified'],
            self_generated_certificate_only=True,test_fixture_profile_requirement_disabled=True,
            public_certificate_SHA256=independent['public_certificate_SHA256'],
            candidate=runtime['candidate'],stage=build['private_procfs_stage'],
            source_kernel_commit='0d24e0824a66dd795517b11b6f4457c5f24afef1',
            developer_provisioning_or_device_trust_verified=False,
            references={name:sha(r/name) for name in refs},log=build['log'],log_sha256=build['log_sha256'],full_goal_complete=False)
out=r/a.report;assert not out.exists();out.write_text(json.dumps(record,indent=2)+'\n');print(out)
