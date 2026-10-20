#!/usr/bin/env python3
"""Save exact source inputs before editing, preserving all historical digests."""
from pathlib import Path
import fcntl,hashlib,json,os,sys,tempfile
root=Path(__file__).resolve().parent.parent
folder=root/'runtime/source-input-history';folder.mkdir(parents=True,exist_ok=True);manifest=folder/'manifest.json'
with (folder/'writer.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    records=json.loads(manifest.read_text()) if manifest.exists() else {}
    for name in sys.argv[1:]:
        relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
        source=root/relative;assert source.is_file() and source.resolve().is_relative_to(root)
        data=source.read_bytes();digest=hashlib.sha256(data).hexdigest();target=folder/digest
        if target.is_dir():target/=relative.name
        if target.exists():assert target.read_bytes()==data
        else:
            with target.open('xb') as out:out.write(data)
        key=str(relative);old=records.get(key,{});revisions=dict(old.get('revisions',{}))
        if old.get('sha256'):revisions[old['sha256']]=old['snapshot']
        records[key]=dict(sha256=digest,snapshot=str(target.relative_to(root)),revisions=revisions)
    fd,name=tempfile.mkstemp(prefix='.manifest-',dir=folder)
    try:
        with os.fdopen(fd,'w') as out:out.write(json.dumps(records,indent=2)+'\n')
        os.replace(name,manifest)
    finally:
        if Path(name).exists():Path(name).unlink()
print('Archived',len(sys.argv)-1,'source inputs')
