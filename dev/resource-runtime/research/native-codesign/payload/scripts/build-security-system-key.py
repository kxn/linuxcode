#!/usr/bin/env python3
"""Expose real native token-key lookup through the newer SystemKey API."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,subprocess
a=argparse.ArgumentParser();a.add_argument('--tag',required=True);args=a.parse_args();assert re.fullmatch('[a-z0-9-]+',args.tag)
r=Path(__file__).resolve().parent.parent;w=r/('runtime/security-system-key-'+args.tag);assert not w.exists();w.mkdir()
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';src=r/'vendor/darling/src/external/security/OSX/sec/Security/SecSystemKey.c';obj=w/'system-key.o'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(src),'-o',str(obj)],check=True)
library=w/'libraries/libDarlingSecuritySystemKey.dylib';library.parent.mkdir();subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreFoundation','-framework','Security','-lSystem','-install_name','/usr/lib/'+library.name,str(obj),'-o',str(library)],check=True)
base=r/'runtime/local-identity-store-readonly-v2/frameworks/Security.framework/Versions/A/Security'
payload,changes=runpy.run_path(str(r/'scripts/macho-named-reexport.py'))['add'](base.read_bytes(),'/usr/lib/'+library.name,['_SecKeyCopySystemKey'])
target=w/'frameworks/Security.framework/Versions/A/Security';target.parent.mkdir(parents=True);target.write_bytes(payload);f=target.parents[2];(f/'Versions/Current').symlink_to('A');(f/'Security').symlink_to('Versions/Current/Security')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();record=dict(root=str(w.relative_to(r)),framework=str(target.relative_to(r)),library=str(library.relative_to(r)),files={str(p.relative_to(r)):sha(p) for p in [src,base,library,target,r/'runtime/security-upstream-reference/source.json']},changes=changes,builtin_key_generation_implemented=False,hardware_or_attestation_success_verified=False,native_token_key_lookup_delegated=True,installed=False)
(r/('artifacts/security-system-key-'+args.tag+'-stage.json')).write_text(json.dumps(record,indent=2)+'\n');print('Built native token-key lookup API; no replacement device keys')
