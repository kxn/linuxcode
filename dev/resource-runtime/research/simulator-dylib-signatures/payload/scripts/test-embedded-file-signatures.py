#!/usr/bin/env python3
"""Check platform, Developer ID and ad-hoc identities against both fcntl policies."""
from pathlib import Path
import hashlib,json,struct,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;folder=Path(tempfile.mkdtemp(prefix='embedded-file-signature-controls-',dir=root/'runtime'))
checker=root/'runtime/simulator-dyld-signature-host-v3/check';results=[]
def signature(path):
 data=path.read_bytes();offset=0
 if data[:4]==bytes.fromhex('cafebabe'):
  choices=[struct.unpack_from('>IIIII',data,8+20*i) for i in range(struct.unpack_from('>I',data,4)[0])]
  offset=next(x[2] for x in choices if x[0]==0x1000007)
 at=offset+32
 for i in range(struct.unpack_from('<I',data,offset+16)[0]):
  command,size=struct.unpack_from('<II',data,at)
  if command==29:return offset,*struct.unpack_from('<II',data,at+8)
  at+=size
 raise ValueError('no signature')
def check(name,path,embedded,expected):
 offset,start,size=signature(path);cmd=[str(checker),str(path),str(offset),str(start),str(size)]+(['embedded'] if embedded else [])
 r=subprocess.run(cmd,capture_output=True,text=True);text=r.stdout+r.stderr
 passed=r.returncode==expected and 'Sanitizer' not in text and ('covered=0' in text if expected else 'covered=0 ' not in text)
 results.append(dict(name=name,passed=passed,command=cmd,status=r.returncode,output=text,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
dyld=root/json.loads((root/'runtime/dyld-sim-signature-reference-v1/metadata.json').read_text())['source'];swift=root/'runtime/state/prefix/usr/lib/swift/libswift_Concurrency.dylib';asset=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/Library/PrivateFrameworks/AssetCatalogFoundation.framework/AssetCatalogFoundation';adhoc=root/'runtime/embedded-signature-controls-v1/ad-hoc.dylib'
for name,path in [('platform-dyld',dyld),('platform-asset',asset)]:
 check(name+'-platform-policy',path,False,0);check(name+'-embedded-policy',path,True,0)
check('Developer-ID-with-recognized-critical-marker',swift,True,0)
check('Developer-ID-is-not-platform-identity',swift,False,1)
check('ad-hoc-code-coverage',adhoc,True,0)
check('ad-hoc-is-not-platform-identity',adhoc,False,1)
for name,path in [('Developer-ID',swift),('ad-hoc',adhoc),('platform',dyld)]:
 data=bytearray(path.read_bytes());offset,start,size=signature(path);data[offset+1024]^=1;bad=folder/(name+'-modified');bad.write_bytes(data);check(name+'-changed-code-page',bad,True,1)
report=dict(verified=all(x['passed'] for x in results),sanitizers=['address','undefined'],results=results,files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),root/'fixtures/hello/simulator-dyld-signature-host.cpp',root/'vendor/darlingserver/src/file-signatures.cpp']},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n')
for row in results:print(row['name'],row['passed'],row['output'].strip()[:150])
print('EVIDENCE',folder/'result.json');raise SystemExit(0 if report['verified'] else 1)
