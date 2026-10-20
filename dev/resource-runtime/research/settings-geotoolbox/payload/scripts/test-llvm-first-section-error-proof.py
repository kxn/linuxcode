#!/usr/bin/env python3
"""Verify exact LLVM error opcodes and unchanged decoding of all Settings binds."""
from pathlib import Path
import argparse,hashlib,json,runpy,struct
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
output=root/args.output;assert not output.exists()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
current=runpy.run_path(str(root/'scripts/inspect-preserved-patch-got.py'))
batch=json.loads((root/'runtime/original-dyld-validation-batch-u3l47obx/result.json').read_text());assert batch['verified']
first='artifacts/'+batch['reports'][0]['target']+'-independent-inspection.json'
old_sha=json.loads((root/first).read_text())['files']['scripts/inspect-preserved-patch-got.py']
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
old_path=resolve('scripts/inspect-preserved-patch-got.py',old_sha);old=runpy.run_path(str(old_path))
streams_checked=0
for row in batch['reports']:
    validation=json.loads((root/row['report']).read_text());data=(root/validation['image']).read_bytes()
    assert sha(validation['image'])==validation['image_sha256']
    _,_,streams=current['macho'](data)
    for label,index in [('eager',2),('lazy',6)]:
        offset,size=streams[index:index+2];blob=data[offset:offset+size]
        assert current['binding_stream'](blob,label=='lazy')==old['binding_stream'](blob,label=='lazy')
        streams_checked+=1
cases=[];rejected=[]
for inspection in ['artifacts/remoteui-closure-liftui-resource-v2-independent-inspection.json',
                   'artifacts/settings-closure-relevancekit-resource-v2-independent-inspection.json']:
    report=json.loads((root/inspection).read_text());limitation=report['LLVM_first_section_base_limitation']
    validation=json.loads((root/limitation['original_validator']).read_text());assert validation['verified']
    data=(root/validation['image']).read_bytes();error=limitation['stderr'];proof=current['first_section_error_proof'](data,error)
    cases.append(dict(image=validation['image'],image_sha256=sha(validation['image']),reported_opcode_proof=proof))
    reason=proof[0]['reported_error'];other='not in section' if reason!='not in section' else 'extends beyond section boundary'
    changes=[('wrong_reason',error.replace(reason,other)),('unknown_error',error.replace('bad offset, '+reason,'unrelated failure')),
             ('wrong_opcode',error.replace(proof[0]['opcode_offset'],'0xffffffff'))]
    for name,changed in changes:
        try:current['first_section_error_proof'](data,changed)
        except AssertionError:rejected.append(dict(image=validation['image'],control=name))
        else:raise AssertionError('Accepted mismatched LLVM error '+name)
report=dict(verified=True,actual_diagnostic_cases=cases,rejected_diagnostic_controls=rejected,
    prior_decoded_binding_streams_exactly_unchanged=streams_checked,original_images=61,
    old_parser_sha256=old_sha,old_parser_snapshot=str(old_path),
    sources={n:sha(n) for n in ['scripts/inspect-preserved-patch-got.py','scripts/test-llvm-first-section-error-proof.py']},
    runtime_behavior_verified=False)
output.write_text(json.dumps(report,indent=2)+'\n');print('VERIFIED',streams_checked,'unchanged streams and',len(rejected),'rejecting diagnostics')
