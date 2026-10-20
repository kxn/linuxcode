#!/usr/bin/env python3
"""Apply libc++'s original export policies with the unmodified Apple linker."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True)
parser.add_argument('--tag', required=True)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
sha = lambda p: hashlib.sha256((root/p).read_bytes()).hexdigest()
build = json.loads((root/args.build).read_text())
assert build['linked'] and build['standard']=='c++20' and not build['previous_backend_missing_exports']
for name,digest in build['sources'].items():
    assert sha(name)==digest,name
for item in build['compilation']:
    assert item['returncode']==0 and sha(item['object'])==item['object_sha256']
folder = root/('runtime/libcxx-char8-backend-'+args.tag)
report = root/('artifacts/libcxx-char8-backend-'+args.tag+'-build.json')
assert not folder.exists() and not report.exists()
folder.mkdir()
(folder/'libraries').mkdir()
tool = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld-classic'
installed='runtime/state/prefix'+tool
extracted='runtime/xcode-extract/Xcode.app/Contents/Developer'+tool.split('/Contents/Developer',1)[1]
assert sha(installed)==sha(extracted)
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path)
original_root='vendor/darling/src/external/libcxx'
policies={key:original_root+'/lib/'+name for key,name in [
    ('-unexported_symbols_list','libc++unexp.exp'),('-force_symbols_not_weak_list','notweak.exp'),
    ('-force_symbols_weak_list','weak.exp')]}
raw=str((folder/'unprocessed-libc++0.dylib').relative_to(root))
command=[tool,'-dylib','-arch','x86_64','-platform_version','macos','11.0','11.0',
    '-install_name','/usr/lib/libc++0.dylib','-compatibility_version','1.0.0',
    '-current_version','1.0.0','-no_adhoc_codesign',
    '-syslibroot',guest('runtime/rootfs/usr/libexec/darling'),
    '-L'+guest('runtime/rootfs/usr/libexec/darling/usr/lib'),'-lSystem',
    '-reexport_library',guest(build['ABI_library'])]
for flag,path in policies.items():
    command += [flag,guest(path)]
command += [guest(c['object']) for c in build['compilation']]+['-o',guest(raw)]
script=folder/'link.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(command)+
    '\nstatus=$?\nprintf "CHAR8_LINK_STATUS %s\\n" "$status"\nexit "$status"\n')
module=runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
p=module['profile'](stage=args.stage)
invoke=p['command'][:-2]+['/bin/bash',guest(script.relative_to(root))]
invoke[3]='120'
env=module['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:
    env.pop(name,None)
log=folder/'link.log'
with log.open('w') as out:
    result=subprocess.run(invoke,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text()
statuses=re.findall(r'^CHAR8_LINK_STATUS (\d+)$',text,re.M)
record={**build,'linked':False,'parent_build':args.build,'parent_build_sha256':sha(args.build),
    'original_link_tool':tool,'original_link_tool_sha256':sha(installed),
    'original_link_tool_bytes_equal_extracted':True,'original_link_command':command,
    'link_command':invoke,'link_outer_status':result.returncode,'link_native_status':statuses,
    'link_log':str(log.relative_to(root)),'link_log_sha256':sha(log.relative_to(root)),
    'Apple_force_weak_and_notweak_policies_applied':result.returncode==0 and statuses==['0'],
    'export_policies':{path:sha(path) for path in policies.values()},
    'relinker':str(Path(__file__).relative_to(root)),
    'relinker_sha256':sha(Path(__file__).relative_to(root))}
if result.returncode!=0 or statuses!=['0']:
    report.write_text(json.dumps(record,indent=2)+'\n')
    print(text[-3500:])
    raise SystemExit(1)
normalize=runpy.run_path(str(root/'scripts/normalize-macho-weak-bind.py'))['normalize']
data,normalization=normalize((root/raw).read_bytes())
library=folder/'libraries/libc++0.dylib'
library.write_bytes(data)


def exports(path):
    text=subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(root/path)],text=True)
    return {symbol:flags.strip() for symbol,flags in re.findall(r'^0x[0-9A-Fa-f]+\s+(\S+)(.*)$',text,re.M)}


old,new=exports(build['old_backend']),exports(library.relative_to(root))
missing=sorted(old.keys()-new.keys())
flags=[dict(symbol=n,old=old[n],new=new[n]) for n in sorted(old.keys()&new.keys()) if old[n]!=new[n]]
record.update(linked=True,library=str(library.relative_to(root)),library_sha256=sha(library.relative_to(root)),
    previous_backend_missing_exports=missing,direct_exports=len(new),added_exports=sorted(new.keys()-old.keys()),
    existing_export_flags_changed=flags,existing_export_flags_preserved=not flags,
    weak_bind_normalization=normalization,installed=False,runtime_execution_verified=False)
report.write_text(json.dumps(record,indent=2)+'\n')
print(text[-1800:])
print('BUILD_REPORT',report.relative_to(root),'missing',len(missing),'flag differences',len(flags))
raise SystemExit(0 if not missing and not flags else 1)
