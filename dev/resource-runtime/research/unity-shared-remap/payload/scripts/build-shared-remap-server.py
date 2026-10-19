#!/usr/bin/env python3
"""Build a private Darling server for segmented shared remapping."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import runpy
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-stage', default='artifacts/mldr-dynamic-rlimit-v3-stage.json')
args = parser.parse_args()
parent = runpy.run_path(str(root / 'scripts/mldr-dynamic-rlimit-profile.py'))
p = parent['profile'](stage=args.parent_stage)
folder = Path(tempfile.mkdtemp(prefix='shared-remap-server-', dir=root / 'runtime'))
build = root / 'runtime/darlingserver-source-build'
baseline = build / 'darlingserver/darlingserver'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before = sha(baseline)
assert before == 'ae78babd377dd542788f321752b11e9dea6413ee49d1009f00df825fdd9efd6b'
backup = folder / 'baseline-build-output'
command = ['cmake', '--build', str(build), '--target', 'darlingserver', '-j', '8']
# Existing variants use copied executables. Still serialize the shared build
# output so a concurrent runtime cannot observe its temporary replacement.
with (root / 'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    shutil.copy2(baseline, backup)
    try:
        baseline.unlink()
        with (folder / 'build.log').open('w') as stream:
            subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT, check=True)
        shutil.copy2(baseline, folder / 'darlingserver')
    finally:
        replacement = folder / 'baseline.restore'
        shutil.copy2(backup, replacement)
        replacement.replace(baseline)
assert sha(baseline) == before
repo = root / 'vendor/darlingserver'
names = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-co', '--exclude-standard', '-z'], text=True).split('\0')
inputs = {str((repo / name).relative_to(root)): sha(repo / name)
    for name in names if name and (repo / name).is_file()}
source_runtime = {key: dict(value) for key, value in p['source_runtime'].items()}
source_runtime['LINUXCODE_DARLING_SERVER'] = dict(path=str((folder / 'darlingserver').relative_to(root)), sha256=sha(folder / 'darlingserver'))
record = dict(full_server_source_build=True, installed=False, baseline_build_output_restored=True,
    baseline_build_output_sha256=before, command=command, parent_stage=args.parent_stage,
    previous_source_runtime=p['source_runtime'], source_runtime=source_runtime,
    server=str((folder / 'darlingserver').relative_to(root)), server_sha256=sha(folder / 'darlingserver'),
    source_files=inputs, files={str(path.relative_to(root)): sha(path) for path in
        [Path(__file__), root / args.parent_stage, folder / 'build.log']},
    runtime_execution_verified=False, full_goal_complete=False)
(folder / 'stage.json').write_text(json.dumps(record, indent=2) + '\n')
print('STAGE_REPORT', folder / 'stage.json', flush=True)
