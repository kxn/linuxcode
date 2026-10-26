"""Verify a recorded build input, including an explicitly frozen older revision.

Older private runtime variants keep their original binary and build manifest.
When a source is subsequently fixed, a content-addressed snapshot preserves the
exact input to those older builds; the new variant separately checks live inputs.
"""
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json
root=Path(__file__).resolve().parent.parent
def verify(item):
    name=item['source'];sha=item['sha256']
    digest=lambda path:verified_digest(path)
    if digest(root/name)==sha:return name
    frozen=json.loads((root/'runtime/source-input-history/manifest.json').read_text())
    entry=frozen[name]
    snapshot=entry['snapshot'] if entry['sha256']==sha else entry.get('revisions',{}).get(sha)
    assert snapshot=='runtime/source-input-history/'+sha,name
    assert digest(root/snapshot)==sha,name
    return snapshot
