#!/usr/bin/env python3
"""Compose an immutable private runtime and graphics stage with one XPC singleton."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-stage', required=True)
parser.add_argument('--libxpc-build', required=True)
parser.add_argument('--graphics-parent', required=True)
parser.add_argument('--adapter-report', required=True)
parser.add_argument('--runtime-tag', required=True)
parser.add_argument('--graphics-tag', required=True)
args = parser.parse_args()
assert args.runtime_tag.isalnum() and args.graphics_tag.isalnum()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
read = lambda path: json.loads((root/path).read_text())
resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
parent = read(args.parent_stage)
graphics = read(args.graphics_parent)
source = read(args.libxpc_build)
adapter = read(args.adapter_report)
for report in [parent, graphics]:
    for name, digest in report['files'].items():
        resolve(name, digest)
    for name, target in report.get('links', {}).items():
        assert os.readlink(root/name) == target
assert source['full_libxpc_source_build'] and adapter['source_peer_error_build'] == args.libxpc_build
assert not adapter['source_peer_singleton_owned_by_adapter']
assert adapter['existing_provider_reexport']['added_dependency_edges'] == 0
for relative, digest in {**source['source_files'], **source['modified_files']}.items():
    assert sha('vendor/darling/src/external/libxpc/'+relative) == digest
xpc = str(Path(source['variant_root'])/'usr/lib/system/libxpc.dylib')
assert sha(xpc) == source['library_sha256'] == adapter['source_peer_error_sha256']
assert sha(adapter['output']) == adapter['library_sha256']
runtime_folder = Path('runtime/private-procfs-'+args.runtime_tag)
runtime_report = Path('artifacts/private-procfs-'+args.runtime_tag+'-stage.json')
graphics_folder = Path('runtime/coregraphics-native-'+args.graphics_tag)
graphics_report = Path('artifacts/coregraphics-native-'+args.graphics_tag+'-stage.json')
for name in [runtime_folder, runtime_report, graphics_folder, graphics_report]:
    assert not (root/name).exists()
old_runtime = Path(parent['source_runtime']['LINUXCODE_LIBXPC']['path']).parent
assert str(old_runtime).startswith('runtime/private-procfs-')
subprocess.run(['cp', '-a', '--reflink=auto', str(root/old_runtime), str(root/runtime_folder)], check=True)
def remap(name, old, new):
    path = Path(name)
    return str(new/path.relative_to(old)) if path.is_relative_to(old) else name
runtime = dict(parent, source_runtime={key: dict(row, path=remap(row['path'], old_runtime, runtime_folder))
    for key, row in parent['source_runtime'].items()},
    files={remap(name, old_runtime, runtime_folder): digest for name, digest in parent['files'].items()},
    runtime_execution_verified=False, full_goal_complete=False)
for key in ['mtab', 'system_library', 'system_version_binding']:
    runtime[key] = remap(parent[key], old_runtime, runtime_folder)
for name in [runtime['source_runtime']['LINUXCODE_LIBXPC']['path'],
             str(runtime_folder/'darling-root/usr/lib/system/libxpc.dylib')]:
    shutil.copy2(root/xpc, root/name)
    runtime['files'][name] = sha(name)
runtime['source_runtime']['LINUXCODE_LIBXPC']['sha256'] = source['library_sha256']
# Pair the adapter for ordinary clients as well as resource-tool children.
# Selecting only the graphics copy leaves normal clients with the old,
# separately allocated singleton despite the new backend export.
for name in [runtime_folder/'libraries/libDarlingXPCRichError.dylib',
             runtime_folder/'darling-root/usr/lib/libDarlingXPCRichError.dylib']:
    if (root/name).exists():
        original = old_runtime/name.relative_to(runtime_folder)
        assert not (root/name).is_symlink() and sha(str(name)) == parent['files'][str(original)]
    shutil.copy2(root/adapter['output'], root/name)
    runtime['files'][str(name)] = sha(str(name))
runtime['peer_error_adapter'] = dict(path=str(runtime_folder/'libraries/libDarlingXPCRichError.dylib'),
    sha256=adapter['library_sha256'])
runtime['source_builds'] = dict(parent['source_builds'], libxpc=args.libxpc_build)
runtime['parent_private_stage'] = args.parent_stage
old_graphics = Path(graphics['library']).parents[4]
shutil.copytree(root/old_graphics, root/graphics_folder, symlinks=True)
destination = graphics_folder/'libraries/libDarlingXPCRichError.dylib'
if (root/destination).exists():
    original = old_graphics/'libraries/libDarlingXPCRichError.dylib'
    assert not (root/destination).is_symlink() and sha(str(destination)) == graphics['files'][str(original)]
shutil.copy2(root/adapter['output'], root/destination)
new_graphics = dict(graphics, library=remap(graphics['library'], old_graphics, graphics_folder),
    parent_stage=args.graphics_parent, parent_stage_sha256=sha(args.graphics_parent),
    installed=False, runtime_execution_verified=False, resource_compilation_verified=False,
    dependencies=[*[row for row in graphics['dependencies'] if row['target'] != 'source-peer-error-adapter'], dict(target='source-peer-error-adapter',
        source=adapter['output'], reconstruction=args.adapter_report)], files=dict(graphics['files']))
new_graphics['files'].update({str(p.relative_to(root)): sha(str(p.relative_to(root)))
    for p in (root/graphics_folder).rglob('*') if p.is_file() and not p.is_symlink()})
new_graphics['links'] = dict(graphics.get('links', {}), **{str(p.relative_to(root)): os.readlink(p)
    for p in (root/graphics_folder).rglob('*') if p.is_symlink()})
for report in [runtime, new_graphics]:
    for name in [args.parent_stage, args.graphics_parent, args.libxpc_build, args.adapter_report,
                 str(Path(__file__).relative_to(root))]:
        report['files'][name] = sha(name)
(root/runtime_report).write_text(json.dumps(runtime, indent=2)+'\n')
(root/graphics_report).write_text(json.dumps(new_graphics, indent=2)+'\n')
print(runtime_report)
print(graphics_report)
