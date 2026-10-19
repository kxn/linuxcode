#!/usr/bin/env python3
"""Combine the remap server and RPC receive fix in one coherent private root."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--server-stage', required=True)
parser.add_argument('--kernel-build', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag.isalnum()
folder = root / ('runtime/shared-remap-runtime-' + args.tag)
report = root / ('artifacts/shared-remap-runtime-' + args.tag + '-stage.json')
assert not folder.exists() and not report.exists()
server = json.loads((root / args.server_stage).read_text())
kernel = json.loads((root / args.kernel_build).read_text())
assert kernel['full_libsystem_kernel_source_build'] and kernel['complete_source_files'] == 879
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
base = root / kernel['variant_root']
library = base / 'usr/lib/system/libsystem_kernel.dylib'
assert sha(library) == kernel['binary_sha256']
parent = runpy.run_path(str(root / 'scripts/shared-remap-runtime-profile.py'))
p = parent['profile'](stage=args.server_stage)
folder.mkdir()
subprocess.run(['cp', '-a', '--reflink=auto', str(base), str(folder / 'darling-root')], check=True)
source_runtime, files = {}, {}
for key, row in p['source_runtime'].items():
    source = library if key == 'LINUXCODE_LIBSYSTEM_KERNEL' else root / row['path']
    assert key == 'LINUXCODE_LIBSYSTEM_KERNEL' or sha(source) == row['sha256']
    target = folder / source.name
    shutil.copy2(source, target)
    relative = str(target.relative_to(root))
    source_runtime[key] = dict(path=relative, sha256=sha(target))
    files[relative] = sha(target)
version = folder / 'darling-root/System/Library/CoreServices/SystemVersion.plist'
for path in [Path(__file__), root / args.server_stage, root / args.kernel_build,
             version, folder / 'darling-root/usr/lib/system/libsystem_kernel.dylib',
             folder / 'darling-root/usr/libexec/darling/mldr',
             root / 'vendor/darlingserver/duct-tape/src/memory.c',
             root / 'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/include/linux_premigration/resources/dserver-rpc-defs.h']:
    files[str(path.relative_to(root))] = sha(path)
record = dict(installed=False, parent_stage=server['parent_stage'],
    previous_source_runtime=server['previous_source_runtime'], source_runtime=source_runtime,
    system_version_binding=str(version.relative_to(root)), files=files,
    server_stage=args.server_stage, kernel_build=args.kernel_build,
    runtime_execution_verified=False, full_goal_complete=False)
report.write_text(json.dumps(record, indent=2) + '\n')
print('STAGE_REPORT', report)
