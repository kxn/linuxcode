#!/usr/bin/env python3
"""Compose the private procfs server, kernel, queue and filesystem layout."""
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
parser.add_argument('--server-build', required=True)
parser.add_argument('--kernel-build', required=True)
parser.add_argument('--libsystem-build', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag.isalnum()
folder = root / ('runtime/private-procfs-' + args.tag)
report = root / ('artifacts/private-procfs-' + args.tag + '-stage.json')
assert not folder.exists() and not report.exists()
module = runpy.run_path(str(root / 'scripts/loader-environment-runtime-profile.py'))
p = module['profile'](args.parent_stage)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
server = json.loads((root / args.server_build).read_text())
kernel = json.loads((root / args.kernel_build).read_text())
system = json.loads((root / args.libsystem_build).read_text())
assert server['full_server_source_build'] and kernel['complete_source_files'] == 879
assert kernel['full_libsystem_kernel_source_build'] and system['full_initializer_and_queue_source_build']
assert sha(root / server['server']) == server['server_sha256']
kernel_path = root / kernel['variant_root'] / 'usr/lib/system/libsystem_kernel.dylib'
assert sha(kernel_path) == kernel['binary_sha256']
assert sha(root / system['output']) == system['output_sha256']
folder.mkdir()
subprocess.run(['cp', '-a', '--reflink=auto', str(root / kernel['variant_root']), str(folder / 'darling-root')], check=True)
guestroot = folder / 'darling-root'
# This is an owned, fresh directory copy. The Linux /proc outside the guest
# and all previously selected roots retain their original mounts/layout.
(guestroot / 'proc').rmdir()
private_proc = guestroot / 'private/var/db/darling/proc'
private_proc.mkdir(parents=True, exist_ok=True)
mtab = guestroot / 'private/etc/mtab'
assert mtab.is_symlink()
mtab.unlink()
mtab.symlink_to('/private/var/db/darling/proc/self/mounts')
files = {str(path.relative_to(root)): sha(path) for path in
    [Path(__file__), *[root / arg for arg in [args.parent_stage, args.server_build, args.kernel_build, args.libsystem_build]]]}
source_runtime = {}
for key, row in p['source_runtime'].items():
    source = root / server['server'] if key == 'LINUXCODE_DARLING_SERVER' else kernel_path if key == 'LINUXCODE_LIBSYSTEM_KERNEL' else root / row['path']
    target = folder / Path(row['path']).name
    shutil.copy2(source, target)
    relative = str(target.relative_to(root))
    source_runtime[key] = dict(path=relative, sha256=sha(target))
    files[relative] = sha(target)
system_path = folder / 'libraries/libSystem.B.dylib'
system_path.parent.mkdir()
shutil.copy2(root / system['output'], system_path)
for path in [kernel_path, system_path, guestroot / 'usr/lib/system/libsystem_kernel.dylib',
    guestroot / 'usr/libexec/darling/mldr', guestroot / 'usr/bin/plutil',
    guestroot / 'System/Library/CoreServices/SystemVersion.plist']:
    files[str(path.relative_to(root))] = sha(path)
data = dict(installed=False, parent_stage=args.parent_stage, previous_source_runtime=p['source_runtime'],
    source_runtime=source_runtime, files=files,
    system_library=str(system_path.relative_to(root)), system_library_sha256=sha(system_path),
    system_version_binding=str((guestroot / 'System/Library/CoreServices/SystemVersion.plist').relative_to(root)),
    private_procfs='/private/var/db/darling/proc', guest_proc_directory_present=False,
    mtab=str(mtab.relative_to(root)), mtab_target='/private/var/db/darling/proc/self/mounts',
    source_builds=dict(server=args.server_build, kernel=args.kernel_build, system=args.libsystem_build),
    runtime_execution_verified=False, full_goal_complete=False)
report.write_text(json.dumps(data, indent=2) + '\n')
print('STAGE_REPORT', report)
