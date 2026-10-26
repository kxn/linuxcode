#!/usr/bin/env python3
"""Audit every selected Swift framework for omitted uniquely named witness loads."""
from pathlib import Path
import argparse,collections,hashlib,json,re,runpy,struct
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--output',required=True);p.add_argument('--contracts-directory',required=True);a=p.parse_args();output=r/a.output;folder=r/a.contracts_directory;assert not output.exists() and not folder.exists();folder.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();pins=json.loads((r/'config/coregraphics-image-pins.json').read_text());configuration=json.loads((r/a.configuration).read_text());overlay=json.loads((r/configuration['resource_overlay_stage']).read_text());frameworks=r/overlay['frameworks'];groups=collections.defaultdict(list)
for name,pin in pins.items():
 if pin.get('preserve_swift_code_with_patch_got') and '/usr/lib/swift/' not in pin['path']:groups[pin['path']].append(name)
ns=runpy.run_path(str(r/'scripts/dsc-image.py'),init_globals={'REFERENCE_CACHE_PATH':r/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h','REFERENCE_LIBRARY_ROOT':r/'runtime/fullsystem-libraries'});provider='/usr/lib/swift/libswiftCore.dylib';core=ns['image'](provider);exports=collections.defaultdict(list)
for name,value in core.exports.items():
 if value[0]=='address':exports[value[1]].append(name)
witnesses={address:names[0] for address,names in exports.items() if len(names)==1 and names[0].startswith('_$s') and names[0].endswith('WV')};slots={};results=[];skipped=[]
verify=runpy.run_path(str(r/'scripts/original-pooled-swift-witness.py'))['validate'];pattern=re.compile(rb'(?=([\x48\x4c]\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d][\s\S]{4}))')
for path,targets in groups.items():
 if '.framework/' not in path:continue
 outer,suffix=path.split('.framework/',1);candidate=frameworks/(Path(outer).name+'.framework')/suffix
 if not candidate.is_file():continue
 digest=sha(candidate);selected_target=None;report=None
 for target in reversed(targets):
  file=r/('runtime/rebuilt-'+target+'/reconstruction.json')
  if not file.exists():continue
  record=json.loads(file.read_text())
  if record['staged_image_sha256']==digest:selected_target=target;report=record;break
 if report is None:skipped.append(dict(image=path,reason='selected bytes have no matching reconstruction'));continue
 image=ns['image'](path)
 if provider not in image.dependencies:skipped.append(dict(image=path,reason='no direct SwiftCore dependency'));continue
 got=report['byte_preserving_patch_got'];known={int(row['slot'],16) for key in ['cells','original_local_stub_cells','original_pooled_swift_any','original_pooled_enum_indices','original_pooled_swift_witness'] for row in got.get(key,[])}
 start,end=[int(v,16) for v in got['original_vm_range']];assert 0<end-start<=128*1024*1024
 if (start,end) not in slots:
  table={}
  for at in range(start,end,8):
   target=ns['pointer'](at)
   if target in witnesses:table[at]=(witnesses[target],target)
  slots[(start,end)]=table
 wanted={at:dict(symbol=name,target=target,references=[]) for at,(name,target) in slots[(start,end)].items() if at not in known}
 for _,_,address,size,flags in image.sections:
  if not flags&0x80000400:continue
  data=ns['read'](address,size)
  for match in pattern.finditer(data):
   code=match.group(1);instruction=address+match.start();at=instruction+7+struct.unpack_from('<i',code,3)[0]
   if at in wanted:wanted[at]['references'].append(dict(offset=hex(instruction-image.base),bytes=code.hex()))
 contracts=[dict(symbol=row['symbol'],provider=provider,slot_offset=hex(at-image.base),references=row['references'],type_layout_bytes=ns['read'](row['target']+64,24).hex()) for at,row in wanted.items() if row['references']]
 proof=verify(ns,path,contracts)
 row=dict(target=selected_target,image=path,candidate=str(candidate.relative_to(r)),candidate_sha256=digest,missing_tables=len(proof),references=sum(len(v['references']) for v in proof))
 if contracts:
  file=folder/(selected_target+'.json');file.write_text(json.dumps(contracts,indent=2)+'\n');row.update(contracts=str(file.relative_to(r)),contracts_sha256=sha(file),symbols=[x['symbol'] for x in contracts])
 results.append(row);print(selected_target,row['missing_tables'],row['references'],flush=True)
output.write_text(json.dumps(dict(diagnostic_only=True,configuration=a.configuration,configuration_sha256=sha(r/a.configuration),results=results,skipped=skipped,images_checked=len(results),omitted_witness_cells=sum(v['missing_tables'] for v in results),original_load_references=sum(v['references'] for v in results),source_sha256=sha(Path(__file__)),validator_sha256=sha(r/'scripts/original-pooled-swift-witness.py'),full_goal_complete=False),indent=2)+'\n')
