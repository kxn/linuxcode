#!/usr/bin/env python3
"""Extend a verified immutable image with one exactly named original enum index."""
from pathlib import Path
import argparse,copy,fcntl,hashlib,json,os,runpy,struct,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',required=True);p.add_argument('--parent-inspection',required=True);p.add_argument('--target',required=True);p.add_argument('--provider',required=True);p.add_argument('--symbol',required=True);p.add_argument('--slot-offset',type=lambda s:int(s,0),required=True);p.add_argument('--expected-bytes',required=True);p.add_argument('--validate-only',action='store_true');p.add_argument('--instruction-offset',type=lambda s:int(s,0));p.add_argument('--instruction-bytes');args=p.parse_args()
assert (args.instruction_offset is None)==(args.instruction_bytes is None)
sha=lambda b:hashlib.sha256(b).hexdigest();manifest=root/'config/coregraphics-image-pins.json'
assert args.target and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.target)
assert args.symbol.startswith('_$s') and args.symbol.endswith('mFWC');expected=bytes.fromhex(args.expected_bytes);assert len(expected)==4 and struct.unpack('<I',expected)[0]<=65535
lock=(root/'runtime/resource-image-preparation.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX);raw=manifest.read_bytes();pins=json.loads(raw);assert args.parent in pins and args.target not in pins;pin=copy.deepcopy(pins[args.parent]);assert pin['preserve_code_with_patch_got'] and pin['preserve_swift_code_with_patch_got']
inspection=json.loads((root/args.parent_inspection).read_text());assert inspection['verified'] and inspection['original_code_bytes_equal'];parent=root/('runtime/rebuilt-'+args.parent)/Path(pin['path']).name;parent_report=json.loads(parent.with_name('reconstruction.json').read_text());assert sha(parent.read_bytes())==parent_report['staged_image_sha256']
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h','REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'});image=ns['image'](pin['path']);assert args.provider in image.dependencies;provider=ns['image'](args.provider);entry=provider.exports[args.symbol];assert entry[0]=='address' and entry[2]==0;address=entry[1];assert [(n,v) for n,v in provider.exports.items() if v[0]=='address' and v[1]==address]==[(args.symbol,entry)];assert any(start<=address<start+size and not flags&0x80000400 for _,_,start,size,flags in provider.sections)
slot=image.base+args.slot_offset;assert ns['pointer'](slot)==address;assert ns['read'](address,4)==expected
proof=dict(verified=True,parent=args.parent,parent_inspection=args.parent_inspection,parent_inspection_sha256=sha((root/args.parent_inspection).read_bytes()),parent_staged_image_sha256=sha(parent.read_bytes()),original_image=pin['path'],original_image_sha256=pin['sha256'],original_slot=hex(slot),original_slot_offset=hex(args.slot_offset),original_decoded_target=hex(address),symbol=args.symbol,provider=args.provider,original_literal_bytes=expected.hex(),original_literal_uint32=struct.unpack('<I',expected)[0],actual_provider_export_unique=True,original_slot_targets_exact_named_export=True,source='scripts/prepare-original-enum-case-candidate.py',source_sha256=sha(Path(__file__).read_bytes()))
assert not (root/('runtime/rebuilt-'+args.target)).exists();record=root/('artifacts/'+args.target+'-input.json');assert not record.exists()
if args.instruction_offset is not None:
 assert args.instruction_bytes
 row=dict(symbol=args.symbol,provider=args.provider,slot_offset=hex(args.slot_offset),instruction_offset=hex(args.instruction_offset),instruction_bytes=args.instruction_bytes,literal_bytes=expected.hex())
 validator='scripts/original-pooled-enum-index.py';contracts=runpy.run_path(str(root/validator))['validate'](ns,pin['path'],[row]);pin.setdefault('original_pooled_enum_indices',[]).append(row);proof['pooled_enum_contracts']=contracts;proof['pooled_enum_validator_sha256']=sha((root/validator).read_bytes())
else:
 pin.setdefault('cache_enum_case_literals',{});assert args.symbol not in pin['cache_enum_case_literals'];pin['cache_enum_case_literals'][args.symbol]=args.provider
if args.validate_only:print(json.dumps(proof,indent=2));raise SystemExit(0)
pins[args.target]=pin
subprocess.run(['python3','scripts/archive-source-inputs.py','config/coregraphics-image-pins.json'],cwd=root,check=True)
pending=manifest.with_suffix('.pending');pending.write_text(json.dumps(pins,indent=2)+'\n');os.replace(pending,manifest);lock.close()
command=['python3','scripts/rebuild-c-cache-image.py','--target-manifest','config/coregraphics-image-pins.json','--target',args.target,'--lazy-functions','--collect-missing-imports','--experimental-swift','--repair-swift-relative'];proof.update(target=args.target,pin=pin,previous_manifest_sha256=sha(raw),manifest_sha256=sha(manifest.read_bytes()),command=command,reconstruction_attempted=True,image_runtime_verified=False);record.write_text(json.dumps(proof,indent=2)+'\n');log=root/('logs/'+args.target+'-build.log');assert not log.exists()
with log.open('w') as out:status=subprocess.run(command,cwd=root,stdout=out,stderr=subprocess.STDOUT).returncode
proof.update(build_returncode=status,log=str(log.relative_to(root)),log_sha256=sha(log.read_bytes()));record.write_text(json.dumps(proof,indent=2)+'\n');print(record.relative_to(root));raise SystemExit(status)
