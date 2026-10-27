#!/usr/bin/env python3
"""Add verified identifiers and local native signer compatibility; reject remote signing."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,subprocess
a=argparse.ArgumentParser();a.add_argument('--tag',required=True);a.add_argument('--debug-stop',action='store_true');args=a.parse_args();assert re.fullmatch('[a-z0-9-]+',args.tag)
r=Path(__file__).resolve().parent.parent;w=r/('runtime/security-code-signer-compat-'+args.tag);assert not w.exists();w.mkdir()
reference=r/'artifacts/original-codesign-security-constant-reference.json';ref=json.loads(reference.read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(r/'runtime/fullsystem-libraries'/ref['provider'].lstrip('/'))==ref['provider_sha256']
constants=w/'constants.c';constants.write_text('#include <CoreFoundation/CoreFoundation.h>\n'+''.join('const CFStringRef '+n[1:]+' = CFSTR('+json.dumps(v)+');\n' for n,v in ref['native_CFString_values'].items()))
source=r/'vendor/darling/src/external/security/OSX/sec/Security/SecCodeSignerCompatibility.c';sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';objects=[]
for src in [constants,source]:
    obj=w/(src.stem+'.o');subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-Wno-deprecated-declarations',*(['-DLINUXCODE_CODESIGN_BREAKPOINT=1'] if args.debug_stop else []),'-c',str(src),'-o',str(obj)],check=True);objects.append(str(obj))
library=w/'libraries/libDarlingSecurityCodeSignerCompatibility.dylib';library.parent.mkdir();subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreFoundation','-framework','Security','-lSystem','-install_name','/usr/lib/'+library.name,*objects,'-o',str(library)],check=True)
base=r/'runtime/security-system-key-v2/frameworks/Security.framework/Versions/A/Security';names=list(ref['native_CFString_values'])+['_SecCodeSignerCreate','_SecCodeSignerRemoteCreate','_SecCodeSignerRemoteAddSignature','_SecTrustCopyCertificateChain'];payload,changes=runpy.run_path(str(r/'scripts/macho-named-reexport.py'))['add'](base.read_bytes(),'/usr/lib/'+library.name,names)
target=w/'frameworks/Security.framework/Versions/A/Security';target.parent.mkdir(parents=True);target.write_bytes(payload);f=target.parents[2];(f/'Versions/Current').symlink_to('A');(f/'Security').symlink_to('Versions/Current/Security')
support=r/'runtime/security-system-key-v2/libraries/libDarlingSecuritySystemKey.dylib'
record=dict(root=str(w.relative_to(r)),framework=str(target.relative_to(r)),library=str(library.relative_to(r)),support_libraries=[str(support.relative_to(r))],files={str(p.relative_to(r)):sha(p) for p in [source,constants,base,library,target,reference,support]},changes=changes,remote_signing_implemented=False,new_constraints_implemented=False,native_local_code_signing_delegated=True,installed=False)
(r/('artifacts/security-code-signer-compat-'+args.tag+'-stage.json')).write_text(json.dumps(record,indent=2)+'\n');print('Built native local signer compatibility; remote/constraint requests return errors')
