#!/usr/bin/env python3
"""Run original absolute-path resource tools with the source-level child environment scope."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', default='config/direct-resource-tool-environment-v2.json')
parser.add_argument('--tool', choices=['actool', 'ibtool'], action='append', help='Run only the selected tools for a focused diagnostic; default remains both')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='direct-resource-tools-', dir=root / 'runtime'))
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
p = module['profile'](stage=args.stage, configuration=args.configuration)
env = module['environment'](p)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(name, None)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
cases = []
for tool in (args.tool or ['actool', 'ibtool']):
    path = 'Applications/Xcode.app/Contents/Developer/usr/bin/' + tool
    original = root / 'runtime/state/prefix' / path
    extracted = root / 'runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin' / tool
    digest = sha(original)
    assert digest == sha(extracted)
    script = folder / (tool+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
        shlex.join(['/' + path, '--version']) + '\nstatus=$?\nprintf "DIRECT_RESOURCE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = p['command'][:-2] + ['/bin/bash', '/Volumes/SystemRoot/workspace/' + str(script.relative_to(root))]
    command[3] = '90'
    log = folder / (tool+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^DIRECT_RESOURCE_STATUS (\d+)$', text, re.M)
    assert sha(original) == digest
    cases.append(dict(tool=tool, original_sha256=digest, original_extracted_bytes_equal=True,
        command=command, outer_status=result.returncode, native_status=statuses,
        verified=result.returncode == 0 and statuses == ['0'],
        resource_framework_loading_observed='/runtime/ios-resource-lazy-v1/frameworks/' in text,
        log=str(log.relative_to(root)), log_sha256=sha(log)))
    print(tool, text[-2000:], flush=True)
record = dict(verified=all(case['verified'] for case in cases), stage=args.stage,
    scope=p['direct_resource_environment'], cases=cases, full_resource_compilation_verified=False,
    sources={str(path.relative_to(root)): sha(path) for path in [Path(__file__), root / 'scripts/direct-resource-tool-runtime-profile.py', root / args.stage]})
(folder / 'result.json').write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if record['verified'] else 1)
