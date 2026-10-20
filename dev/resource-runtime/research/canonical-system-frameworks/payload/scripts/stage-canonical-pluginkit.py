#!/usr/bin/env python3
"""Keep original PlugInKit at its system path outside DVT's override scan."""
from pathlib import Path
import argparse,hashlib,json,os,runpy,shutil,subprocess
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for key in ['configuration','graphics-tag','tag','output-configuration']:p.add_argument('--'+key,required=True)
a=p.parse_args();assert all(v and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in v) for v in [a.graphics_tag,a.tag])
read=lambda n:json.loads((root/n).read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();config=read(a.configuration);parent_name=config['graphics_stage'];parent=read(parent_name)
assert sha(root/parent_name)==config['graphics_stage_sha256']
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in parent['files'].items():resolve(name,digest)
for name,target in parent.get('links',{}).items():assert os.readlink(root/name)==target
old=Path(parent['library']).parents[4];graphics=root/('runtime/coregraphics-native-'+a.graphics_tag);folder=root/('runtime/canonical-pluginkit-'+a.tag);report=root/('artifacts/canonical-pluginkit-'+a.tag+'-stage.json');g_report=root/('artifacts/coregraphics-native-'+a.graphics_tag+'-stage.json');output=root/a.output_configuration
assert not any(q.exists() for q in [graphics,folder,report,g_report,output])
original=root/old/'frameworks/PlugInKit.framework';assert original.is_dir()
overlay=read(config['resource_overlay_stage']);assert not (root/overlay['frameworks']/'PlugInKit.framework').exists()
expected=read('artifacts/fullsystem-pluginkit-resources-v1.json');assert expected['complete'] and expected['source_asset_sha256_verified']
assert sha(original/'Versions/A/Resources/Info.plist')==expected['original_info_sha256']
folder.mkdir();shutil.copytree(root/old,graphics,symlinks=True)
canonical='darling-root/System/Library/PrivateFrameworks/PlugInKit.framework';destination=folder/canonical;destination.parent.mkdir(parents=True);os.rename(graphics/'frameworks/PlugInKit.framework',destination)
files={}
for q in original.rglob('*'):
 rel=q.relative_to(original);candidate=destination/rel
 if q.is_symlink():assert os.readlink(q)==os.readlink(candidate)
 elif q.is_file():assert sha(q)==sha(candidate);files[str(candidate.relative_to(root))]=sha(candidate)
parent_launcher='runtime/native-codesign-ci-v3/darling';parent_namespace='runtime/native-codesign-ci-v3/runtime-ns.sh';launcher=folder/'darling';namespace=folder/'runtime-ns.sh'
s=(root/parent_launcher).read_text();needle='runtime/native-codesign-ci-v3/runtime-ns.sh';assert s.count(needle)==1;launcher.write_text(s.replace(needle,str(namespace.relative_to(root))));launcher.chmod(0o755)
s=(root/parent_namespace).read_text();needle='if [[ -n $system_version_relative ]]; then';assert s.count(needle)==1
relative=str(destination.relative_to(root));assert not (root/'runtime/state/prefix/System/Library/PrivateFrameworks/PlugInKit.framework').is_symlink()
block='''# Preserve the system location; DVT scans DYLD_FRAMEWORK_PATH for plugins.
/usr/bin/env -i HOME=/root USER=root LOGNAME=root \\
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \\
    LANG=en_US.UTF-8 DPREFIX="$DPREFIX" /usr/bin/darling shell /usr/bin/true
canonical_server_pid=$(cat /state/prefix/.init.pid)
[[ $canonical_server_pid =~ ^[0-9]+$ && $(cat "/proc/$canonical_server_pid/comm") == darlingserver ]] || exit 2
/usr/bin/nsenter --target "$canonical_server_pid" --mount \\
    /usr/bin/mkdir -p /state/prefix/System/Library/PrivateFrameworks/PlugInKit.framework
/usr/bin/nsenter --target "$canonical_server_pid" --mount \\
    /usr/bin/mount --bind "/workspace/CANONICAL_PROVIDER" /state/prefix/System/Library/PrivateFrameworks/PlugInKit.framework
/usr/bin/nsenter --target "$canonical_server_pid" --mount \\
    /usr/bin/mount -o remount,bind,ro /state/prefix/System/Library/PrivateFrameworks/PlugInKit.framework
'''.replace('CANONICAL_PROVIDER',relative)
namespace.write_text(s.replace(needle,block+'\n'+needle));namespace.chmod(0o755)
subprocess.run(['bash','-n',str(launcher),str(namespace)],cwd=root,check=True)
g={**parent,'library':str((graphics/Path(parent['library']).relative_to(old)).relative_to(root)),'parent_stage':parent_name,'parent_stage_sha256':sha(root/parent_name),'files':dict(parent['files']),'links':dict(parent.get('links',{})),'canonical_system_framework_stage':str(report.relative_to(root)),'PlugInKit_removed_from_plugin_search_directory':True}
for q in graphics.rglob('*'):
 name=str(q.relative_to(root))
 if q.is_symlink():g['links'][name]=os.readlink(q)
 elif q.is_file():g['files'][name]=sha(q)
for name in [parent_name,str(Path(__file__).relative_to(root))]:g['files'][name]=sha(root/name)
g_report.write_text(json.dumps(g,indent=2)+'\n')
for q in [launcher,namespace,root/parent_launcher,root/parent_namespace,Path(__file__),root/a.configuration,root/'artifacts/fullsystem-pluginkit-resources-v1.json']:files[str(q.relative_to(root))]=sha(q)
record=dict(private_canonical_PlugInKit_mount=True,original_provider_bytes_preserved=True,original_metadata_changed=False,parent_launcher=parent_launcher,launcher=str(launcher.relative_to(root)),namespace=str(namespace.relative_to(root)),canonical_provider=str(destination.relative_to(root)),guest_path='/System/Library/PrivateFrameworks/PlugInKit.framework',source_framework=str(original.relative_to(root)),files=files,runtime_execution_verified=False,full_goal_complete=False)
report.write_text(json.dumps(record,indent=2)+'\n');config.update(graphics_stage=str(g_report.relative_to(root)),graphics_stage_sha256=sha(g_report),resource_launcher_stage=str(report.relative_to(root)),resource_launcher_stage_sha256=sha(report));output.write_text(json.dumps(config,indent=2)+'\n');print(report.relative_to(root));print(g_report.relative_to(root));print(output.relative_to(root))
