#!/usr/bin/env python3
"""Independently check actual ExtensionKit protocol pointer relocation with LLVM.

Checks file layout and real dyld rebase entries, not runtime protocol semantics.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, runpy, struct, subprocess
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='artifacts/objc-protocol-got-relocation.json')
args=parser.parse_args()
report=root/args.output
assert not report.exists(), 'Keep earlier evidence immutable; choose a new --output'
pins=json.loads((root/'config/ios-resource-image-pins.json').read_text());pin=pins['extensionkit-resource-native']
source=root/('runtime/fullsystem-libraries'+pin['path']);output=root/'runtime/rebuilt-extensionkit-resource-native/ExtensionKit'
assert hashlib.sha256(source.read_bytes()).hexdigest()==pin['sha256']
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
 'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
 'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
obj=ns['image'](pin['path']);read,pointer=ns['read'],ns['pointer'];local_protocols={}
for name,segment,address,length,flags in obj.sections:
 if name=='__objc_protolist':
  for offset in range(0,length,8):
   target=pointer(address+offset);name=read(pointer(target+8),512).split(b'\0')[0].decode()
   local_protocols[name]=target
# These are the two genuinely unexported original cache pointers that failed
# reconstruction; expected definitions come independently from the input list.
original_targets={0x7ff843543930:'BSServiceConnectionListenerDelegate',0x7ff8436e7e10:'_EXViewServiceApplicationDelegate'}
slots={target:set() for target in original_targets}
for name,segment,address,length,flags in obj.sections:
 if name=='__objc_const' and segment=='__DATA_CONST':
  assert length%8==0
  for slot in range(address,address+length,8):
   target=pointer(slot)
   if target in slots:slots[target].add(slot)
assert set(slots)==set(original_targets)
assert all(slots.values()), 'Both original unexported protocol references must be present'
data=output.read_bytes();segments=[];cursor=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 command,size=struct.unpack_from('<II',data,cursor)
 if command==0x19:
  vm,length,fileoff,filesize=struct.unpack_from('<QQQQ',data,cursor+24);segments.append((vm,length,fileoff,filesize))
 cursor+=size
def offset(address):
 for vm,length,fileoff,filesize in segments:
  if vm<=address<=vm+filesize-8:return fileoff+address-vm
 raise AssertionError('Reference outside output file-backed segments')
llvm=subprocess.check_output(['llvm-objdump-19','--macho','--rebase',str(output)],text=True)
rebases={int(match[1],16) for line in llvm.splitlines() if (match:=re.search(r'\s(0x[0-9A-Fa-f]+)\s+pointer$',line))}
checks=0;records=[]
for original,name in original_targets.items():
 assert read(pointer(original+8),512).split(b'\0')[0].decode()==name
 local=local_protocols[name];assert local!=original
 assert struct.unpack('<II',read(local+64,8))==(96,0)
 expected=local-obj.base
 for original_slot in slots[original]:
  relative_slot=original_slot-obj.base;at=offset(relative_slot)
  def verify(payload,entries):
   assert struct.unpack_from('<Q',payload,at)[0]==expected,'Metadata must point to the original local definition'
   assert relative_slot in entries,'Actual dyld rebase entry is required'
  verify(data,rebases);checks+=1
  # Returning the stale cache address must fail independently of the builder.
  bad=bytearray(data);struct.pack_into('<Q',bad,at,original)
  try:verify(bad,rebases)
  except AssertionError:checks+=1
  else:raise AssertionError('Stale canonical pointer accepted')
  try:verify(data,rebases-{relative_slot})
  except AssertionError:checks+=1
  else:raise AssertionError('Missing dyld relocation accepted')
  records.append(dict(protocol=name,original_cache_pointer=hex(original),local_original_definition=hex(local),original_slot=hex(original_slot),output_slot=hex(relative_slot)))
assert checks>=6
paths=['scripts/restore-objc-metadata.py','scripts/rebuild-c-cache-image.py','scripts/test-objc-protocol-got.py',str(source.relative_to(root)),str(output.relative_to(root))]
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),verified=True,checks=checks,records=records,
 oracle='llvm-objdump-19 actual Mach-O rebase table and independent original __objc_protolist',
 sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths},
 full_ExtensionKit_runtime_verified=False,resource_compilation_verified=False)
report.parent.mkdir(parents=True,exist_ok=True)
report.write_text(json.dumps(record,indent=2)+'\n')
print('Original protocol pointer checks passed:',checks)
