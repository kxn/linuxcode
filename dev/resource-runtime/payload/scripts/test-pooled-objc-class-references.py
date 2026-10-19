#!/usr/bin/env python3
"""Check actual pooled class-reference tables, relocations, bindings and rejection.

Uses LLVM as the relocation oracle. Does not claim framework API execution.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy, hashlib, json, re, runpy, struct, subprocess, sys
root=Path(__file__).resolve().parent.parent
pins=json.loads((root/'config/ios-resource-image-pins.json').read_text())
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
 'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
 'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
folder=root/'runtime/pooled-objc-class-reference-tests';folder.mkdir(exist_ok=True)
checks=0;cases=[];files={}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for target in ['onboardingkit-resource-native','telephonyutilities-resource-native']:
 pin=pins[target];original=root/('runtime/fullsystem-libraries'+pin['path']);assert digest(original)==pin['sha256']
 obj=ns['image'](pin['path']);binary=root/('runtime/rebuilt-'+target+'/'+Path(pin['path']).name);data=binary.read_bytes();segments=[];cursor=32
 for _ in range(struct.unpack_from('<I',data,16)[0]):
  cmd,size=struct.unpack_from('<II',data,cursor)
  if cmd==0x19:segments.append(struct.unpack_from('<QQQQ',data,cursor+24))
  cursor+=size
 def fileoff(address):
  for vm,length,offset,size in segments:
   if vm<=address<=vm+size-8:return offset+address-vm
  raise AssertionError('Recovered pointer is outside file-backed segments')
 rebase_text=subprocess.check_output(['llvm-objdump-19','--macho','--rebase',str(binary)],text=True)
 bind_text=subprocess.check_output(['llvm-objdump-19','--macho','--bind',str(binary)],text=True)
 rebases={int(m[1],16) for line in rebase_text.splitlines() if (m:=re.search(r'\s(0x[0-9A-Fa-f]+)\s+pointer$',line))}
 bindings={int(parts[2],16):(int(parts[4]),parts[5],parts[6]) for line in bind_text.splitlines() if len(parts:=line.split())==7 and parts[3]=='pointer'}
 cell_sets=[]
 for record in pin['cache_objc_class_reference_cells']:
  original_cell=int(record['address'],16);class_address=ns['resolve'](record['provider'],record['symbol']);assert ns['pointer'](original_cell)==class_address
  cells=set()
  for address in record['references']:
   address=int(address,16);assert ns['pointer'](address)==original_cell
   slot=address-obj.base;at=fileoff(slot);cell=struct.unpack_from('<Q',data,at)[0];cells.add(cell)
   def verify(payload,relocations,binds):
    assert slot in relocations,'Table slot needs a real dyld rebase'
    value=struct.unpack_from('<Q',payload,at)[0]
    assert value==cell,'Table must preserve the address of the recovered Class cell'
    assert struct.unpack_from('<Q',payload,fileoff(value))[0]==0,'Class cell must await the real symbol binding'
    assert binds[value]==(0,'Foundation','_OBJC_CLASS_$_NSString'),'Class cell needs the original Class binding'
   verify(data,rebases,bindings);checks+=1
   bad=bytearray(data);struct.pack_into('<Q',bad,at,class_address)
   wrong_bindings=dict(bindings);wrong_bindings[cell]=(0,'Foundation','_OBJC_CLASS_$_NSNumber')
   for label,payload,relocations,binds in [('flattened_pointer',bad,rebases,bindings),('missing_rebase',data,rebases-{slot},bindings),('missing_binding',data,rebases,{k:v for k,v in bindings.items() if k!=cell}),('wrong_class',data,rebases,wrong_bindings)]:
    try:verify(payload,relocations,binds)
    except (AssertionError,KeyError):checks+=1
    else:raise AssertionError('Invalid class-reference relocation accepted: '+label)
  assert len(cells)==1,'Repeated references must share one recovered cell';checks+=1
  cell_sets.append(dict(original_cell=hex(original_cell),restored_cell=hex(next(iter(cells))),symbol=record['symbol'],references=record['references']))
 cases.append(dict(target=target,tables=cell_sets,binary_sha256=digest(binary),full_framework_execution_verified=False))
 files[str(binary.relative_to(root))]=digest(binary)
# Exercise the actual reconstruction entry point with changed pinned records.
base=pins['onboardingkit-resource-native'];damaged=[]
for label in ['wrong_class','reference_outside_section','misaligned_cell','cell_inside_image','duplicate_cell','omitted_table_slot']:
 config=copy.deepcopy(base);record=config['cache_objc_class_reference_cells'][0]
 if label=='wrong_class':record['symbol']='_OBJC_CLASS_$_NSNumber'
 elif label=='reference_outside_section':record['references'][0]='0x1000'
 elif label=='misaligned_cell':record['address']=hex(int(record['address'],16)+1)
 elif label=='cell_inside_image':record['address']=record['references'][0]
 elif label=='duplicate_cell':config['cache_objc_class_reference_cells'].append(copy.deepcopy(record))
 elif label=='omitted_table_slot':record['references'].pop()
 target='class-cell-reject-'+label.replace('_','-');manifest=folder/(label+'.json');manifest.write_text(json.dumps({target:config},indent=2)+'\n')
 output=root/('runtime/rebuilt-'+target+'/OnBoardingKit');assert not output.exists()
 log=folder/(label+'.log')
 with log.open('w') as stream:r=subprocess.run([sys.executable,str(root/'scripts/rebuild-c-cache-image.py'),'--target-manifest',str(manifest),'--target',target,'--experimental-swift','--repair-swift-relative','--analyze-code'],cwd=root,stdout=stream,stderr=subprocess.STDOUT)
 assert r.returncode!=0 and not output.exists(),label
 text=log.read_text();assert ('class-reference' in text or 'Unclassified cache pointer' in text),text[-1500:]
 checks+=1;damaged.append(label);files[str(log.relative_to(root))]=digest(log);files[str(manifest.relative_to(root))]=digest(manifest)
for name in ['scripts/rebuild-c-cache-image.py','scripts/test-pooled-objc-class-references.py','config/ios-resource-image-pins.json']:
 files[name]=digest(root/name)
report=dict(checked_at=datetime.now(timezone.utc).isoformat(),verified=True,checks=checks,cases=cases,
 damaged_pins_rejected_without_image=damaged,oracle='LLVM actual rebase/bind tables plus independent original cache pointer reads',
 files=files,full_OnBoardingKit_or_TelephonyUtilities_execution_verified=False,resource_compilation_verified=False)
p=root/'artifacts/pooled-objc-class-reference-relocation.json';assert not p.exists();p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2)+'\n')
print('Pooled Objective-C Class reference checks passed:',checks)
