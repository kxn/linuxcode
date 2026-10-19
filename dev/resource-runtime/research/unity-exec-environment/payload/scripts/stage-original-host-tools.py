#!/usr/bin/env python3
"""Install pinned original command-line tools into a fresh private runtime root."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-stage', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag.isalnum()
folder = root / ('runtime/original-host-tools-' + args.tag)
report = root / ('artifacts/original-host-tools-' + args.tag + '-stage.json')
assert not folder.exists() and not report.exists()
parent = json.loads((root / args.parent_stage).read_text())
assert parent['parent_profile'] == 'scripts/libsystem-kqueue-runtime-profile.py'
p = runpy.run_path(str(root / 'scripts/loader-environment-runtime-profile.py'))['profile'](args.parent_stage)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
config_path = root / 'config/original-host-tools.json'
config = json.loads(config_path.read_text())
for row in config['tools']:
    source = root / row['source']
    assert sha(source) == row['sha256']
    assert source.read_bytes()[:8] == bytes.fromhex('cffaedfe07000001')
folder.mkdir()
base = (root / p['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent
subprocess.run(['cp', '-a', '--reflink=auto', str(base / 'darling-root'), str(folder / 'darling-root')], check=True)
files = {str(path.relative_to(root)): sha(path) for path in [Path(__file__), root / args.parent_stage, config_path]}
source_runtime = {}
for key, row in p['source_runtime'].items():
    source = root / row['path']
    assert sha(source) == row['sha256']
    target = folder / source.name
    shutil.copy2(source, target)
    relative = str(target.relative_to(root))
    source_runtime[key] = dict(path=relative, sha256=sha(target))
    files[relative] = sha(target)
tools = []
for row in config['tools']:
    target = folder / 'darling-root' / row['install_path'].lstrip('/')
    assert not target.exists(), row['install_path']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / row['source'], target)
    target.chmod(0o755)
    assert sha(target) == row['sha256']
    relative = str(target.relative_to(root))
    files[relative] = sha(target)
    tools.append({**row, 'installed': relative, 'original_bytes_preserved': True})
for name in ['usr/lib/system/libsystem_kernel.dylib', 'usr/libexec/darling/mldr', 'System/Library/CoreServices/SystemVersion.plist']:
    target = folder / 'darling-root' / name
    files[str(target.relative_to(root))] = sha(target)
data = dict(installed=False, parent_profile=parent['parent_profile'],
    parent_profile_arguments=parent['parent_profile_arguments'],
    previous_source_runtime=parent['previous_source_runtime'], source_runtime=source_runtime,
    files=files, parent_stage=args.parent_stage, original_tools=tools,
    runtime_execution_verified=False, full_goal_complete=False)
report.write_text(json.dumps(data, indent=2) + '\n')
print('STAGE_REPORT', report)
