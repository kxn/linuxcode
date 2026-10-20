#!/usr/bin/env python3
"""Add matched original AppKit bundle metadata and layout rules to a fresh overlay."""
from pathlib import Path
import argparse,hashlib,json,os,plistlib,runpy,shutil
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for key in ['configuration','tag','output-configuration']:p.add_argument('--'+key,required=True)
a=p.parse_args();assert a.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.tag)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
config=json.loads((root/a.configuration).read_text());parent_name=config['resource_overlay_stage'];parent=json.loads((root/parent_name).read_text())
assert sha(root/parent_name)==config['resource_overlay_stage_sha256']
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in parent['files'].items():resolve(name,digest)
for name,target in parent.get('links',{}).items():assert os.readlink(root/name)==target
base=root/'runtime/recovery/macOS Base System'
version=plistlib.loads((base/'System/Library/CoreServices/SystemVersion.plist').read_bytes());assert version['ProductBuildVersion']=='25G83'
source=base/'System/Library/Frameworks/AppKit.framework/Versions/C/Resources'
info=plistlib.loads((source/'Info.plist').read_bytes());assert info['CFBundleIdentifier']=='com.apple.AppKit' and info['CFBundleExecutable']=='AppKit'
assert plistlib.loads((source/'AquaGuideRules.plist').read_bytes())
old=Path(parent['frameworks']).parent;folder=root/('runtime/resource-framework-overlay-'+a.tag)
report=root/('artifacts/resource-framework-overlay-'+a.tag+'-stage.json');output=root/a.output_configuration
assert not any(q.exists() for q in [folder,report,output])
shutil.copytree(root/old,folder,symlinks=True)
framework=folder/'frameworks/AppKit.framework';destination=framework/'Versions/C/Resources';assert not destination.exists();destination.mkdir()
files={}
for name in ['Info.plist','AquaGuideRules.plist']:
 src=source/name;dst=destination/name;assert src.is_file() and not src.is_symlink();shutil.copyfile(src,dst);assert sha(src)==sha(dst);files[str(src.relative_to(root))]=sha(src)
assert not (framework/'Resources').exists();(framework/'Resources').symlink_to('Versions/Current/Resources')
record={**parent,'frameworks':str((folder/'frameworks').relative_to(root)),'libraries':str((folder/'libraries').relative_to(root)),
 'parent_overlay':parent_name,'parent_overlay_sha256':sha(root/parent_name),'files':dict(parent['files']),'links':dict(parent.get('links',{})),
 'extra_framework_paths':[str(folder/Path(n).relative_to(old)) for n in parent.get('extra_framework_paths',[])],
 'extra_library_paths':[str(folder/Path(n).relative_to(old)) for n in parent.get('extra_library_paths',[])],
 'original_appkit_layout_resources':dict(source_OS_build=version['ProductBuildVersion'],bundle_identifier=info['CFBundleIdentifier'],files=files,original_binary_changed=False,runtime_execution_verified=False)}
# Extra search paths are workspace relative, just like the inherited overlay.
for key in ['extra_framework_paths','extra_library_paths']:record[key]=[str(Path(n).relative_to(root)) for n in record[key]]
for q in folder.rglob('*'):
 name=str(q.relative_to(root))
 if q.is_symlink():record['links'][name]=os.readlink(q)
 elif q.is_file():record['files'][name]=sha(q)
record['files'].update(files)
for name in [parent_name,a.configuration,str(Path(__file__).relative_to(root))]:record['files'][name]=sha(root/name)
report.write_text(json.dumps(record,indent=2)+'\n')
config['resource_overlay_stage']=str(report.relative_to(root));config['resource_overlay_stage_sha256']=sha(report)
output.write_text(json.dumps(config,indent=2)+'\n');print(report.relative_to(root));print(output.relative_to(root))
