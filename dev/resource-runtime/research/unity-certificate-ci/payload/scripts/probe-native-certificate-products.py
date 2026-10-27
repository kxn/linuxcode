#!/usr/bin/env python3
"""Strictly verify existing certificate products with the original native frontend."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile

r = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate', required=True)
p.add_argument('--identity-store', required=True)
p.add_argument('--product', action='append', required=True)
a = p.parse_args()
candidate = json.loads((r / a.candidate).read_text())
module = runpy.run_path(str(r / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=candidate['inputs']['stage']['path'],
                            configuration=candidate['inputs']['configuration']['path'])
profile = runpy.run_path(str(r / 'scripts/native-certificate-runtime.py'))['select'](profile, a.candidate, a.identity_store)
folder = Path(tempfile.mkdtemp(prefix='native-certificate-products-', dir=r / 'runtime'))
folder.chmod(0o700)
cert = profile['native_certificate_runtime']
lines = ['#!/bin/bash', 'set -e', 'ulimit -c 0', 'unset DISPLAY WAYLAND_DISPLAY XAUTHORITY',
         cert['startup'], 'trap ' + shlex.quote(cert['cleanup']) + ' EXIT', 'set +e', 'failed=0']
for index, name in enumerate(a.product):
    path = (r / name).resolve(strict=True); assert path.is_relative_to(r / 'runtime')
    lines += [shlex.join(['/usr/bin/codesign', '--verify', '--strict', '--verbose=4',
                         '/Volumes/SystemRoot/workspace/' + str(path.relative_to(r))]),
              'status=$?', f'printf "CERTIFICATE_PRODUCT_{index}_STATUS %s\\n" "$status"',
              'if [ "$status" -ne 0 ]; then failed=1; fi']
lines.append('exit "$failed"')
script = folder / 'run.sh'; script.write_text('\n'.join(lines) + '\n')
command = profile['command'][:-2] + ['/bin/bash', '/Volumes/SystemRoot/workspace/' + str(script.relative_to(r))]
command[3] = '180'
env = module['environment'](profile)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']: env.pop(name, None)
log = folder / 'run.log'
print('RUNNING', folder.relative_to(r), flush=True)
with log.open('w') as stream: res = subprocess.run(command, cwd=r, env=env, stdout=stream, stderr=subprocess.STDOUT)
text = log.read_text(); statuses = re.findall(r'^CERTIFICATE_PRODUCT_(\d+)_STATUS (\d+)$', text, re.M)
verified = res.returncode == 0 and statuses == [(str(i), '0') for i in range(len(a.product))]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
record = dict(verified=verified, products=a.product, native_statuses=statuses, outer_status=res.returncode,
              candidate=a.candidate, candidate_sha256=sha(r / a.candidate), command=command,
              log=str(log.relative_to(r)), log_sha256=sha(log),
              script=str(script.relative_to(r)), script_sha256=sha(script),
              certificate_runtime=cert, source_sha256=sha(Path(__file__)),
              certificate_chain_or_device_trust_verified=False, full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(text[-3500:]); print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
