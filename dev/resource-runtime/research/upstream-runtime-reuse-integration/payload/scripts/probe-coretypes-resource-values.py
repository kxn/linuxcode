#!/usr/bin/env python3
"""Run actual Foundation URL metadata/NSFileManager operations on CoreTypes."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, subprocess
root=Path(__file__).resolve().parent.parent
digest=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--wait',action='store_true');args=parser.parse_args()
profile=json.loads((root/'artifacts/uniform-type-identifiers-native-xcode-sysdir-sandbox-container-nounlink-typed-malloc-simple-log-datavault-user-local-dir-source-libtrace-source-objc-support-showsdks.json').read_text())
environment=os.environ.copy()
for key,item in profile['source_runtime'].items():
    assert digest(item['path'])==item['sha256'];environment[key]=str(root/item['path'])
command=profile['command'][:-2]+['/Volumes/SystemRoot/workspace/artifacts/coretypes-resource-values']+(['--wait'] if args.wait else [])
if args.wait:command[3]='180'
log='logs/coretypes-resource-values'+('-debug' if args.wait else '')+'.log'
with (root/log).open('w') as stream:
    process=subprocess.Popen(command,cwd=root,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    for line in process.stdout:stream.write(line);stream.flush();print(line,end='',flush=True)
    status=process.wait()
report=dict(checked_at=datetime.now(timezone.utc).isoformat(),command=command,source_runtime=profile['source_runtime'],
    exit_status=status,log=log,log_sha256=digest(log),source_sha256=digest('fixtures/hello/coretypes-resource-values.m'),
    binary_sha256=digest('artifacts/coretypes-resource-values'),Foundation_URL_and_enumeration_verified=status==0,
    full_xcode_build_ready=False,signing_ready=False)
(root/('artifacts/coretypes-resource-values'+('-debug' if args.wait else '')+'.json')).write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if status==0 else 1)
