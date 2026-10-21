#!/usr/bin/env python3
"""Expose an inspected resource framework at its original guest bundle path."""
from pathlib import Path
import argparse,hashlib,json,plistlib,runpy,shutil,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-stage',required=True);p.add_argument('--framework',required=True)
p.add_argument('--canonical',required=True);p.add_argument('--inspection',required=True)
p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.isalnum()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
parent=root/a.parent_stage;data=json.loads(parent.read_text())
for n,d in data['files'].items():resolve(n,d)
source=root/a.framework;assert source.is_dir() and source.resolve().is_relative_to(root/'runtime') and source.suffix=='.framework'
canonical=Path(a.canonical);assert canonical.is_absolute() and '..' not in canonical.parts and canonical.parent==Path('/System/Library/PrivateFrameworks') and canonical.name==source.name
inspection=root/a.inspection;proof=json.loads(inspection.read_text());assert proof['verified'] and proof['original_code_bytes_equal']
info=plistlib.loads((source/'Resources/Info.plist').read_bytes());executable=info['CFBundleExecutable'];assert '/' not in executable and executable==source.stem
image=source/executable;image_digest=sha(image)
assert any(v==image_digest for v in proof['files'].values()),'Inspection must pin selected image bytes'
inputs={};links={}
for q in source.rglob('*'):
 if q.is_symlink():
  target=q.readlink();assert not target.is_absolute() and q.resolve().is_relative_to(source.resolve());links[str(q.relative_to(source))]=str(target)
 elif q.is_file():inputs[str(q.relative_to(root))]=sha(q)
folder=root/('runtime/audit-session-runtime-'+a.tag);report=root/('artifacts/private-procfs-auditsession'+a.tag+'-stage.json');assert not folder.exists() and not report.exists();folder.mkdir()
base=(root/data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent/'darling-root';assert base.is_dir()
subprocess.run(['cp','-a','--reflink=auto',str(base),str(folder/'darling-root')],check=True)
destination=folder/'darling-root'/str(canonical).lstrip('/');assert not destination.exists() and not destination.is_symlink();destination.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,destination,symlinks=True)
selected={}
for key,row in data['source_runtime'].items():
 assert sha(root/row['path'])==row['sha256'];target=folder/Path(row['path']).name;shutil.copy2(root/row['path'],target);n=str(target.relative_to(root));selected[key]=dict(path=n,sha256=sha(target));data['files'][n]=sha(target)
for n,d in inputs.items():
 q=destination/(root/n).relative_to(source);assert sha(q)==d;data['files'][n]=d;data['files'][str(q.relative_to(root))]=d
for n,t in links.items():assert (destination/n).readlink()==Path(t)
for q in [Path(__file__),parent,inspection]:data['files'][str(q.relative_to(root))]=sha(q)
data['source_runtime']=selected;data['system_version_binding']=str((folder/'darling-root/System/Library/CoreServices/SystemVersion.plist').relative_to(root));data['files'][data['system_version_binding']]=sha(root/data['system_version_binding']);data['mtab']=str((folder/'darling-root/private/etc/mtab').relative_to(root));assert (root/data['mtab']).readlink()==Path(data['mtab_target'])
data['runtime_execution_verified']=False;data['full_goal_complete']=False
data['canonical_resource_framework']=dict(source=a.framework,canonical=a.canonical,inspection=a.inspection,executable_sha256=image_digest,bundle_identifier=info['CFBundleIdentifier'],files=inputs,symlinks=links,compiled_code_modified=False)
report.write_text(json.dumps(data,indent=2)+'\n');print(report.relative_to(root))
