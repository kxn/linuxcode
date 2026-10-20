#!/usr/bin/env python3
"""Replace one verified image in fresh graphics and resource-overlay copies."""
from pathlib import Path
import argparse,copy,hashlib,json,os,runpy,shutil
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for name in ['graphics-parent','overlay-parent','parent-target','target','inspection','graphics-tag','overlay-tag']:p.add_argument('--'+name,required=True)
a=p.parse_args();assert all(v and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in v) for v in [a.graphics_tag,a.overlay_tag]);read=lambda n:json.loads((root/n).read_text());sha=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest();resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve'];g,o=read(a.graphics_parent),read(a.overlay_parent);pins=read('config/coregraphics-image-pins.json');old,new=pins[a.parent_target],pins[a.target];assert old['path']==new['path'] and old['sha256']==new['sha256'] and old['path'].count('.framework/')==1
for record in [g,o]:
 for name,digest in record['files'].items():resolve(name,digest)
 for name,target in record.get('links',{}).items():assert os.readlink(root/name)==target
source='runtime/rebuilt-'+a.target+'/'+Path(new['path']).name;reconstruction=str(Path(source).parent/'reconstruction.json');report=read(reconstruction);inspection=read(a.inspection);assert inspection['verified'] and inspection['original_code_bytes_equal'] and inspection['files'][source]==sha(source)==report['staged_image_sha256'];assert not report['rip_instructions_patched'] and not report['backend_call_overrides']
old_source='runtime/rebuilt-'+a.parent_target+'/'+Path(old['path']).name;old_hash=sha(old_source)
outer,suffix=new['path'].split('.framework/',1);rel=Path('frameworks')/(Path(outer).name+'.framework')/suffix
old_graph=Path(g['library']).parents[4];old_overlay=Path(o['frameworks']).parent
for base in [old_graph,old_overlay]:assert sha(str(base/rel))==old_hash
new_graph=Path('runtime/coregraphics-native-'+a.graphics_tag);new_overlay=Path('runtime/resource-framework-overlay-'+a.overlay_tag)
outputs=[Path('artifacts/coregraphics-native-'+a.graphics_tag+'-stage.json'),Path('artifacts/resource-framework-overlay-'+a.overlay_tag+'-stage.json')]
assert all(not (root/n).exists() for n in [new_graph,new_overlay,*outputs]);shutil.copytree(root/old_graph,root/new_graph,symlinks=True);shutil.copytree(root/old_overlay,root/new_overlay,symlinks=True)
for base in [new_graph,new_overlay]:shutil.copyfile(root/source,root/base/rel);assert sha(str(base/rel))==report['staged_image_sha256']
def rebase(n,oldroot,newroot):return str(newroot/Path(n).relative_to(oldroot))
g=copy.deepcopy(g);g['library']=rebase(g['library'],old_graph,new_graph);found=0
for row in g['dependencies']:
 if row['target']==a.parent_target:row.update(target=a.target,source=source,reconstruction=reconstruction);found+=1
assert found==1;g.update(parent_stage=a.graphics_parent,parent_stage_sha256=sha(a.graphics_parent),runtime_execution_verified=False,resource_compilation_verified=False,installed=False)
o=copy.deepcopy(o);o.update(frameworks=str(new_overlay/'frameworks'),libraries=str(new_overlay/'libraries'),parent_overlay=a.overlay_parent,parent_overlay_sha256=sha(a.overlay_parent),graphics_stage=str(outputs[0]),runtime_execution_verified=False,installed=False)
for key in ['extra_framework_paths','extra_library_paths']:o[key]=[rebase(n,old_overlay,new_overlay) for n in o.get(key,[])]
for record,base in [(g,new_graph),(o,new_overlay)]:
 record['files']=dict(record['files']);record['links']=dict(record.get('links',{}))
 for n in [a.graphics_parent,a.overlay_parent,a.inspection,source,reconstruction,'scripts/replace-original-framework-stage.py','config/coregraphics-image-pins.json']:record['files'][n]=sha(n)
 for q in (root/base).rglob('*'):
  n=str(q.relative_to(root))
  if q.is_symlink():record['links'][n]=os.readlink(q)
  elif q.is_file():record['files'][n]=sha(n)
 record['replaced_original_framework']=dict(parent_target=a.parent_target,target=a.target,old_sha256=old_hash,new_sha256=report['staged_image_sha256'],inspection=a.inspection,relative_path=str(rel))
(root/outputs[0]).write_text(json.dumps(g,indent=2)+'\n');o['graphics_stage_sha256']=sha(str(outputs[0]));(root/outputs[1]).write_text(json.dumps(o,indent=2)+'\n');print(*(str(n) for n in outputs),sep='\n')
