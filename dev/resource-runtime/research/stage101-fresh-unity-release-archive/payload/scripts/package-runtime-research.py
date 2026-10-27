#!/usr/bin/env python3
"""Package an explicit UTF-8 source/evidence list without copying private binaries."""
from pathlib import Path
import argparse,hashlib,json,shutil
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec',required=True);a=p.parse_args();spec=json.loads((root/a.spec).read_text());private_logs=set(spec.get('private_logs',[]));assert all(isinstance(n,str) and not Path(n).is_absolute() and '..' not in Path(n).parts for n in private_logs);overlay=root/'distribution/linuxcode/dev/resource-runtime';folder=overlay/'research'/spec['name'];assert (folder/'README.md').is_file() and not (folder/'reference/original-file-map.json').exists();mapping={};sha=lambda b:hashlib.sha256(b).hexdigest()
def attach(name,payload=False):
    if name in mapping:return
    path=Path(name);assert not path.is_absolute() and '..' not in path.parts
    source=root/path;data=source.read_bytes();text=data.decode('utf-8')
    rel=('payload/' if payload else 'reference/')+name+('' if payload or name.endswith('.json') else '.json');target=folder/rel;assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True)
    if payload:shutil.copy2(source,target)
    elif name.endswith('.json'):target.write_bytes(data)
    else:target.write_text(json.dumps(dict(original_path=name,original_sha256=sha(data),encoding='utf-8',text=text),ensure_ascii=True,indent=2)+'\n')
    mapping[name]=dict(sha256=sha(data),attachment=rel,wrapped_utf8=not payload and not name.endswith('.json'))
for name in [*spec['payload'],str(Path(__file__).relative_to(root)),a.spec]:attach(name,True)
for name in spec['reference']:
    attach(name)
    if name.endswith('.json'):
        record=json.loads((root/name).read_text());log=record.get('log') if isinstance(record,dict) else None
        if isinstance(log,str) and log not in private_logs and (root/log).is_file():attach(log)
history=json.loads((root/'runtime/source-input-history/manifest.json').read_text());selected={n:history[n] for n in spec['payload'] if n in history}
for row in selected.values():
    for name in set([row['snapshot'],*row.get('revisions',{}).values()]):attach(name)
(folder/'reference/source-history.json').write_text(json.dumps(selected,indent=2)+'\n');(folder/'reference/original-file-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
for name,row in mapping.items():
    b=(folder/row['attachment']).read_bytes()
    if row['wrapped_utf8']:b=json.loads(b)['text'].encode('utf-8')
    assert sha(b)==row['sha256'],name
manifest=overlay/'overlay.json';d=json.loads(manifest.read_text())
for path in folder.rglob('*'):
    if path.is_file():d['research_files'][str(path.relative_to(overlay))]=sha(path.read_bytes())
manifest.write_text(json.dumps(d,indent=2)+'\n');print('PACKAGED',len(mapping),'attachments',folder)
