#!/usr/bin/env python3
"""Reject memory-only payload mutations in the actual signed App and FAT slices."""
from pathlib import Path
import argparse,hashlib,json,runpy,struct
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',required=True);p.add_argument('--report',required=True);a=p.parse_args();app=r/a.app;verify=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify'];results=[]
for bundle in [app,app/'Frameworks/libHarfBuzzSharp.framework']:
 import plistlib
 info=plistlib.loads((bundle/'Info.plist').read_bytes());binary=bundle/info['CFBundleExecutable'];original=binary.read_bytes();slices=[(0,len(original))]
 if original[:4]==b'\xca\xfe\xba\xbe':
  slices=[struct.unpack_from('>II',original,8+20*i+8) for i in range(struct.unpack_from('>I',original,4)[0])]
 for index,(offset,size) in enumerate(slices):
  assert size>0x5000;corrupt=bytearray(original);corrupt[offset+0x4000]^=1
  try:verify(bundle,bytes(corrupt))
  except AssertionError as error:
   assert 'code page hash mismatch' in str(error);results.append(dict(bundle=str(bundle.relative_to(r)),slice=index,mutation='in-memory signed code page',rejected=True,reason=str(error)))
  else:raise AssertionError('Tampered signed payload was accepted')
 assert binary.read_bytes()==original
assert len(results)==3
destination=r/a.report;assert not destination.exists();destination.write_text(json.dumps(dict(verified=True,cases=results,actual_products_modified=False,verifier_sha256=hashlib.sha256((r/'scripts/verify-adhoc-bundle.py').read_bytes()).hexdigest()),indent=2)+'\n');print('THIN_APP_AND_BOTH_FAT_SLICES_REJECT_TAMPERING')
