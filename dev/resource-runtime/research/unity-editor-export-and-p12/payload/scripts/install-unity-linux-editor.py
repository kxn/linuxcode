#!/usr/bin/env python3
"""Extract verified official Unity Editor/iOS archives into a separate local prefix."""
from pathlib import Path
import hashlib,json,subprocess,tarfile
r=Path(__file__).resolve().parent.parent;folder=r/'runtime/unity-editor-downloads-v1';verified=json.loads((folder/'verified-downloads.json').read_text());assert verified['verified']
target=r/('runtime/unity-editor-linux-'+verified['version']);assert not target.exists();target.mkdir()
def extract(name,destination):
    item=verified['files'][name];archive=r/item['path'];assert archive.stat().st_size==item['bytes']
    destination.mkdir(parents=True,exist_ok=True)
    subprocess.run(['tar','--extract','--xz','--file',str(archive),'--directory',str(destination),'--no-same-owner'],check=True)
extract('editor',target)
module=r/verified['files']['ios']['path']
with tarfile.open(module,mode='r|xz') as stream:
    first=next((m.name.removeprefix('./') for m in stream if m.name.removeprefix('./') not in ['', '.']),None)
if first and (first=='Editor' or first.startswith('Editor/')):destination=target
elif first and (first=='iOSSupport' or first.startswith('iOSSupport/')):destination=target/'Editor/Data/PlaybackEngines'
else:raise RuntimeError('Unknown iOS module archive layout: '+str(first))
extract('ios',destination);editor=target/'Editor/Unity';support=target/'Editor/Data/PlaybackEngines/iOSSupport'
assert editor.is_file() and support.is_dir();assert editor.open('rb').read(4)==b'\x7fELF'
ldd=subprocess.run(['ldd',str(editor)],capture_output=True,text=True);(target/'ldd.log').write_text(ldd.stdout+ldd.stderr)
record=dict(installed=True,version=verified['version'],revision=verified['revision'],native_linux_x86_64=True,private_prefix=str(target.relative_to(r)),editor=str(editor.relative_to(r)),editor_sha256=hashlib.sha256(editor.read_bytes()).hexdigest(),ios_support=str(support.relative_to(r)),official_downloads='runtime/unity-editor-downloads-v1/verified-downloads.json',missing_linked_libraries=[l.strip() for l in ldd.stdout.splitlines() if 'not found' in l],license_activated=False,Unity_export_verified=False)
(target/'installation.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
