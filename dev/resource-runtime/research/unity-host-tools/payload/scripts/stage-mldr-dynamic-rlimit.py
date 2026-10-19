#!/usr/bin/env python3
"""Stage a source-built loader without replacing an existing runtime variant."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True)
parser.add_argument('--tag', required=True)
parser.add_argument('--parent-profile', default='scripts/xcode-tool-dispatch-runtime-profile.py')
parser.add_argument('--diagnostic', action='store_true')
parser.add_argument('--parent-arguments-file', type=Path)
args = parser.parse_args()
assert args.tag.isalnum()
report = root / ('artifacts/mldr-dynamic-rlimit-' + args.tag + '-stage.json')
folder = root / ('runtime/mldr-dynamic-rlimit-' + args.tag)
assert not folder.exists() and not report.exists()
build_path = root / args.build
build = json.loads(build_path.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for path, value in build['files'].items():
    assert sha(root / path) == value, path
assert sha(root / build['loader']) == build['loader_sha256']
parent_path = root / args.parent_profile
parent = runpy.run_path(str(parent_path))
profile_arguments = json.loads(args.parent_arguments_file.read_text()) if args.parent_arguments_file else {}
if args.diagnostic:
    profile_arguments['diagnostic'] = True
p = parent['profile'](**profile_arguments)
base = (root / p['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent
folder.mkdir()
subprocess.run(['cp', '-a', '--reflink=auto', str(base / 'darling-root'), str(folder / 'darling-root')], check=True)
files = {str(path.relative_to(root)): sha(path) for path in [Path(__file__), parent_path, build_path]}
source_runtime = {}
for name, row in p['source_runtime'].items():
    source = root / row['path']
    assert sha(source) == row['sha256']
    target = folder / source.name
    shutil.copy2(source, target)
    relative = str(target.relative_to(root))
    files[relative] = row['sha256']
    source_runtime[name] = dict(path=relative, sha256=row['sha256'])
loader = folder / 'darling-root/usr/libexec/darling/mldr'
previous = sha(loader)
shutil.copy2(root / build['loader'], loader)
files[str(loader.relative_to(root))] = sha(loader)
record = dict(installed=False, parent_profile=str(parent_path.relative_to(root)),
    parent_profile_arguments=profile_arguments,
    previous_source_runtime=p['source_runtime'], source_runtime=source_runtime,
    previous_loader_sha256=previous, loader=str(loader.relative_to(root)), loader_sha256=sha(loader),
    build=args.build, files=files, runtime_execution_verified=False)
report.write_text(json.dumps(record, indent=2) + '\n')
print('STAGE_REPORT', report)
