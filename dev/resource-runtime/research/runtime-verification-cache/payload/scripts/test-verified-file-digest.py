#!/usr/bin/env python3
"""Verify persistent digest hits, mutation invalidation and concurrent publication."""
from pathlib import Path
import concurrent.futures,hashlib,json,os,runpy,subprocess,sys,tempfile,time
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='digest-cache-controls-',dir=r/'runtime'));cache=w/'cache.json';os.environ['LINUXCODE_FILE_DIGEST_CACHE']=str(cache);module=r/'scripts/verified-file-digest.py';m=runpy.run_path(str(module));digest=m['digest'];cases=[]
def check(name,test):
 assert test,name;cases.append(dict(case=name,verified=True))
p=w/'input';p.write_bytes(b'one');time.sleep(1.05);expected=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();check('cold_hash',digest(p)==expected(p));before=m['statistics']();check('unchanged_file_hits_cache',digest(p)==expected(p) and m['statistics']()['files_hashed']==before['files_hashed'])
st=p.stat();p.write_bytes(b'two');os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns));check('same_size_restored_mtime_uses_ctime',digest(p)==expected(p) and digest(p)!=hashlib.sha256(b'one').hexdigest())
replacement=w/'replacement';replacement.write_bytes(b'new');os.replace(replacement,p);check('atomic_replacement_invalidates',digest(p)==expected(p));other=w/'other';other.write_bytes(b'other');time.sleep(1.05);link=w/'link';link.symlink_to(p.name);assert digest(link)==expected(p);link.unlink();link.symlink_to(other.name);check('symlink_target_change_invalidates',digest(link)==expected(other));p.unlink()
try:digest(p)
except FileNotFoundError:check('deleted_file_is_not_a_cache_hit',True)
else:raise AssertionError('Deleted file accepted')
assert digest(other)==expected(other)
m['state'].flush()
code="import runpy,json,sys; m=runpy.run_path(sys.argv[1]); print(m['digest'](sys.argv[2])); print(json.dumps(m['statistics']()))"
def child(path,cache_path=cache):
 env=dict(os.environ,LINUXCODE_FILE_DIGEST_CACHE=str(cache_path));result=subprocess.run([sys.executable,'-c',code,str(module),str(path)],env=env,capture_output=True,text=True,check=True);lines=result.stdout.splitlines();assert lines[0]==expected(path);return json.loads(lines[1])
check('separate_process_reuses_digest',child(other)['files_hashed']==0)
inputs=[]
for i in range(2):
 path=w/('parallel-'+str(i));path.write_bytes(str(i).encode());inputs.append(path)
with concurrent.futures.ThreadPoolExecutor(2) as pool:list(pool.map(child,inputs))
saved=json.loads(cache.read_text())['entries'];check('concurrent_cache_updates_merge',all(str(p.absolute()) in saved for p in inputs))
bad=w/'bad-cache.json';bad.write_text('{broken');check('malformed_disposable_cache_rehashes',child(other,bad)['files_hashed']==1)
report=r/'artifacts/verified-file-digest-controls-v1.json';assert not report.exists();report.write_text(json.dumps(dict(verified=True,cases=cases,source=str(module.relative_to(r)),source_sha256=hashlib.sha256(module.read_bytes()).hexdigest(),test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runtime_execution_results_cached=False,full_goal_complete=False),indent=2)+'\n');print('VERIFIED',len(cases),'cache controls')
