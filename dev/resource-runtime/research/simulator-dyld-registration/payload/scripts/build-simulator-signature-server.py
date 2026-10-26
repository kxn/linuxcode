#!/usr/bin/env python3
"""Build a private descriptor-based simulator signature registration server."""
from pathlib import Path
import argparse,fcntl,hashlib,json,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',required=True);a=p.parse_args()
parent=json.loads((root/a.parent_stage).read_text())
folder=Path(tempfile.mkdtemp(prefix='simulator-signature-server-',dir=root/'runtime'))
build=root/'runtime/darlingserver-source-build';baseline=build/'darlingserver/darlingserver'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
expected='ae78babd377dd542788f321752b11e9dea6413ee49d1009f00df825fdd9efd6b'
command=['cmake','--build',str(build),'--target','darlingserver','-j','8']
with (root/'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);assert sha(baseline)==expected
    backup=folder/'baseline-build-output';shutil.copy2(baseline,backup)
    try:
        baseline.unlink()
        with (folder/'build.log').open('w') as out:subprocess.run(command,cwd=root,stdout=out,stderr=subprocess.STDOUT,check=True)
        shutil.copy2(baseline,folder/'darlingserver')
    finally:
        replacement=folder/'baseline.restore';shutil.copy2(backup,replacement);replacement.replace(baseline)
    assert sha(baseline)==expected
repo=root/'vendor/darlingserver'
names=subprocess.check_output(['git','-C',str(repo),'ls-files','-co','--exclude-standard','-z'],text=True).split('\0')
inputs={str((repo/n).relative_to(root)):sha(repo/n) for n in names if n and (repo/n).is_file()}
selected={key:dict(value) for key,value in parent['source_runtime'].items()}
selected['LINUXCODE_DARLING_SERVER']=dict(path=str((folder/'darlingserver').relative_to(root)),sha256=sha(folder/'darlingserver'))
report=dict(full_server_source_build=True,installed=False,baseline_build_output_restored=True,baseline_build_output_sha256=expected,command=command,parent_stage=a.parent_stage,previous_source_runtime=parent['source_runtime'],source_runtime=selected,server=str((folder/'darlingserver').relative_to(root)),server_sha256=sha(folder/'darlingserver'),source_files=inputs,files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/a.parent_stage,folder/'build.log']},runtime_execution_verified=False,full_goal_complete=False)
(folder/'stage.json').write_text(json.dumps(report,indent=2)+'\n');print('STAGE_REPORT',folder/'stage.json',flush=True)
