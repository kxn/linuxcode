#!/usr/bin/env python3
"""Recover one proven original Swift Any pool binding in a fresh AppKit image."""
from pathlib import Path
import argparse,copy,fcntl,hashlib,json,os,runpy,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for n in ['parent','parent-inspection','target']:p.add_argument('--'+n,required=True)
p.add_argument('--validate-only',action='store_true');args=p.parse_args();assert args.target and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.target)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();manifest=root/'config/coregraphics-image-pins.json'
with (root/'runtime/resource-image-preparation.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);raw=manifest.read_bytes();pins=json.loads(raw);assert args.target not in pins;pin=copy.deepcopy(pins[args.parent]);inspection=json.loads((root/args.parent_inspection).read_text());source=root/('runtime/rebuilt-'+args.parent+'/AppKit');old=json.loads(source.with_name('reconstruction.json').read_text());assert inspection['verified'] and inspection['original_code_bytes_equal'] and inspection['files'][str(source.relative_to(root))]==sha(source)==old['staged_image_sha256']
 assert pin['path']=='/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit' and pin['preserve_code_with_patch_got'] and pin['preserve_swift_code_with_patch_got'];assert not pin.get('original_pooled_swift_any')
 row=dict(symbol='_$sypN',provider='/usr/lib/swift/libswiftCore.dylib',slot_offset='0x392ae880',instruction_offset='0x5c426c',instruction_bytes='488b350da6ce384883c608')
 ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h','REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
 validator='scripts/original-pooled-swift-any.py';proof=runpy.run_path(str(root/validator))['validate'](ns,pin['path'],[row]);pin['original_pooled_swift_any']=[row]
 if args.validate_only:print(json.dumps(proof,indent=2));raise SystemExit(0)
 record=root/('artifacts/'+args.target+'-input.json');assert not record.exists() and not (root/('runtime/rebuilt-'+args.target)).exists();subprocess.run(['python3','scripts/archive-source-inputs.py','config/coregraphics-image-pins.json'],cwd=root,check=True);pins[args.target]=pin;pending=manifest.with_suffix('.pending');pending.write_text(json.dumps(pins,indent=2)+'\n');os.replace(pending,manifest)
command=['python3','scripts/rebuild-c-cache-image.py','--target-manifest','config/coregraphics-image-pins.json','--target',args.target,'--lazy-functions','--collect-missing-imports','--experimental-swift','--repair-swift-relative'];log=root/('logs/'+args.target+'-build.log');assert not log.exists()
d=dict(target=args.target,parent=args.parent,parent_inspection=args.parent_inspection,parent_staged_image_sha256=sha(source),previous_manifest_sha256=hashlib.sha256(raw).hexdigest(),manifest_sha256=sha(manifest),pin=pin,original_contract=proof,source_sha256=sha(Path(__file__)),validator_sha256=sha(root/validator),command=command,runtime_verified=False)
record.write_text(json.dumps(d,indent=2)+'\n')
with log.open('w') as out:status=subprocess.run(command,cwd=root,stdout=out,stderr=subprocess.STDOUT).returncode
d.update(build_status=status,log=str(log.relative_to(root)),log_sha256=sha(log));record.write_text(json.dumps(d,indent=2)+'\n');print(record.relative_to(root));raise SystemExit(status)
