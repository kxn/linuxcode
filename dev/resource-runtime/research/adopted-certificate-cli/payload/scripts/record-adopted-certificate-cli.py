#!/usr/bin/env python3
"""Record the unchanged PATH-based Unity build with a new caller identity."""
from pathlib import Path
import argparse
import hashlib
import json
import re

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--run',required=True);p.add_argument('--invocation',required=True)
p.add_argument('--independent',required=True);p.add_argument('--report',required=True);a=p.parse_args()
read=lambda n:json.loads((r/n).read_text());sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
setup=read(a.run+'/prepared.json');driver=read(a.run+'/PATH-invocation.json')
plan=read(a.invocation+'/plan.json');native=read(a.invocation+'/result.json');independent=read(a.independent)
assert native['native_exit_status']==native['outer_exit_status']==native['exit_status']==0
assert native['log_sha256']==sha(r/a.invocation/'output.log')
text=(r/a.invocation/'output.log').read_text();assert '** BUILD SUCCEEDED **' in text
assert plan['original_argv']==driver['command'][1:] and plan['mapped_argv']==setup['arguments']
assert plan['certificate_signing_ready'] and plan['signing_scope']=='certificate'
assert driver['credentials_differ'] and driver['new_certificate_SHA256']!=driver['previous_certificate_SHA256']
assert independent['verified'] and len(independent['checks'])==7
assert independent['public_certificate_SHA256']==driver['new_certificate_SHA256']
assert len(re.findall(r'^CodeSign ',text,re.M))==7
assert not re.search(r'^CompileC ',text,re.M)
assert len(re.findall(r'^PRIVATE_WORKSPACE_BIND ',text,re.M))==2
assert 'LINUXCODE_UTI_PREFLIGHT' not in text
for name,digest in setup['original_guards'].items():assert sha(r/name)==digest
record=dict(verified=True,host='Linux x86_64 Darling; no Mac',target='iPhoneOS arm64',
            PATH_launcher=driver['launcher'],native_build_status=0,outer_status=0,
            original_CI_arguments_retained=True,host_path_conversion_verified=True,
            original_xcodebuild_and_codesign=True,zsign_used=False,
            code_sign_tasks=7,independently_verified_products=7,CompileC_tasks=0,
            caller_supplied_identity_used=True,old_experiment_identity_required=False,
            public_certificate_SHA256=driver['new_certificate_SHA256'],
            previous_public_certificate_SHA256=driver['previous_certificate_SHA256'],
            test_fixture_certificate_only=True,test_profile_requirement_disabled=setup['test_fixture_profile_requirement_disabled'],
            developer_provisioning_or_device_trust_verified=False,
            no_repeated_UTI_or_service_list_diagnostics=True,
            prior_tamper_control_proof='artifacts/unity-certificate-products-independent-v1.json',
            tamper_controls_repeated=False,original_verified_build_preserved=True,
            application=setup['application'],candidate=setup['candidate'],
            references={name:sha(r/name) for name in [a.run+'/prepared.json',a.run+'/PATH-invocation.json',a.invocation+'/plan.json',a.invocation+'/result.json',a.independent]},
            source_inputs={name:sha(r/name) for name in ['distribution/linuxcode/linuxcode/cli.py','distribution/linuxcode/linuxcode/certificates.py','scripts/native-certificate-runtime.py']},
            log=a.invocation+'/output.log',log_sha256=native['log_sha256'],full_goal_complete=False)
out=r/a.report;assert not out.exists();out.write_text(json.dumps(record,indent=2)+'\n');print(out)
