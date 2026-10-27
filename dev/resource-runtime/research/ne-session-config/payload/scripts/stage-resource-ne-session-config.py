#!/usr/bin/env python3
"""Stage source NE notification-state queries without replacing old runtime files."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.replace('-','').isalnum()
c=json.loads((r/a.configuration).read_text());parent=r/c['resource_system_build'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert sha(parent)==c['resource_system_build_sha256']
base=json.loads(parent.read_text());old=r/base['output'];assert sha(old)==base['output_sha256']
resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in base['files'].items():resolve(name,digest)
folder=r/('runtime/resource-ne-session-config-'+a.tag);folder.mkdir();libraries=folder/'libraries';libraries.mkdir();inherited=[]
for source in old.parent.glob('*.dylib'):
    if source==old:continue
    target=libraries/source.name;shutil.copy2(source,target);inherited.append(target)
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=r/'vendor/darling/src/networkextension/ne_session_config.c';header=r/'vendor/darling/src/networkextension/include/ne_session.h';obj=folder/'config.o';helper=libraries/'libDarlingNESessionConfig.dylib'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-I',str(header.parent),'-O2','-c',str(source),'-o',str(obj)],['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-no_fixup_chains','-no_adhoc_codesign','-syslibroot',str(sdk),'-install_name','/usr/lib/'+helper.name,str(obj),'-lSystem','-o',str(helper)]]
for command in commands:subprocess.run(command,check=True)
symbols=['_ne_session_app_vpn_configs_present','_ne_session_always_on_vpn_configs_present','_ne_session_on_demand_configs_present'];exports=subprocess.check_output(['llvm-nm-19','--defined-only','--extern-only',str(helper)],text=True);assert sorted(s.split()[-1] for s in exports.splitlines() if s.strip())==sorted(symbols)
payload,changes=runpy.run_path(str(r/'scripts/macho-named-reexport.py'))['add'](old.read_bytes(),'/usr/lib/'+helper.name,symbols);assert changes['original_instructions_and_other_bytes_preserved']
library=libraries/'libSystem.B.dylib';library.write_bytes(payload)
inputs=[source,header,Path(__file__),r/'vendor/darling/src/networkextension/CMakeLists.txt',helper,library,*inherited,parent,r/a.configuration]
record={**base,'parent_source_build':str(parent.relative_to(r)),'parent_source_build_sha256':sha(parent),'parent_link_command':base['command'],'command':commands,'output':str(library.relative_to(r)),'output_sha256':sha(library),'files':{**base['files'],**{str(p.relative_to(r)):sha(p) for p in inputs}},'link_inputs':{**base['link_inputs'],**{str(p.relative_to(r)):sha(p) for p in [helper,*inherited]}},'NE_session_helper':str(helper.relative_to(r)),'NE_session_helper_sha256':sha(helper),'NE_config_notification':'com.apple.neconfigurationchanged','NE_app_VPN_state_bit':62,'added_NE_session_reexport':changes,'runtime_execution_verified':False,'full_UE_build_verified':False}
(folder/'build.json').write_text(json.dumps(record,indent=2)+'\n');print('BUILD_REPORT',folder/'build.json')
