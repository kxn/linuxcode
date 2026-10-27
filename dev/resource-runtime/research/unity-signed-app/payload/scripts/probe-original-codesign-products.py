#!/usr/bin/env python3
"""Verify actual products with original codesign and independent hash/seal checks."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--product',action='append',required=True);a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='original-codesign-products-',dir=root/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();bundle=runpy.run_path(str(root/'scripts/verify-adhoc-bundle.py'))['verify'];generic=runpy.run_path(str(root/'scripts/verify-adhoc-generic-file.py'))['verify'];checks={}
for n in a.product:
 target=root/n;assert target.exists() and target.resolve().is_relative_to(root/'runtime');checks[n]=bundle(target) if target.is_dir() else generic(target)
mod=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=mod['profile'](stage=a.stage,configuration=a.configuration);env=mod['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
command=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(command) if v.startswith(key+'='));command[i]=key+'='+scope[key]
guest=lambda n:'/Volumes/SystemRoot/workspace/'+n;lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY','failed=0']
for i,n in enumerate(a.product):lines.extend([shlex.join(['/usr/bin/codesign','--verify','--strict','--verbose=2',guest(n)]),'status=$?',f'printf "ORIGINAL_CODESIGN_PRODUCT_{i}_STATUS %s\\n" "$status"','if [ "$status" -ne 0 ]; then failed=1; fi'])
lines.append('exit "$failed"');script=folder/'run.sh';script.write_text('\n'.join(lines)+'\n');command+=['/bin/bash',guest(str(script.relative_to(root)))];command[3]='180';log=folder/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ORIGINAL_CODESIGN_PRODUCT_([0-9]+)_STATUS ([0-9]+)$',t,re.M);expected=[(str(i),'0') for i in range(len(a.product))];verified=res.returncode==0 and statuses==expected and all(v['verified'] for v in checks.values());report=dict(verified=verified,stage=a.stage,configuration=a.configuration,source_runtime=profile['source_runtime'],outer_status=res.returncode,native_statuses=statuses,independent_checks=checks,command=command,log=str(log.relative_to(root)),log_sha256=sha(log),sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/'scripts/verify-adhoc-bundle.py',root/'scripts/verify-adhoc-generic-file.py',root/a.stage,root/a.configuration]},ad_hoc_only=True,certificate_or_device_trust_verified=False,zsign_used=False,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-6000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
