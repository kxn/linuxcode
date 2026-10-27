#!/usr/bin/env python3
"""Download pinned official Linux Editor/iOS modules with resumable HTTP ranges."""
from pathlib import Path
import base64,concurrent.futures,hashlib,json,os,subprocess,time,urllib.request
r=Path(__file__).resolve().parent.parent;folder=r/'runtime/unity-editor-downloads-v1';inputs=json.loads((folder/'inputs.json').read_text());chunk=16*1024*1024
jobs=[]
for name in ['editor','ios']:
    item=inputs[name];size=item['downloadSize']['value'];parts=folder/(name+'-parts');parts.mkdir(exist_ok=True)
    for start in range(0,size,chunk):jobs.append((name,item,start,min(size,start+chunk)-1,parts/(str(start)+'.part')))
def fetch(job):
    name,item,start,end,path=job;expected=end-start+1
    if path.exists() and path.stat().st_size==expected:return name,expected
    pending=path.with_suffix('.pending')
    for attempt in range(5):
        try:
            existing=pending.stat().st_size if pending.exists() else 0
            if existing>expected:raise RuntimeError('Partial range exceeds expected size')
            if existing==expected:pending.replace(path);return name,expected
            current=start+existing;deadline=time.monotonic()+120
            request=urllib.request.Request(item['url'],headers={'Range':f'bytes={current}-{end}'})
            with urllib.request.urlopen(request,timeout=30) as response,pending.open('ab') as out:
                assert response.status==206 and response.headers['Content-Range']==f'bytes {current}-{end}/{item["downloadSize"]["value"]}'
                count=existing
                while True:
                    if time.monotonic()>deadline:raise TimeoutError('Range transfer deadline')
                    data=response.read1(min(256*1024,expected-count+1))
                    if not data:break
                    count+=len(data)
                    if count>expected:raise RuntimeError('Server returned more than the requested range')
                    out.write(data);out.flush()
                if count!=expected:raise RuntimeError('Incomplete range')
            pending.replace(path);return name,expected
        except Exception:
            if attempt==4:raise
            time.sleep(attempt+1)

completed=0
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
    for future in concurrent.futures.as_completed([pool.submit(fetch,job) for job in jobs]):
        name,size=future.result()
        completed+=size
        if completed//(128*1024*1024)!=(completed-size)//(128*1024*1024):print('DOWNLOADED_MiB',completed//(1024*1024),flush=True)
records={}
for name in ['editor','ios']:
    item=inputs[name];output=folder/(name+'.tar.xz')
    if output.exists():output.rename(folder/(name+'.initial-partial.tar.xz'))
    pending=folder/(name+'.assembled');md5=hashlib.md5();sha=hashlib.sha256()
    with pending.open('wb') as out:
        for job in jobs:
            if job[0]!=name:continue
            with job[4].open('rb') as stream:
                while data:=stream.read(4*1024*1024):out.write(data);md5.update(data);sha.update(data)
    algorithm,digest=item['integrity'].split('-',1);assert algorithm=='md5' and md5.digest()==base64.b64decode(digest)
    assert pending.stat().st_size==item['downloadSize']['value'];pending.rename(output)
    records[name]=dict(path=str(output.relative_to(r)),sha256=sha.hexdigest(),official_integrity=item['integrity'],bytes=output.stat().st_size)
(folder/'verified-downloads.json').write_text(json.dumps(dict(version=inputs['version'],revision=inputs['revision'],verified=True,files=records),indent=2)+'\n');print('OFFICIAL_DOWNLOADS_VERIFIED',flush=True)
