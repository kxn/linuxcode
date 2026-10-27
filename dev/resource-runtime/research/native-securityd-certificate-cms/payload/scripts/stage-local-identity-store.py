#!/usr/bin/env python3
"""Build an opt-in native Security identity query facade without changing defaults."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, struct, subprocess, runpy, plistlib
r=Path(__file__).resolve().parent.parent
a=argparse.ArgumentParser();a.add_argument('--tag',required=True);a.add_argument('--export-overlay-base');a.add_argument('--backend-base');a.add_argument('--csparser-build');args=a.parse_args()
assert re.fullmatch('[a-z0-9-]+',args.tag)
w=r/('runtime/local-identity-store-'+args.tag);assert not w.exists();w.mkdir()
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
base=r/(args.backend_base or 'runtime/security-cryptokit-constants/frameworks/Security.framework/Versions/A/Security')
source=r/'vendor/darling/src/external/security/OSX/sec/Security/SecLocalIdentityStore.c'
backend=w/'libraries/libDarlingLocalIdentitySecurityBackend.dylib';backend.parent.mkdir();shutil.copyfile(base,backend)
payload=bytearray(backend.read_bytes());assert struct.unpack_from('<I',payload)[0]==0xfeedfacf
offset=32;changed=0
for _ in range(struct.unpack_from('<I',payload,16)[0]):
    cmd,size=struct.unpack_from('<II',payload,offset)
    if cmd==0xd:
        start=offset+struct.unpack_from('<I',payload,offset+8)[0];end=offset+size
        name=('/usr/lib/'+backend.name).encode()+b'\0';assert len(name)<=end-start
        payload[start:end]=name+b'\0'*(end-start-len(name));changed+=1
    offset+=size
assert changed==1;backend.write_bytes(payload)
obj=w/'store.o'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-Wno-deprecated-declarations','-c',str(source),'-o',str(obj)],check=True)
library=w/'frameworks/Security.framework/Versions/A/Security';library.parent.mkdir(parents=True)
subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreFoundation','-lSystem','-install_name','/System/Library/Frameworks/Security.framework/Versions/A/Security','-compatibility_version','1.0.0','-current_version','60157.40.30','-headerpad','0x1000','-reexport_library',str(backend),str(obj),'-o',str(library)],check=True)
framework=library.parents[2];(framework/'Versions/Current').symlink_to('A');(framework/'Security').symlink_to('Versions/Current/Security')
overlay_inputs=[]
if args.export_overlay_base:
    facade=w/'libraries/libDarlingLocalIdentityStore.dylib'
    subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreFoundation','-lSystem','-install_name','/usr/lib/'+facade.name,'-reexport_library',str(backend),str(obj),'-o',str(facade)],check=True)
    overlay_base=r/args.export_overlay_base
    payload,_=runpy.run_path(str(r/'scripts/macho-named-reexport.py'))['add'](overlay_base.read_bytes(),'/usr/lib/'+facade.name,['_SecItemCopyMatching','_SecIdentityCopyPreference','_SecItemCopyParentCertificates_osx'],replace_existing=True)
    library.write_bytes(payload);overlay_inputs=[overlay_base,facade]
if args.csparser_build:
    parser=json.loads((r/args.csparser_build).read_text());parser_binary=r/parser['binary'];assert hashlib.sha256(parser_binary.read_bytes()).hexdigest()==parser['binary_sha256']
    bundle=library.parent/'PlugIns/csparser.bundle';shutil.copytree(r/parser['bundle'],bundle)
    resources=library.parent/'Resources';resources.mkdir()
    original_resources=r/'runtime/rootfs/usr/libexec/darling/System/Library/Frameworks/Security.framework/Versions/A/Resources'
    for resource in original_resources.iterdir():
        if resource.is_file() and resource.suffix in ('.mds','.mdsinfo'):
            target=resources/resource.name;shutil.copy2(resource,target);overlay_inputs += [resource,target]
    (resources/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='com.apple.security',CFBundleExecutable='Security',CFBundleName='Security compatibility',CFBundlePackageType='FMWK',CFBundleVersion='59306.61.1')))
    (framework/'Resources').symlink_to('Versions/Current/Resources');(framework/'PlugIns').symlink_to('Versions/Current/PlugIns')
    overlay_inputs += [parser_binary,*[p for p in bundle.rglob('*') if p.is_file()],resources/'Info.plist']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(source=str(source.relative_to(r)),framework=str(library.relative_to(r)),root=str(w.relative_to(r)),files={str(p.relative_to(r)):sha(p) for p in [source,base,backend,library,*overlay_inputs]},read_only=True,encrypted_store=False,certificate_trust_evaluated=False,supported_key_types=['RSA PKCS1 DER'],installed=False)
report=r/('artifacts/local-identity-store-'+args.tag+'-stage.json');assert not report.exists();report.write_text(json.dumps(record,indent=2)+'\n');print(report)
