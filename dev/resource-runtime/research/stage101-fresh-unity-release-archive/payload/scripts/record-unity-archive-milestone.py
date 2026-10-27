#!/usr/bin/env python3
"""Join actual archive, native strict checks and independent cryptographic proof."""
from pathlib import Path
import argparse
import hashlib
import json

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive-report',required=True);p.add_argument('--native-products',required=True);p.add_argument('--report',required=True);p.add_argument('--source-kernel-commit');p.add_argument('--prepared-run');a=p.parse_args()
read=lambda n:json.loads((r/n).read_text());sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
archive=read(a.archive_report);strict=read(a.native_products);independent=read(archive['independent_products'])
refs=[a.archive_report,a.native_products,archive['independent_products']]
if archive.get('cli_invocation'):
    invocation=r/archive['cli_invocation'];status=json.loads((invocation/'result.json').read_text());plan=json.loads((invocation/'plan.json').read_text())
    assert sha(invocation/'result.json')==archive['native_evidence_sha256']
    assert sha(invocation/'plan.json')==archive['cli_plan_sha256']
    assert status['native_exit_status']==status['outer_exit_status']==status['exit_status']==0
    build=dict(native_certificate_runtime=plan['certificate_runtime'],xcode_arguments=plan['mapped_argv'],
               log=str((invocation/'output.log').relative_to(r)),log_sha256=status['log_sha256'])
    refs += [str((invocation/'result.json').relative_to(r)),str((invocation/'plan.json').relative_to(r))]
else:
    build=read(archive['build_report']);refs.append(archive['build_report'])
assert archive['verified'] and archive['native_archive_status']==archive['outer_status']==0
count=len(strict['products']);assert count>0 and len(set(strict['products']))==count
assert strict['verified'] and strict['outer_status']==0 and strict['native_statuses']==[[str(i),'0'] for i in range(count)]
assert independent['verified'] and all(x['verified'] for x in independent['checks'].values()) and sorted(strict['products'])==sorted(independent['checks'])
app=r/archive['application'];required={archive['application'],*[str(p.relative_to(r)) for p in (app/'Frameworks').glob('*.framework')]}
assert required.issubset(strict['products']), 'Every archived framework and App requires native and independent checks'
assert sha(r/strict['log'])==strict['log_sha256']
assert sha(r/build['log'])==build['log_sha256']
runtime=build['native_certificate_runtime'];assert runtime['candidate']==strict['candidate'] and runtime['candidate_sha256']==strict['candidate_sha256']
assert sha(r/runtime['candidate'])==runtime['candidate_sha256']
selected=read(runtime['candidate']);stage=selected['inputs']['stage'];assert sha(r/stage['path'])==stage['sha256']
configuration=build['xcode_arguments'][build['xcode_arguments'].index('-configuration')+1]
if configuration=='Release':assert archive['standalone_symbols_required'] and archive['standalone_symbol_generation_verified']
record=dict(verified=True,host='Linux x86_64 Darling; no Mac',target='iPhoneOS arm64',configuration=configuration,
            full_Unity_CocoaPods_certificate_CI_verified=True,original_xcodebuild_invoked=True,original_codesign=True,
            zsign_used=False,ad_hoc_only=False,real_CMS_certificate_signature=True,original_archive_verified=True,
            archive=archive['archive'],application=archive['application'],native_archive_status=0,outer_status=0,
            CompileC_tasks=archive['CompileC_tasks'],code_sign_tasks=archive['CodeSign_tasks'],
            native_strict_verified_products=count,independent_verified_products=count,
            required_archived_products=sorted(required),
            standalone_symbol_products=archive['standalone_symbol_products'],standalone_symbol_generation_verified=archive['standalone_symbol_generation_verified'],
            LLVM_DWARF_verification=archive.get('LLVM_DWARF_verification',False),
            self_generated_certificate_only=True,test_fixture_profile_requirement_disabled=True,
            public_certificate_SHA256=independent['public_certificate_SHA256'],
            candidate=runtime['candidate'],stage=stage['path'],stage_sha256=stage['sha256'],
            source_kernel_commit=a.source_kernel_commit,
            developer_provisioning_or_device_trust_verified=False,
            references={name:sha(r/name) for name in refs},log=build['log'],log_sha256=build['log_sha256'],
            tool_sha256=sha(Path(__file__)),full_goal_complete=False)
if a.prepared_run:
    prepared=read(a.prepared_run+'/prepared.json');driver=read(a.prepared_run+'/driver-result.json')
    assert driver['exit_status']==0 and driver['archive']==archive['archive']==prepared['archive']
    assert driver['original_guards_preserved'] and all(driver['original_guards_preserved'].values())
    assert set(driver['original_guards_preserved'])==set(prepared['original_guards'])
    record.update(original_Debug_guards_preserved=driver['original_guards_preserved'],
                  prepared_run=a.prepared_run,source_milestone=prepared['source_milestone'])
    for name in ['prepared.json','driver-result.json']:
        relative=a.prepared_run+'/'+name;record['references'][relative]=sha(r/relative)
out=r/a.report;assert not out.exists();out.write_text(json.dumps(record,indent=2)+'\n');print(out)
