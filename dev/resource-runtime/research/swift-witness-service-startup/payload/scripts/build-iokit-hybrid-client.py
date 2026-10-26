#!/usr/bin/env python3
"""Compose source IOKit registry clients with retained original extra exports."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,struct,subprocess
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert re.fullmatch('[a-z0-9-]+',a.tag);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();cfg=json.loads((r/a.configuration).read_text());stage=r/cfg['resource_overlay_stage'];overlay=json.loads(stage.read_text());original=r/overlay['frameworks']/'IOKit.framework/Versions/A/IOKit';legacy=r/'runtime/foundation-native-library-stage/libDarlingIOKitBackend.dylib';w=r/('runtime/iokit-hybrid-client-'+a.tag);assert not w.exists();w.mkdir();libraries=w/'libraries';libraries.mkdir();extra=libraries/'libLinuxcodeOriginalIOKit.dylib';shutil.copy2(original,extra);subprocess.run(['python3',str(r/'scripts/macho-set-id.py'),str(extra),'/usr/lib/libLinuxcodeOriginalIOKit.dylib'],check=True)
def code_sections(path):
 d=path.read_bytes();assert d[:8]==bytes.fromhex('cffaedfe07000001');at=32;out={}
 for _ in range(struct.unpack_from('<I',d,16)[0]):
  cmd,size=struct.unpack_from('<II',d,at)
  if cmd==0x19:
   count=struct.unpack_from('<I',d,at+64)[0]
   for i in range(count):
    s=at+72+80*i;name=d[s:s+16].split(b'\0')[0];address,length,offset=struct.unpack_from('<QQI',d,s+32);flags=struct.unpack_from('<I',d,s+64)[0]
    if flags&0x80000400:out[name.decode()]=dict(address=address,size=length,sha256=sha_bytes(d[offset:offset+length]))
  at+=size
 return out
sha_bytes=lambda b:hashlib.sha256(b).hexdigest();before=code_sections(original);after=code_sections(extra);assert before==after
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';src=r/'vendor/darling/src/external/IOKitUser/IOMainPort.c';constant=w/'constant.c';constant.write_text('#include <mach/mach.h>\nconst mach_port_t kIOMainPortDefault = MACH_PORT_NULL;\n');commands=[]
for n,s in [('main',src),('constant',constant)]:
 command=['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-Wno-deprecated-declarations','-c',str(s),'-o',str(w/(n+'.o'))];subprocess.run(command,check=True);commands.append(command)
framework=w/'frameworks/IOKit.framework';out=framework/'Versions/A/IOKit';out.parent.mkdir(parents=True);command=['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-install_name','/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit','-compatibility_version','1.0.0','-current_version','275.0.0','-reexport_library',str(legacy),'-reexport_library',str(extra),str(w/'main.o'),str(w/'constant.o'),'-o',str(out)];subprocess.run(command,check=True);commands.append(command)
(framework/'Versions/Current').symlink_to('A');(framework/'IOKit').symlink_to('Versions/Current/IOKit')
report=dict(verified_code_preservation=True,original_extra_export_code_sections=before,original=str(original.relative_to(r)),original_sha256=sha(original),legacy_client=str(legacy.relative_to(r)),legacy_client_sha256=sha(legacy),framework=str(out.relative_to(r)),framework_sha256=sha(out),extra_library=str(extra.relative_to(r)),extra_library_sha256=sha(extra),commands=commands,files={str(p.relative_to(r)):sha(p) for p in [Path(__file__),src,constant,stage,r/a.configuration,r/'scripts/macho-set-id.py']},source_registry_clients_reexported_first=True,original_private_exports_retained=True,modern_IOKit_kobject_send_compatibility_verified=False,runtime_execution_verified=False,full_goal_complete=False);dest=r/('artifacts/iokit-hybrid-client-'+a.tag+'-build.json');assert not dest.exists();dest.write_text(json.dumps(report,indent=2)+'\n');print(dest.relative_to(r))
