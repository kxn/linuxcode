#!/usr/bin/env python3
"""Combine a coherent kernel root with the full source libSystem candidate."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel-stage', required=True)
parser.add_argument('--libsystem-build', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag.isalnum()
target = root / ('artifacts/exec-environment-runtime-' + args.tag + '-stage.json')
assert not target.exists()
kernel = json.loads((root / args.kernel_stage).read_text())
parent_profile = 'scripts/libsystem-kqueue-runtime-profile.py'
p = runpy.run_path(str(root / parent_profile))['profile'](stage=args.libsystem_build)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name, digest in kernel['files'].items():
    runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve'](name, digest)
files = {**kernel['files'], **{str(path.relative_to(root)): sha(path) for path in
    [Path(__file__), root / args.kernel_stage, root / args.libsystem_build]}}
data = dict(installed=False, parent_profile=parent_profile,
    parent_profile_arguments=dict(stage=args.libsystem_build),
    previous_source_runtime=p['source_runtime'], source_runtime=kernel['source_runtime'],
    files=files, kernel_stage=args.kernel_stage, runtime_execution_verified=False,
    full_goal_complete=False)
target.write_text(json.dumps(data, indent=2) + '\n')
print('STAGE_REPORT', target)
