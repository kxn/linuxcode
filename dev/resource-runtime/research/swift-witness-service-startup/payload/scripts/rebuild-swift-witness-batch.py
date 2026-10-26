#!/usr/bin/env python3
"""Prepare independent original witness repairs with bounded host-side concurrency."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,subprocess
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--audit',required=True);p.add_argument('--tag',required=True);p.add_argument('--output',required=True);a=p.parse_args();assert a.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.tag);out=r/a.output;assert not out.exists();audit=json.loads((r/a.audit).read_text());wanted=[v for v in audit['results'] if v['missing_tables']];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def work(item):
 assert sha(r/item['contracts'])==item['contracts_sha256'];target=item['target']+'-'+a.tag;log=r/('logs/'+target+'-prepare.log');assert not log.exists()
 command=['python3','scripts/prepare-resource-image-candidate.py','--from-target',item['target'],'--pooled-swift-witness-contracts',item['contracts'],'--target',target,'--build']
 with log.open('w') as output:status=subprocess.run(command,cwd=r,stdout=output,stderr=subprocess.STDOUT).returncode
 return dict(parent_target=item['target'],target=target,returncode=status,missing_tables=item['missing_tables'],references=item['references'],contracts=item['contracts'],command=command,log=str(log.relative_to(r)),log_sha256=sha(log))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 results=list(pool.map(work,wanted))
for row in results:print(row['target'],row['returncode'],flush=True)
result=dict(prepared_all=all(v['returncode']==0 for v in results),audit=a.audit,audit_sha256=sha(r/a.audit),images=[dict(prepared_target=v['target'],**v) for v in results],complete=all(v['returncode']==0 for v in results),runtime_verified=False,full_goal_complete=False);out.write_text(json.dumps(result,indent=2)+'\n');raise SystemExit(0 if result['prepared_all'] else 1)
