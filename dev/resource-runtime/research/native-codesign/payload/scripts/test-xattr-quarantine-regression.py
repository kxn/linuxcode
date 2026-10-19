#!/usr/bin/env python3
"""Run the existing active-policy Quarantine fixture with the new xattr kernel."""
from pathlib import Path
import argparse,hashlib,json,os,re,runpy,subprocess,tempfile
a=argparse.ArgumentParser();a.add_argument("--xattr-stage",default="artifacts/xattr-runtime-v1-stage.json");args=a.parse_args()
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='xattr-quarantine-regression-',dir=r/'runtime'));output=w/'output';output.mkdir();test=r/'runtime/quarantine-vfs-test/test';leaf=r/'runtime/quarantine-vfs-test/leaf';guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r))
m=runpy.run_path(str(r/'scripts/xattr-runtime-profile.py'));p=m['profile'](xattr_stage=args.xattr_stage,derq_stage='artifacts/derq-original-v1-stage.json',identity_stage='artifacts/local-identity-store-readonly-v2-stage.json',identity_store='runtime/local-identity-xcode-empty-v1/store.plist',codesign_stage='artifacts/codesign-zsign-adhoc-v2-stage.json');command=p['command'][:-2]+[guest(test),guest(output),guest(leaf),'source'];command[3]='120';env=m['environment'](p)
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();markers=['QUARANTINE_VFS_RESTRICTED_PROCESS_FILE_EVENTS_AND_EXEC_CHECKS_OK checks=','QUARANTINE_VFS_REAL_PERSISTED_LABELS_KERNEL_PAIRING_FORK_EXEC_AND_UNCONFINED_CONTROL_OK'];ok=res.returncode==0 and all(re.search('^'+re.escape(v),text,re.M) for v in markers);physical=False
if ok:
    for n in ['new','existing','directory','renamed','fork-inherited','exec-inherited']:assert os.getxattr(output/n,'user.com.apple.quarantine').startswith((b'0082;',b'0086;'))
    assert os.getxattr(output/'new','user.user.com.apple.quarantine')==b'shadow';physical=True
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();record=dict(verified=ok and physical,outer_status=res.returncode,physical_Linux_labels_verified=physical,log=str(log.relative_to(r)),log_sha256=sha(log),test_binary_sha256=sha(test),leaf_binary_sha256=sha(leaf),test_driver_sha256=sha(__file__),original_policy_denials_and_fork_exec_semantics_preserved=ok)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3500:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok and physical else 1)
