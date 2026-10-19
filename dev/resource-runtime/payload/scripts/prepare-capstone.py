#!/usr/bin/env python3
"""Install the pinned Linux x86_64 decoder into this project, without pip."""
from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile

project=Path(__file__).resolve().parent.parent
config=json.loads((project/'config/capstone.json').read_text())
archive=project/'downloads'/config['filename']
archive.parent.mkdir(parents=True,exist_ok=True)
if not archive.is_file():
    with urllib.request.urlopen(config['url']) as source:
        archive.write_bytes(source.read())
data=archive.read_bytes()
if len(data)!=config['length'] or hashlib.sha256(data).hexdigest()!=config['sha256']:
    raise ValueError('Pinned Capstone wheel length/SHA256 mismatch')
destination=project/'runtime/tools/python-capstone'
destination.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(archive) as source:
    for member in source.infolist():
        target=destination/member.filename
        if not target.resolve().is_relative_to(destination.resolve()):raise ValueError('Unsafe wheel member path')
        if member.is_dir():target.mkdir(parents=True,exist_ok=True);continue
        original=source.read(member)
        if target.is_file() and target.read_bytes()==original:continue
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original)
print('Pinned Capstone decoder verified in project-local runtime/tools; host Python unchanged.')
