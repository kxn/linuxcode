#!/usr/bin/env python3
"""Select a pinned bootstrap fcntl component by a private namespace mount."""
from pathlib import Path
import argparse,hashlib,json,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for n in ['build','configuration','tag','output-configuration']:p.add_argument('--'+n,required=True)
p.add_argument('--compat-signature',action='append',default=[])
a=p.parse_args();assert a.tag.isalnum()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda n:json.loads((root/n).read_text())
build=read(a.build);assert sha(root/build['source'])==build['source_sha256'] and sha(root/build['loader'])==build['loader_sha256'];assert build['old_ImageLoader_ABI_preserved']
config=read(a.configuration);parent=read(config['resource_launcher_stage']);assert sha(root/config['resource_launcher_stage'])==config['resource_launcher_stage_sha256']
folder=root/('runtime/dyld-bootstrap-fcntl-launcher-'+a.tag);report=root/('artifacts/dyld-bootstrap-fcntl-launcher-'+a.tag+'-stage.json');output=root/a.output_configuration
assert not any(p.exists() for p in [folder,report,output]);folder.mkdir()
launcher=folder/'darling';namespace=folder/'runtime-ns.sh'
s=(root/parent['launcher']).read_text();assert s.count(parent['namespace'])==1;launcher.write_text(s.replace(parent['namespace'],str(namespace.relative_to(root))));launcher.chmod(0o755)
s=(root/parent['namespace']).read_text();needle='mount -t proc proc "$rootfs/proc"';assert s.count(needle)==1
block='''# The loader's C++ objects and addresses remain at the pinned ABI. Only its
# statically linked fcntl entry uses the source-built descriptor RPC component.
python3 - "$project" <<'PYBOOT'
from pathlib import Path
import hashlib,json,sys
r=Path(sys.argv[1]);b=json.loads((r/BUILD_REPORT).read_text())
for key in ['source','loader']:
    assert hashlib.sha256((r/b[key]).read_bytes()).hexdigest()==b[key+'_sha256']
assert b['old_ImageLoader_ABI_preserved'] and not b['component_rebases'] and not b['component_dynamic_imports']
PYBOOT
'''.replace('BUILD_REPORT',repr(a.build))
s=s.replace(needle,block+'\n'+needle)
# Overlayfs ignores bind mounts applied to backing lower-directory files.
# Bind onto the live merged root in darlingserver's own mount namespace.
needle='if [[ -n $system_version_relative ]]; then';assert s.count(needle)==1
block='''bootstrap_server_pid=$(cat /state/prefix/.init.pid)
[[ $bootstrap_server_pid =~ ^[0-9]+$ && $(cat "/proc/$bootstrap_server_pid/comm") == darlingserver ]] || exit 2
/usr/bin/nsenter --target "$bootstrap_server_pid" --mount \\
    /usr/bin/mount --bind "/workspace/LOADER_FILE" /state/prefix/usr/lib/dyld
/usr/bin/nsenter --target "$bootstrap_server_pid" --mount \\
    /usr/bin/mount -o remount,bind,ro /state/prefix/usr/lib/dyld
'''.replace('LOADER_FILE',build['loader'])
compat=[]
for name in a.compat_signature:
    record=read(name);assert record['verified'] and record['ad_hoc_only'] and record['all_MachO_section_bytes_preserved'] and not record['original_input_modified']
    assert sha(root/record['output'])==record['output_sha256']
    prefix='runtime/state/prefix/';assert record['source'].startswith(prefix)
    relative=record['source'][len(prefix):];assert relative.startswith('usr/lib/swift/') and '..' not in Path(relative).parts
    # A read-only bind affects the live private merged view, never its backing
    # prefix input. File names are constrained to this known library directory.
    assert all(c.isalnum() or c in '/._-' for c in record['output']+relative)
    block+='\n/usr/bin/nsenter --target "$bootstrap_server_pid" --mount \\\n    /usr/bin/mount --bind "/workspace/'+record['output']+'" /state/prefix/'+relative+'\n'
    block+='/usr/bin/nsenter --target "$bootstrap_server_pid" --mount \\\n    /usr/bin/mount -o remount,bind,ro /state/prefix/'+relative+'\n'
    compat.append(dict(report=name,path=relative,output=record['output'],sha256=record['output_sha256']))
namespace.write_text(s.replace(needle,block+'\n'+needle));namespace.chmod(0o755);subprocess.run(['bash','-n',str(launcher),str(namespace)],check=True)
files=dict(parent['files'])
for path in [Path(__file__),root/a.build,root/build['loader'],launcher,namespace]:files[str(path.relative_to(root))]=sha(path)
for item in compat:
    for path in [root/item['report'],root/item['output']]:files[str(path.relative_to(root))]=sha(path)
record={**parent,'launcher':str(launcher.relative_to(root)),'namespace':str(namespace.relative_to(root)),'files':files,'bootstrap_component_build':a.build,'private_bootstrap_component_mount':True,'runtime_execution_verified':False}
record['private_ad_hoc_compat_library_mounts']=compat
report.write_text(json.dumps(record,indent=2)+'\n');config['resource_launcher_stage']=str(report.relative_to(root));config['resource_launcher_stage_sha256']=sha(report);output.write_text(json.dumps(config,indent=2)+'\n');print(report.relative_to(root));print(output.relative_to(root))
