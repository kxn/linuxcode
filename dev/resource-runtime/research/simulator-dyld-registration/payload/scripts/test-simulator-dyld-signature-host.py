#!/usr/bin/env python3
"""Exercise real Apple CMS, code coverage and malformed command-83 inputs."""
from pathlib import Path
import hashlib,json,shutil,struct,subprocess,tempfile

root=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='simulator-dyld-signature-controls-',dir=root/'runtime'))
metadata=json.loads((root/'runtime/dyld-sim-signature-reference-v1/metadata.json').read_text())
source=root/metadata['source']; original=source.read_bytes()
assert hashlib.sha256(original).hexdigest()==metadata['source_sha256']
binary=root/'runtime/simulator-dyld-signature-host-v1/check'
offset=metadata['slice_offset'];start=metadata['signature_offset'];size=metadata['signature_size'];base=offset+start
count=struct.unpack_from('>I',original,base+8)[0]
blobs={struct.unpack_from('>I',original,base+12+i*8)[0]:struct.unpack_from('>I',original,base+16+i*8)[0] for i in range(count)}
results=[]
def check(name,data=None,arguments=None,expected=1,contains=None):
    path=source
    if data is not None:
        path=folder/(name+'.macho');path.write_bytes(data)
    args=arguments or [str(path),str(offset),str(start),str(size)]
    result=subprocess.run([str(binary),*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    ok=result.returncode==expected and (contains is None or contains in result.stdout) and 'Sanitizer' not in result.stdout
    results.append(dict(name=name,returncode=result.returncode,output=result.stdout,passed=ok))
check('genuine-Apple-Intel-dyld',expected=0,contains='covered=639920')
for name,at in [('modified-code-page',offset+4096),('modified-CodeDirectory',base+blobs[0]+20),('modified-CMS',base+blobs[65536]+100),('modified-requirements',base+blobs[2]+12)]:
    data=bytearray(original);data[at]^=1;check(name,data,contains='covered=0')
data=bytearray(original);struct.pack_into('>I',data,base+20,0);check('duplicate-signature-slot',data,contains='covered=0')
data=bytearray(original);struct.pack_into('>I',data,base+16,0xffffffff);check('out-of-bounds-signature-slot',data,contains='covered=0')
data=bytearray(original);struct.pack_into('>I',data,base+8,0xffffffff);check('oversized-signature-index',data,contains='covered=0')
check('truncated-file',original[:base+50],contains='covered=0')
for name,args in [('wrong-slice',[str(source),'0',str(start),str(size)]),('wrong-signature-offset',[str(source),str(offset),str(start+1),str(size)]),('oversized-signature',[str(source),str(offset),str(start),str(41*1024*1024)]),('bad-descriptor',[str(folder/'absent'),str(offset),str(start),str(size)]),('nonregular-descriptor',[str(folder),str(offset),str(start),str(size)])]:
    check(name,arguments=args,contains='covered=0')
report=dict(verified=all(x['passed'] for x in results),sanitizers=['address','undefined'],reference_source_sha256=metadata['source_sha256'],results=results,files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),root/'fixtures/hello/simulator-dyld-signature-host.cpp',root/'vendor/darlingserver/src/file-signatures.cpp',root/'vendor/darlingserver/internal-include/darlingserver/apple-code-signing-roots.hpp']},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n')
for row in results:print(row['name'],row['passed'],row['output'].strip()[:160])
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if report['verified'] else 1)
