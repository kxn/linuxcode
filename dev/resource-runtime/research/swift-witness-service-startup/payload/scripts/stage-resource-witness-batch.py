#!/usr/bin/env python3
"""Publish inspected original replacements into one fresh framework overlay."""
from pathlib import Path
import argparse,hashlib,json,os,runpy,shutil,subprocess
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for k in ['configuration','audit','build','inspections','tag','output-configuration']:p.add_argument('--'+k,required=True)
a=p.parse_args();assert a.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.tag);read=lambda n:json.loads((r/n).read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();config=read(a.configuration);parent_name=config['resource_overlay_stage'];parent=read(parent_name);assert sha(r/parent_name)==config['resource_overlay_stage_sha256'];resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
for n,h in parent['files'].items():resolve(n,h)
for n,target in parent.get('links',{}).items():assert os.readlink(r/n)==target
audit=read(a.audit);build=read(a.build);inspections=read(a.inspections);assert build['prepared_all'] and inspections['verified'];old=r/Path(parent['frameworks']).parent;folder=r/('runtime/resource-framework-overlay-'+a.tag);out=r/('artifacts/resource-framework-overlay-'+a.tag+'-stage.json');configuration=r/a.output_configuration;assert not any(q.exists() for q in [folder,out,configuration]);inspected={v['target']:v for v in inspections['images']};audited={v['target']:v for v in audit['results']};pins=read('config/coregraphics-image-pins.json');replacements=[]
for item in build['images']:
 target=item['target'];base=item['parent_target'];inspection=read(inspected[target]['inspection']);assert inspection['verified'] and inspection['original_code_bytes_equal'];pin=pins[target];assert pin['path']==pins[base]['path'] and pin['sha256']==pins[base]['sha256'];source=r/('runtime/rebuilt-'+target)/Path(pin['path']).name;assert inspection['files'][str(source.relative_to(r))]==sha(source);previous=r/audited[base]['candidate'];assert sha(previous)==audited[base]['candidate_sha256'];relative=previous.relative_to(old);replacements.append(dict(parent_target=base,target=target,relative=str(relative),source=str(source.relative_to(r)),original_sha256=sha(previous),replacement_sha256=sha(source),inspection=inspected[target]['inspection']))
subprocess.run(['cp','-a','--reflink=auto',str(old),str(folder)],check=True)
for item in replacements:
 destination=folder/item['relative'];assert sha(destination)==item['original_sha256'];shutil.copyfile(r/item['source'],destination);assert sha(destination)==item['replacement_sha256']
record={**parent,'frameworks':str((folder/'frameworks').relative_to(r)),'libraries':str((folder/'libraries').relative_to(r)),'parent_overlay':parent_name,'parent_overlay_sha256':sha(r/parent_name),'files':dict(parent['files']),'links':dict(parent.get('links',{})),'runtime_execution_verified':False,'installed':False,'original_witness_replacement_batch':replacements}
for key in ['extra_framework_paths','extra_library_paths']:record[key]=[str((folder/(r/n).relative_to(old)).relative_to(r)) for n in parent.get(key,[])]
for q in folder.rglob('*'):
 n=str(q.relative_to(r))
 if q.is_symlink():record['links'][n]=os.readlink(q)
 elif q.is_file():record['files'][n]=sha(q)
for n in [a.configuration,a.audit,a.build,a.inspections,'config/coregraphics-image-pins.json',str(Path(__file__).relative_to(r)),*[v['source'] for v in replacements],*[v['inspection'] for v in replacements]]:record['files'][n]=sha(r/n)
out.write_text(json.dumps(record,indent=2)+'\n');config['resource_overlay_stage']=str(out.relative_to(r));config['resource_overlay_stage_sha256']=sha(out);configuration.write_text(json.dumps(config,indent=2)+'\n');print(out.relative_to(r));print(configuration.relative_to(r));print('REPLACEMENTS',len(replacements))
