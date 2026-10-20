#!/usr/bin/env python3
"""Compose fresh resource stages from independently validated original images."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for n in ['batch-report','configuration','graphics-tag','overlay-tag','output-configuration','stem']:p.add_argument('--'+n,required=True)
a=p.parse_args();assert all(s and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in s) for s in [a.graphics_tag,a.overlay_tag,a.stem]);read=lambda n:json.loads((root/n).read_text());sha=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest();batch=read(a.batch_report);assert batch['verified'];config=read(a.configuration);output=root/a.output_configuration;assert not output.exists();rows=batch['reports'];assert rows and len({x['target'] for x in rows})==len(rows)
def run(args,tag):
 log=root/('logs/'+a.stem+'-'+tag+'.log');assert not log.exists()
 with log.open('w') as out:subprocess.run([sys.executable,*args],cwd=root,stdout=out,stderr=subprocess.STDOUT,check=True)
 print(tag,flush=True)
for row in rows:
 target=row['target'];run(['scripts/inspect-preserved-patch-got.py','--target',target,'--output','artifacts/'+target+'-independent-inspection.json','--original-validator-report',row['report']],target+'-inspection')
flags=[v for row in rows for v in ['--target',row['target']]]
pins=read('config/coregraphics-image-pins.json');framework_targets=[]
for row in rows:
 path=pins[row['target']]['path']
 if '.framework/' in path:framework_targets.append(row['target'])
 else:assert path.startswith('/usr/lib/') and path.endswith('.dylib'), path
assert framework_targets, 'Select at least one framework; standalone dylibs use the graphics library path'
framework_flags=[v for target in framework_targets for v in ['--target',target]]
run(['scripts/test-preserved-patch-got-binaries.py',*flags,'--output','artifacts/'+a.stem+'-real-binary-tests.json'],'binary-controls')
g='artifacts/coregraphics-native-'+a.graphics_tag+'-runtime-inputs-v1.json';o='artifacts/resource-framework-overlay-'+a.overlay_tag+'-runtime-inputs-v1.json'
run(['scripts/extend-coregraphics-stage.py','--parent',config['graphics_stage'],'--tag',a.graphics_tag,*flags],'graphics')
run(['scripts/compact-resource-stage-inputs.py','--stage','artifacts/coregraphics-native-'+a.graphics_tag+'-stage.json','--output',g],'graphics-inputs')
run(['scripts/extend-resource-framework-overlay.py','--parent',config['resource_overlay_stage'],'--graphics-stage',g,*framework_flags,'--tag',a.overlay_tag],'overlay')
run(['scripts/compact-resource-stage-inputs.py','--stage','artifacts/resource-framework-overlay-'+a.overlay_tag+'-stage.json','--output',o],'overlay-inputs')
for k,n in [('graphics_stage',g),('resource_overlay_stage',o)]:config[k]=n;config[k+'_sha256']=sha(n)
output.write_text(json.dumps(config,indent=2)+'\n');print(a.output_configuration)
