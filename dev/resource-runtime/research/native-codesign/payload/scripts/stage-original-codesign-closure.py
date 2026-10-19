#!/usr/bin/env python3
"""Freeze selected reconstructed original codesign dependencies, never install them."""
from pathlib import Path
import argparse,hashlib,json,re,shutil
r=Path(__file__).resolve().parent.parent
a=argparse.ArgumentParser();a.add_argument('--tag',required=True);a.add_argument('--target',action='append',required=True);a.add_argument('--security-stage');args=a.parse_args()
assert re.fullmatch('[a-z0-9-]+',args.tag);w=r/('runtime/original-codesign-closure-'+args.tag);assert not w.exists();w.mkdir()
pins=json.loads((r/'config/signing-image-pins.json').read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();files={};links={};components=[]
for target in args.target:
    pin=pins[target];source=r/('runtime/rebuilt-'+target)/Path(pin['path']).name;report=source.parent/'reconstruction.json';data=json.loads(report.read_text());assert data['target']==target and data['original_image_sha256']==pin['sha256'] and data['staged_image_sha256']==sha(source)
    name=Path(pin['path'])
    if '.framework' in pin['path']:
        index=next(i for i,p in enumerate(name.parts) if p.endswith('.framework'));dest=w/'frameworks'/Path(*name.parts[index:]);framework=w/'frameworks'/name.parts[index]
        dest.parent.mkdir(parents=True);shutil.copy2(source,dest)
        for p,t in [(framework/'Versions/Current','A'),(framework/name.name,'Versions/Current/'+name.name)]:p.symlink_to(t);links[str(p.relative_to(r))]=t
    else:
        dest=w/'libraries'/name.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(source,dest)
    files.update({str(p.relative_to(r)):sha(p) for p in [source,report,dest]});components.append(dict(target=target,pin=pin,source=str(source.relative_to(r)),library=str(dest.relative_to(r))))
if args.security_stage:
    security=json.loads((r/args.security_stage).read_text())
    for name,digest in security['files'].items():assert sha(r/name)==digest,name
    for field in ['framework','library']:
        source=r/security[field];relative=source.relative_to(r/security['root']);dest=w/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);files.update({str(source.relative_to(r)):sha(source),str(dest.relative_to(r)):sha(dest)})
    for name in security.get('support_libraries',[]):
        source=r/name;dest=w/'libraries'/source.name;shutil.copy2(source,dest);files.update({name:sha(source),str(dest.relative_to(r)):sha(dest)})
    f=w/'frameworks/Security.framework'
    for p,t in [(f/'Versions/Current','A'),(f/'Security','Versions/Current/Security')]:p.symlink_to(t);links[str(p.relative_to(r))]=t
record=dict(root=str(w.relative_to(r)),components=components,files=files,links=links,security_stage=args.security_stage,installed=False,runtime_verified=False)
output=r/('artifacts/original-codesign-closure-'+args.tag+'-stage.json');assert not output.exists();output.write_text(json.dumps(record,indent=2)+'\n');print(output)
