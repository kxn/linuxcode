#!/usr/bin/env python3
"""Prepare signed and unsigned self-owned Mach-O metadata fixtures on Linux."""
from pathlib import Path
import argparse,hashlib,json,plistlib,runpy,shutil,struct,subprocess,tempfile
ROOT=Path(__file__).resolve().parent.parent

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',default='runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk');p.add_argument('--zsign-build',default='artifacts/zsign-linux-build.json');a=p.parse_args()
 w=Path(tempfile.mkdtemp(prefix='csops-metadata-probe-',dir=ROOT/'runtime'));sdk=(ROOT/a.sdk).resolve(strict=True);source=ROOT/'fixtures/hello/csops-signature-metadata.c';obj=w/'probe.o';unsigned=w/'unsigned';signed=w/'signed';sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 zbuild=ROOT/a.zsign_build;zb=json.loads(zbuild.read_text());zsign=ROOT/zb['binary'];assert sha(zsign)==zb['binary_sha256']
 commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-framework','CoreFoundation','-framework','Security','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(unsigned)]]
 with (w/'build.log').open('w') as out:
  for cmd in commands:subprocess.run(cmd,cwd=ROOT,check=True,stdout=out,stderr=subprocess.STDOUT)
 shutil.copy2(unsigned,signed)
 ent=w/'entitlements.plist';ent.write_bytes(plistlib.dumps({'org.linuxcode.csops.true':True,'org.linuxcode.csops.false':False,'org.linuxcode.csops.text':'actual-file-metadata'}))
 sign=[str(zsign),'-a','-f','-b','org.linuxcode.csops-metadata-smoke','-e',str(ent),str(signed)]
 with (w/'host-sign.log').open('w') as out:subprocess.run(sign,cwd=ROOT,check=True,stdout=out,stderr=subprocess.STDOUT)
 check=runpy.run_path(str(ROOT/'scripts/verify-adhoc-macho-file.py'))['verify'](signed);assert check['verified']
 guards=runpy.run_path(str(ROOT/'scripts/build-pinned-platform-guards.py'));data=signed.read_bytes();meta=guards['signature_metadata'](data)
 for name in ['xml','der']:
  assert meta[name];(w/(name+'.blob')).write_bytes(meta[name])
 sig=data[meta['signature_offset']:meta['signature_offset']+meta['signature_capacity']];count=struct.unpack_from('>I',sig,8)[0];cd=None
 for i in range(count):
  slot,offset=struct.unpack_from('>II',sig,12+8*i)
  if slot==0:cd=sig[offset:offset+struct.unpack_from('>I',sig,offset+4)[0]]
 assert cd and cd[37] in [1,2,3,4];algorithm={1:'sha1',2:'sha256',3:'sha256',4:'sha384'}[cd[37]];(w/'cdhash.bin').write_bytes(hashlib.new(algorithm,cd).digest()[:20])
 # A one-slice FAT fixture exercises the real executable slice offset too.
 fat=w/'signed-fat';raw=unsigned.read_bytes();cpu,sub=struct.unpack_from('<II',raw,4)
 fat.write_bytes(struct.pack('>7I',0xcafebabe,1,cpu,sub,4096,len(raw),12)+bytes(4096-28)+raw);fat.chmod(0o755)
 fat_sign=[*sign[:-1],str(fat)]
 with (w/'host-sign-fat.log').open('w') as out:subprocess.run(fat_sign,cwd=ROOT,check=True,stdout=out,stderr=subprocess.STDOUT)
 fat_check=runpy.run_path(str(ROOT/'scripts/verify-adhoc-macho-file.py'))['verify'](fat);assert fat_check['verified']
 fat_arch=next(x for x in guards['slices'](fat.read_bytes()) if x['cpu_type']==0x1000007);fat_meta=guards['signature_metadata'](fat_arch['data'])
 for name in ['xml','der']:(w/('fat-'+name+'.blob')).write_bytes(fat_meta[name])
 fsig=fat_arch['data'][fat_meta['signature_offset']:fat_meta['signature_offset']+fat_meta['signature_capacity']]
 for i in range(struct.unpack_from('>I',fsig,8)[0]):
  slot,offset=struct.unpack_from('>II',fsig,12+8*i)
  if slot==0:
   fcd=fsig[offset:offset+struct.unpack_from('>I',fsig,offset+4)[0]];(w/'fat-cdhash.bin').write_bytes(hashlib.new({1:'sha1',2:'sha256',3:'sha256',4:'sha384'}[fcd[37]],fcd).digest()[:20])
 inputs=[Path(__file__),source,unsigned,signed,fat,ent,w/'xml.blob',w/'der.blob',w/'cdhash.bin',w/'fat-xml.blob',w/'fat-der.blob',w/'fat-cdhash.bin',zbuild,zsign]
 report=dict(prepared=True,native_execution_attempted=False,source=str(source.relative_to(ROOT)),unsigned=str(unsigned.relative_to(ROOT)),signed=str(signed.relative_to(ROOT)),xml_blob=str((w/'xml.blob').relative_to(ROOT)),der_blob=str((w/'der.blob').relative_to(ROOT)),cdhash=str((w/'cdhash.bin').relative_to(ROOT)),build_commands=commands,sign_command=sign,independent_signature_check=check,own_fixture_only=True,certificate_or_Apple_platform_identity_claimed=False,files={str(path.relative_to(ROOT)):sha(path) for path in inputs})
 report['fat']={name:str(path.relative_to(ROOT)) for name,path in [('signed',fat),('xml_blob',w/'fat-xml.blob'),('der_blob',w/'fat-der.blob'),('cdhash',w/'fat-cdhash.bin')]};report['fat_independent_signature_check']=fat_check;report['fat_sign_command']=fat_sign
 (w/'prepared.json').write_text(json.dumps(report,indent=2)+'\n');print(w/'prepared.json')
if __name__=='__main__':main()
