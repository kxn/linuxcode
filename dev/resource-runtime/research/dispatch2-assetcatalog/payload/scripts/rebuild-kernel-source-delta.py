#!/usr/bin/env python3
"""Recompile explicit changed units from an immutable complete kernel build.

Pinned repositories, recorded headers and every translation-unit source must
match the template except for the named changes. Existing objects remain in
their original directory; no prior binary or report is overwritten.
"""
from pathlib import Path
import argparse, copy, hashlib, json, subprocess

root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--template-report', required=True)
p.add_argument('--output-dir', required=True)
p.add_argument('--report', required=True)
p.add_argument('--changed-source', action='append', required=True)
p.add_argument('--changed-header',action='append',default=[])
p.add_argument('--recompile-group',action='append',default=[])
a = p.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
template = root / a.template_report
d = json.loads(template.read_text())
folder = root / a.output_dir
assert folder.is_relative_to(root / 'runtime') and not folder.exists()
assert not (root / a.report).exists()
for repo, commit in d['actual_source_repositories'].items():
    assert subprocess.check_output(['git', '-C', str(root / repo), 'rev-parse', 'HEAD'], text=True).strip() == commit
changed_headers=set(a.changed_header);seen_headers=set();groups=set(a.recompile_group)
if changed_headers:
    assert groups=={'kqueue'} and all(n.startswith('vendor/darling/src/external/libkqueue/') for n in changed_headers), 'Only the closed embedded-kqueue header group is supported'
for key in ['metadata_source_headers', 'source_list_headers']:
    for name, digest in d[key].items():
        current=sha(root/name)
        if current!=digest:
            assert name in changed_headers,name
            seen_headers.add(name);d[key][name]=current
assert seen_headers==changed_headers
assert groups<={row['group'] for row in d['sources']}
changes = set(a.changed_source)
assert len(changes) == len(a.changed_source)
assert {row['source'] for row in d['sources'] if sha(root / row['source']) != row['sha256']} == changes
folder.mkdir()
objects = []
rows = copy.deepcopy(d['sources'])
commands = []
for row in rows:
    obj = Path(row['command'][row['command'].index('-o') + 1])
    assert obj.is_file(), obj
    if row['source'] in changes or row['group'] in groups:
        obj = folder / obj.name
        row['command'][row['command'].index('-o') + 1] = str(obj)
        commands.append(row['command'])
        with (folder / (obj.stem + '.compile.log')).open('w') as out:
            subprocess.run(row['command'], check=True, stdout=out, stderr=subprocess.STDOUT)
        row['sha256'] = sha(root / row['source'])
    objects.append(obj)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
filelist = folder / 'objects.filelist'
filelist.write_text(''.join(guest(obj) + '\n' for obj in objects))
output = folder / 'libsystem_kernel.dylib'
sdk = '/Volumes/SystemRoot/usr/libexec/darling'
cmd = [str(root / 'bin/darling'), 'shell', '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-bind_at_load', '-no_compact_unwind', '-install_name', '/usr/lib/system/libsystem_kernel.dylib', '-compatibility_version', '1.0.0', '-syslibroot', sdk, '-L', sdk + '/usr/lib/system', '-lsystem_c', '-lcompiler_rt', '-ldyld']
if d['experimental_direct_kevent_workqueue']:
    cmd += ['-lsystem_pthread', '-lsystem_malloc', '-lsystem_platform']
cmd += ['-filelist', guest(filelist), '-o', guest(output)]
plan = dict(template=a.template_report, template_sha256=sha(template), tool_sha256=sha(Path(__file__)), explicit_changed_sources=sorted(changes), explicit_changed_headers=sorted(changed_headers), complete_recompiled_groups=sorted(groups), recompiled_objects=len(commands), reused_objects=len(objects)-len(commands), compile_commands=commands, link_command=cmd, objects={str(obj.relative_to(root)): sha(obj) for obj in objects}, recorded_headers_verified=True, all_header_dependencies_recorded=False)
(folder / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
with (folder / 'link.log').open('w') as out:
    subprocess.run(cmd, check=True, timeout=120, stdout=out, stderr=subprocess.STDOUT)
old = root / d['variant_root']
variant = folder / 'darling-root'
subprocess.run(['cp', '-a', '--reflink=auto', str(old), str(variant)], check=True)
import shutil
shutil.copy2(output, variant / 'usr/lib/system/libsystem_kernel.dylib')
for name in ['libquarantine.dylib', 'libsystem_sandbox.dylib', 'libdyld.dylib']:
    shutil.copy2(variant / 'usr/lib/system' / name, folder / name)
d.update(sources=rows, binary_sha256=sha(output), variant_root=str(variant.relative_to(root)), runtime_execution_verified=False, incremental_source_build=plan)
(root / a.report).write_text(json.dumps(d, indent=2) + '\n')
print('KERNEL_SOURCE_DELTA', a.report, 'recompiled', len(commands), 'reused', len(objects)-len(commands))
