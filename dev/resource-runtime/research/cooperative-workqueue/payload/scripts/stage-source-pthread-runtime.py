#!/usr/bin/env python3
"""Compose a private source-pthread variant with the existing coherent backend."""
from pathlib import Path
import argparse, hashlib, json, runpy, shutil, subprocess
root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-stage', required=True)
p.add_argument('--pthread-build', required=True)
p.add_argument('--tag', required=True)
a = p.parse_args()
assert a.tag.isalnum()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
parent = json.loads((root / a.parent_stage).read_text())
build = json.loads((root / a.pthread_build).read_text())
assert build['full_libpthread_source_build'] and build['complete_source_files'] == 13
assert sha(root / build['binary']) == build['binary_sha256']
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
for name, digest in parent['files'].items():
    resolve(name, digest)
folder = root / ('runtime/source-pthread-runtime-' + a.tag)
report = root / ('artifacts/private-procfs-source-pthread-' + a.tag + '-stage.json')
assert not folder.exists() and not report.exists()
folder.mkdir()
guest = folder / 'darling-root'
subprocess.run(['cp', '-a', '--reflink=auto', str(root / build['variant_root']), str(guest)], check=True)
for key, item in parent['source_runtime'].items():
    target = folder / Path(item['path']).name
    shutil.copy2(root / item['path'], target)
    name = str(target.relative_to(root))
    parent['source_runtime'][key] = dict(path=name, sha256=sha(target))
    parent['files'][name] = sha(target)
    if target.suffix == '.dylib':
        dest = guest / 'usr/lib/system' / target.name
        assert sha(dest) == sha(target), 'Kernel/pthread variant must share the selected source backend'
parent['system_version_binding'] = str((guest / 'System/Library/CoreServices/SystemVersion.plist').relative_to(root))
parent['mtab'] = str((guest / 'private/etc/mtab').relative_to(root))
for path in [Path(__file__), root / a.pthread_build, guest / 'usr/lib/system/libsystem_pthread.dylib',
             root / parent['system_version_binding']]:
    parent['files'][str(path.relative_to(root))] = sha(path)
parent['source_builds']['pthread'] = a.pthread_build
parent['source_pthread_build'] = a.pthread_build
parent['runtime_execution_verified'] = False
parent['full_goal_complete'] = False
report.write_text(json.dumps(parent, indent=2) + '\n')
print(report.relative_to(root))
