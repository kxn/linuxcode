#!/usr/bin/env python3
"""Add the exact original read-only NE agent UUID to an immutable libSystem stage."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,struct,subprocess,sys
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--configuration',required=True);parser.add_argument('--tag',required=True);args=parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder=root/('runtime/resource-ne-agent-'+args.tag);assert not folder.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=json.loads((root/args.configuration).read_text());parent=c['resource_system_build'];assert sha(root/parent)==c['resource_system_build_sha256']
base=json.loads((root/parent).read_text());assert base['full_initializer_and_queue_source_build'] and base['complete_source_files']==20 and base['original_source_instructions_preserved']
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in base['files'].items():resolve(name,digest)
for name,digest in base['link_inputs'].items():assert sha(root/name)==digest
original=root/base['output'];assert sha(original)==base['output_sha256']
contract_path=root/'artifacts/ne-privacy-dns-original-constant-contract-v1.json';contract=json.loads(contract_path.read_text());assert contract['verified'] and contract['bytes']==16
assert sha(root/('runtime/fullsystem-libraries'+contract['provider']))==contract['provider_sha256']
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=root/'vendor/darling/src/networkextension/ne_agent_constants.c';(folder/'libraries').mkdir(parents=True);inherited=[]
for old in original.parent.glob('*.dylib'):
    if old==original:continue
    new=folder/'libraries'/old.name;shutil.copy2(old,new);assert sha(new)==sha(old);inherited.append(new)
obj=folder/'uuid.o';name='libDarlingNEAgentConstants.dylib';helper=folder/'libraries'/name
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],
 ['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-no_fixup_chains','-no_adhoc_codesign',
  '-install_name','/usr/lib/'+name,'-exported_symbol',contract['symbol'],str(obj),'-o',str(helper)]]
for command in commands:subprocess.run(command,check=True)
symbols=[s.split() for s in subprocess.check_output(['llvm-nm-19','--defined-only','--extern-only',str(helper)],text=True).splitlines() if s.strip()]
assert len(symbols)==1 and symbols[0][-1]==contract['symbol'];address=int(symbols[0][0],16);assert address%16==0
b=helper.read_bytes();at=32;actual=None;code=0
for _ in range(struct.unpack_from('<I',b,16)[0]):
    kind,size=struct.unpack_from('<II',b,at)
    if kind==0x19:
        vm,length,off,filesz=struct.unpack_from('<QQQQ',b,at+24)
        if vm<=address and address+16<=vm+filesz:
            assert struct.unpack_from('<i',b,at+60)[0]&2==0
            actual=b[off+address-vm:off+address-vm+16]
        for i in range(struct.unpack_from('<I',b,at+64)[0]):
            s=at+72+80*i;count=struct.unpack_from('<Q',b,s+40)[0];flags=struct.unpack_from('<I',b,s+64)[0]
            if flags&0x80000400:code+=count
    at+=size
assert actual==bytes.fromhex(contract['original_bytes']) and code==0
payload,changes=runpy.run_path(str(root/'scripts/macho-named-reexport.py'))['add'](original.read_bytes(),'/usr/lib/'+name,[contract['symbol']])
assert changes['original_instructions_and_other_bytes_preserved'];library=folder/'libraries/libSystem.B.dylib';library.write_bytes(payload)
inputs=[Path(__file__),source,helper,library,*inherited,root/parent,root/args.configuration,contract_path,
 root/'scripts/macho-named-reexport.py',root/'vendor/darling/src/networkextension/CMakeLists.txt',sdk/'usr/include/uuid/uuid.h']
report={**base,'parent_source_build':parent,'parent_source_build_sha256':sha(root/parent),'parent_link_command':base['command'],
 'command':[sys.executable,*sys.argv],'output':str(library.relative_to(root)),'output_sha256':sha(library),
 'files':{**base['files'],**{str(p.relative_to(root)):sha(p) for p in inputs}},
 'link_inputs':{**base['link_inputs'],**{str(p.relative_to(root)):sha(p) for p in [helper,*inherited]}},
 'inherited_helper_bytes_preserved':{str(p.relative_to(root)):sha(p) for p in inherited},
 'NE_agent_helper':str(helper.relative_to(root)),'NE_agent_helper_sha256':sha(helper),'NE_agent_bytes':16,
 'NE_agent_original_bytes_equal':True,'NE_agent_readonly_segment':True,'NE_agent_helper_executable_bytes':code,
 'NE_agent_build_commands':commands,'added_NE_agent_reexport':changes,'runtime_execution_verified':False,'full_Unity_build_verified':False}
(folder/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('BUILD_REPORT',folder/'build.json')
