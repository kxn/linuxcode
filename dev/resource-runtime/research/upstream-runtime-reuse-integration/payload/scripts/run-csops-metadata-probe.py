#!/usr/bin/env python3
"""Run prepared self-owned csops fixtures with one shared Darling bootstrap."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile,time
ROOT=Path(__file__).resolve().parent.parent

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',required=True);p.add_argument('--stage',required=True);p.add_argument('--configuration',required=True);p.add_argument('--case',choices=['all','unsigned','signed-thin','signed-fat','signed-peer'],default='all');a=p.parse_args();sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 prepared=(ROOT/a.prepared).resolve(strict=True);assert prepared.is_relative_to(ROOT/'runtime');d=json.loads(prepared.read_text());assert d['own_fixture_only']
 for n,h in d['files'].items():assert sha(ROOT/n)==h,n
 module=runpy.run_path(str(ROOT/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration=a.configuration);assert profile['direct_resource_environment']['runtime_mode']=='unified'
 w=Path(tempfile.mkdtemp(prefix='csops-metadata-native-',dir=ROOT/'runtime'));guest=lambda n:'/Volumes/SystemRoot/workspace/'+n
 cases=[('unsigned',[guest(d['unsigned']),'--unsigned']),('signed-thin',[guest(d['signed']),'--signed',guest(d['xml_blob']),guest(d['der_blob']),guest(d['cdhash'])])]
 if d.get('fat'):
  f=d['fat'];cases.append(('signed-fat',[guest(f['signed']),'--signed',guest(f['xml_blob']),guest(f['der_blob']),guest(f['cdhash'])]))
 if a.case not in ['all','signed-peer']:
  cases=[row for row in cases if row[0]==a.case];assert cases,'Requested fixture case is unavailable'
 if a.case=='signed-peer':cases=[]
 lines=['#!/bin/bash','ulimit -c 0','overall=0']
 for name,argv in cases:lines += [shlex.join(argv),'s=$?',f'printf "CSOPS_CASE_STATUS {name} %s\\n" "$s"','if [ "$s" -ne 0 ]; then overall=1; fi']
 # A separate signed process proves caller buffers are not confused with peer memory.
 if a.case in ['all','signed-peer']:
  peer_token=w/'peer-token.bin';peer_argv=[guest(d['signed']),'--peer',guest(str(peer_token.relative_to(ROOT))),guest(d['xml_blob']),guest(d['der_blob']),guest(d['cdhash'])]
  lines += [shlex.join([guest(d['signed']),'--serve-token',guest(str(peer_token.relative_to(ROOT)))])+' &','peer_pid=$!',"trap 'kill \"$peer_pid\" 2>/dev/null || true' EXIT",'for attempt in 1 2 3 4 5 6 7 8 9 10; do',f'  if [ -s {shlex.quote(guest(str(peer_token.relative_to(ROOT))))} ]; then break; fi','  /bin/sleep 0.1','done',shlex.join(peer_argv),'s=$?','printf "CSOPS_CASE_STATUS signed-peer %s\\n" "$s"','if [ "$s" -ne 0 ]; then overall=1; fi','kill "$peer_pid" 2>/dev/null || true','wait "$peer_pid" 2>/dev/null || true','trap - EXIT']
  cases.append(('signed-peer',peer_argv))
 lines+=['exit "$overall"'];script=w/'guest.sh';script.write_text('\n'.join(lines)+'\n');cmd=profile['command'][:-2]+['/bin/bash',guest(str(script.relative_to(ROOT)))];cmd[3]='45';log=w/'native.log';start=time.monotonic()
 with log.open('w') as out:result=subprocess.run(cmd,cwd=ROOT,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
 t=log.read_text(errors='replace');statuses=re.findall(r'^CSOPS_CASE_STATUS (\S+) (\d+)$',t,re.M);expected=[(name,'0') for name,_ in cases];signed=t.count('CSOPS_SIGNED_METADATA_AND_ORIGINAL_SECTASK_OK')
 record=dict(case=a.case,verified=result.returncode==0 and statuses==expected and signed==sum(name!='unsigned' for name,_ in cases) and (not any(name=='unsigned' for name,_ in cases) or 'CSOPS_UNSIGNED_METADATA_OK' in t),outer_status=result.returncode,native_statuses=statuses,signed_original_SecTask_completions=signed,elapsed_seconds=time.monotonic()-start,prepared=str(prepared.relative_to(ROOT)),prepared_sha256=sha(prepared),configuration=a.configuration,configuration_sha256=sha(ROOT/a.configuration),stage=a.stage,stage_sha256=sha(ROOT/a.stage),command=cmd,all_cases_share_one_library_configuration=True,per_executable_configuration_generated=False,original_Security_framework_consumer_exercised=True,own_fixtures_only=True,metadata_reading_only=True,Apple_platform_identity_or_kernel_permission_enforcement_claimed=False,files={str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__),script,log]},raw_log_publishable=False)
 (w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:record[k] for k in ['verified','outer_status','native_statuses','signed_original_SecTask_completions','elapsed_seconds']},indent=2));print('EVIDENCE',w/'result.json');return 0 if record['verified'] else 1
if __name__=='__main__':raise SystemExit(main())
