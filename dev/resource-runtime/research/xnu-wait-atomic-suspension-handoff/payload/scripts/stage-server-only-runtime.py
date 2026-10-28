#!/usr/bin/env python3
"""Clone a coherent private runtime and replace only its source server."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shutil, subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-stage', required=True)
parser.add_argument('--server-build', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args(); assert re.fullmatch('[a-z0-9]+', args.tag)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
data = json.loads((root / args.parent_stage).read_text())
build = json.loads((root / args.server_build).read_text())
assert build['full_server_source_build'] and sha(root / build['server']) == build['server_sha256']
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
for name, digest in data['files'].items(): resolve(name, digest)
for row in data['source_runtime'].values(): assert sha(root / row['path']) == row['sha256']
folder = root / ('runtime/audit-session-runtime-' + args.tag)
report = root / ('artifacts/private-procfs-auditsession' + args.tag + '-stage.json')
assert not folder.exists() and not report.exists(); folder.mkdir()
old_root = (root / data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent / 'darling-root'
guest = folder / 'darling-root'
subprocess.run(['cp', '-a', '--reflink=auto', str(old_root), str(guest)], check=True)
selected = {}
for key, row in data['source_runtime'].items():
    source = root / (build['server'] if key == 'LINUXCODE_DARLING_SERVER' else row['path'])
    target = folder / Path(row['path']).name; shutil.copy2(source, target)
    name = str(target.relative_to(root)); selected[key] = dict(path=name, sha256=sha(target)); data['files'][name] = sha(target)
data['source_runtime'] = selected; data['source_builds']['server'] = args.server_build
for name in [args.parent_stage, args.server_build, str(Path(__file__).relative_to(root))]: data['files'][name] = sha(root / name)
data['system_version_binding'] = str((guest / 'System/Library/CoreServices/SystemVersion.plist').relative_to(root))
data['files'][data['system_version_binding']] = sha(root / data['system_version_binding'])
data['mtab'] = str((guest / 'private/etc/mtab').relative_to(root))
assert (root / data['mtab']).readlink() == Path(data['mtab_target'])
data.update(runtime_execution_verified=False, full_goal_complete=False, server_only_parent_stage=args.parent_stage)
report.write_text(json.dumps(data, indent=2) + '\n'); print(report.relative_to(root))
