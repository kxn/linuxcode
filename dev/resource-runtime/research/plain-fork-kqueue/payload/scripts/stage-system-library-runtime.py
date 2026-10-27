#!/usr/bin/env python3
"""Clone a coherent private root with one newly linked complete libSystem."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shutil, subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-stage', required=True)
parser.add_argument('--system-build', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args(); assert re.fullmatch('[a-z0-9]+', args.tag)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
data = json.loads((root / args.parent_stage).read_text())
build = json.loads((root / args.system_build).read_text())
assert build['full_initializer_and_queue_source_build'] and build['complete_source_files'] == 20
assert sha(root / build['output']) == build['output_sha256']
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
for name, digest in data['files'].items(): resolve(name, digest)
folder = root / ('runtime/audit-session-runtime-' + args.tag)
report = root / ('artifacts/private-procfs-auditsession' + args.tag + '-stage.json')
assert not folder.exists() and not report.exists(); folder.mkdir()
previous = (root / data['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent / 'darling-root'
guest = folder / 'darling-root'
subprocess.run(['cp', '-a', '--reflink=auto', str(previous), str(guest)], check=True)
selected = {}
for key, row in data['source_runtime'].items():
    assert sha(root / row['path']) == row['sha256']
    target = folder / Path(row['path']).name; shutil.copy2(root / row['path'], target)
    name = str(target.relative_to(root)); selected[key] = dict(path=name, sha256=sha(target)); data['files'][name] = sha(target)
system = folder / 'libraries/libSystem.B.dylib'; system.parent.mkdir(); shutil.copy2(root / build['output'], system)
data['files'][str(system.relative_to(root))] = sha(system)
data.update(source_runtime=selected, system_library=str(system.relative_to(root)), system_library_sha256=sha(system),
            system_version_binding=str((guest / 'System/Library/CoreServices/SystemVersion.plist').relative_to(root)),
            mtab=str((guest / 'private/etc/mtab').relative_to(root)), runtime_execution_verified=False,
            full_goal_complete=False, system_library_parent_stage=args.parent_stage)
data['source_builds']['system'] = args.system_build
for name in [args.parent_stage, args.system_build, str(Path(__file__).relative_to(root)), data['system_version_binding']]:
    data['files'][name] = sha(root / name)
assert (root / data['mtab']).readlink() == Path(data['mtab_target'])
report.write_text(json.dumps(data, indent=2) + '\n'); print(report.relative_to(root))
