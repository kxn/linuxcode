#!/usr/bin/env python3
"""Compile the real client receive hook against real Linux sockets and signals.

Only native syscall error/race injection and a controlled socket peer are test
boundaries. No production server protocol, Darling session, or Mach-O program is
run. Historical header is the exact archived pre-fix source, not a model.
"""
from pathlib import Path
import argparse,hashlib,json,resource,runpy,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
relative='vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/include/linux_premigration/resources/dserver-rpc-defs.h'
source=root/relative
historical_sha='78b18f8f91f73fdecf9327d660ea89cefb2ef5066d3a2e5785586e254d834b6f'
fixture=root/'fixtures/hello/client-s2c-signal-boundary.c'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--variants',nargs='+',choices=['candidate','historical'],default=['candidate','historical'])
a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='client-s2c-signal-boundary-',dir=root/'runtime'))
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
historical=root/resolve(relative,historical_sha)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inputs={};commands=[];results={}
snapshot=folder/'fixture.c';shutil.copyfile(fixture,snapshot);inputs[str(fixture.relative_to(root))]=sha(snapshot)
cases=['normal','idle-chld','idle-rt','critical-chld','critical-rt','critical-fd',
       'fd-after-no-fd','eagain','send-error','negative-fd','closed-fd','poll-error']
def extract(text):
 start=text.index('static long int dserver_rpc_hooks_receive_message(')
 opening=text.index('{',start);depth=1;i=opening+1
 while depth:
  if text[i]=='{':depth+=1
  elif text[i]=='}':depth-=1
  i+=1
 return text[start:i]+'\n'
for variant in a.variants:
 src=source if variant=='candidate' else historical;v=folder/variant;v.mkdir()
 header=v/'production-header.h';shutil.copyfile(src,header);inputs[str(src.relative_to(root))]=sha(header)
 (v/'receive-function.inc').write_text(extract(header.read_text()))
 binary=v/'probe';command=['cc','-std=gnu11','-O1','-g','-pthread','-Wno-int-conversion',
                          '-I'+str(v),'-I'+str(root/'vendor/darlingserver/include'),str(snapshot),'-o',str(binary)]
 commands.append(command);subprocess.run(command,check=True,cwd=root)
 rows=[]
 for case in cases:
  try:
   r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=6,
                    preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
   status,output=r.returncode,r.stdout+r.stderr
  except subprocess.TimeoutExpired as e:status,output=124,str(e)
  (v/(case+'.log')).write_text(output);rows.append(dict(case=case,status=status,output=output))
  print(variant,case,status,output.strip(),flush=True)
 results[variant]=rows;inputs[str(binary.relative_to(root))]=sha(binary)
failures={'critical-chld','critical-rt','critical-fd'}
verified=all(row['status']==0 if variant=='candidate' or row['case'] not in failures else
             row['status']==42 and 'EXPECTED_DEADLOCK' in row['output']
             for variant,rows in results.items() for row in rows)
for file in [Path(__file__),root/'vendor/darlingserver/include/darlingserver/rpc-supplement.h']:
 inputs[str(file.relative_to(root))]=sha(file)
report=dict(verified=verified,results=results,files=inputs,commands=commands,
 scope='Exact production dserver_rpc_hooks_receive_message, real Linux AF_UNIX datagram socket pair, '
       'signals, ppoll/rt_sigprocmask, mmap and SCM_RIGHTS. Controlled peer releases ordinary acknowledgements '
       'only after receiving the actual S2C reply; signal handler recursively calls the same receive hook. '
       'Deterministic signal injection immediately after real recv has consumed request. No production '
       'server, actual full InterruptEnter RPC, Darling boot, Mach-O or application build coverage.',
 expected_historical_deadlocks=sorted(failures),historical_header_sha256=historical_sha)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
