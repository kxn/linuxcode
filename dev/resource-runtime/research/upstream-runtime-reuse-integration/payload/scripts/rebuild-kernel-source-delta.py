#!/usr/bin/env python3
"""Recompile explicit changed units from an immutable complete kernel build.

Pinned repositories, recorded headers and every translation-unit source must
match the template except for the named changes. Existing objects remain in
their original directory; no prior binary or report is overwritten.
"""
from pathlib import Path
import argparse, copy, hashlib, json, runpy, shlex, subprocess

root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--template-report', required=True)
p.add_argument('--output-dir', required=True)
p.add_argument('--report', required=True)
p.add_argument('--prepare-only',action='store_true',help='Compile/verify the explicit delta and write the immutable link plan without starting native ld')
p.add_argument('--complete-prepared',action='store_true',help='Verify an existing prepared plan and link its unchanged objects with the selected common runtime')
p.add_argument('--completion-label',help='Preserve an additional completion attempt separately under this prepared build')
p.add_argument('--configuration',help='Explicit shared unified runtime for the original native linker')
p.add_argument('--private-procfs-stage',help='Validated complete cohort selected with --configuration')
p.add_argument('--changed-source', action='append', default=[])
p.add_argument('--changed-header',action='append',default=[])
p.add_argument('--recompile-group',action='append',default=[])
p.add_argument('--changed-included-source',action='append',default=[])
p.add_argument('--header-consumers-file', help='Explicit changed-header to consumer source mapping with old/new hashes and supporting evidence')
p.add_argument('--reuse-recorded-source-snapshots',action='store_true',
               help='Verify exact historical sources and sealed objects for unselected units instead of requiring their working-tree copies')
a = p.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()

def complete_prepared():
    assert not a.prepare_only and a.configuration and a.private_procfs_stage
    assert not any([a.changed_source,a.changed_header,a.recompile_group,a.changed_included_source,a.header_consumers_file])
    folder = root / a.output_dir
    assert folder.resolve().is_relative_to(root/'runtime') and folder.is_dir()
    plan_path = folder/'plan.json'; deferred_path = folder/'deferred-build.json'
    plan = json.loads(plan_path.read_text()); deferred = json.loads(deferred_path.read_text())
    assert deferred['native_link_not_executed'] and deferred['requested_report'] == a.report
    assert plan['template'] == a.template_report and sha(root/a.template_report) == plan['template_sha256']
    resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
    resolve('scripts/rebuild-kernel-source-delta.py',plan['tool_sha256'])
    d = deferred['build']; rows = deferred['updated_sources']
    assert len(rows) == d['complete_source_files'] == len(plan['objects'])
    assert len(rows) == plan['recompiled_objects'] + plan['reused_objects']
    for repo,commit in d['actual_source_repositories'].items():
        assert subprocess.check_output(['git','-C',str(root/repo),'rev-parse','HEAD'],text=True).strip() == commit,repo
    for key in ['metadata_source_headers','source_list_headers','included_source_inputs']:
        for name,digest in d.get(key,{}).items(): assert sha(root/name) == digest,name
    if plan.get('header_consumers_file'):
        assert sha(root/plan['header_consumers_file']) == plan['header_consumers_file_sha256']
    for dependencies in plan.get('compiled_consumer_dependency_sha256',{}).values():
        for name,digest in dependencies.items(): assert sha(root/name) == digest,name
    objects = []
    for row in rows:
        obj = Path(row['command'][row['command'].index('-o')+1])
        assert obj.resolve().is_relative_to(root)
        assert sha(obj) == plan['objects'][str(obj.relative_to(root))],obj
        if row['command'] in plan['compile_commands']:
            assert sha(root/row['source']) == row['sha256'],row['source']
        else:
            resolve(row['source'],row['sha256'])
        objects.append(obj)
    guest = lambda path: '/Volumes/SystemRoot/workspace/'+str(path.relative_to(root))
    assert (folder/'objects.filelist').read_text() == ''.join(guest(obj)+'\n' for obj in objects)
    output = folder/'libsystem_kernel.dylib'; report = root/a.report
    assert not output.exists() and not report.exists() and not (folder/'darling-root').exists()
    if a.completion_label:
        import re
        assert re.fullmatch('[a-z0-9-]+',a.completion_label)
        attempt = folder/('completion-'+a.completion_label)
        assert not attempt.exists()
        completion_plan = attempt/'plan.json'; completion_result = attempt/'result.json'
    else:
        attempt = folder
        completion_plan = folder/'completion-plan.json'; completion_result = folder/'completion-result.json'
    assert not completion_plan.exists() and not completion_result.exists()
    module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
    config = json.loads((root/a.configuration).read_text())
    assert config.get('runtime_mode') == 'unified' and not config.get('executables')
    profile = module['profile'](stage=a.private_procfs_stage,configuration=a.configuration)
    assert not any(value.startswith('DARLING_DYLD_OVERRIDE_') for value in profile['command'])
    linker = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld'
    assert plan['link_command'].count(linker) == 1
    arguments = plan['link_command'][plan['link_command'].index(linker):]
    assert arguments[arguments.index('-filelist')+1] == guest(folder/'objects.filelist')
    assert arguments[arguments.index('-o')+1] == guest(output)
    command = profile['command'][:-2]+arguments
    assert command[0] == 'timeout'; command[3] = '120'
    completion = dict(prepared_plan=str(plan_path.relative_to(root)),prepared_plan_sha256=sha(plan_path),
        deferred_build_sha256=sha(deferred_path),tool_sha256=sha(Path(__file__)),
        prepared_runtime_configuration=plan.get('shared_runtime_configuration'),
        prepared_runtime_configuration_sha256=plan.get('shared_runtime_configuration_sha256'),
        link_runtime_configuration=a.configuration,link_runtime_configuration_sha256=sha(root/a.configuration),
        link_private_procfs_stage=a.private_procfs_stage,link_private_procfs_stage_sha256=sha(root/a.private_procfs_stage),
        link_command=command,recompiled_during_completion=0,verified_objects=len(objects))
    if attempt != folder: attempt.mkdir()
    completion['link_log'] = str((attempt/'link.log').relative_to(root))
    completion_plan.write_text(json.dumps(completion,indent=2)+'\n')
    with (attempt/'link.log').open('w') as log:
        result = subprocess.run(command,timeout=125,stdout=log,stderr=subprocess.STDOUT,env=module['environment'](profile))
    completion['link_exit_status'] = result.returncode
    completion_result.write_text(json.dumps(completion,indent=2)+'\n')
    assert result.returncode == 0,result.returncode
    old = root/d['variant_root']
    import re,shutil
    exports = lambda binary:set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(binary)],text=True),re.M))
    assert exports(old/'usr/lib/system/libsystem_kernel.dylib') == exports(output)
    variant = folder/'darling-root'
    subprocess.run(['cp','-a','--reflink=auto',str(old),str(variant)],check=True)
    shutil.copy2(output,variant/'usr/lib/system/libsystem_kernel.dylib')
    for name in ['libquarantine.dylib','libsystem_sandbox.dylib','libdyld.dylib']:
        shutil.copy2(variant/'usr/lib/system'/name,folder/name)
    d.update(sources=rows,binary_sha256=sha(output),variant_root=str(variant.relative_to(root)),runtime_execution_verified=False,
        incremental_source_build={**plan,'completed_prepared_source_build':completion})
    report.write_text(json.dumps(d,indent=2)+'\n')
    print('KERNEL_SOURCE_DELTA_COMPLETED',a.report,'recompiled',0,'verified_objects',len(objects))

if a.complete_prepared:
    complete_prepared()
    raise SystemExit(0)
template = root / a.template_report
d = json.loads(template.read_text())
folder = root / a.output_dir
assert folder.is_relative_to(root / 'runtime') and not folder.exists()
assert not (root / a.report).exists()
for repo, commit in d['actual_source_repositories'].items():
    assert subprocess.check_output(['git', '-C', str(root / repo), 'rev-parse', 'HEAD'], text=True).strip() == commit
changed_headers=set(a.changed_header);seen_headers=set();groups=set(a.recompile_group)
consumer_input=json.loads((root/a.header_consumers_file).read_text()) if a.header_consumers_file else {}
explicit_headers=consumer_input.get('headers',{})
header_consumers=set()
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
assert not a.reuse_recorded_source_snapshots or explicit_headers or (a.changed_source and not changed_headers), 'Historical reuse requires explicit source changes or header consumer evidence'
assert a.changed_source or changed_headers, 'Specify changed sources or headers'
if explicit_headers:
    assert changed_headers==set(explicit_headers) and not groups
    assert consumer_input.get('evidence'), 'Supporting consumer/regression evidence is required'
    for name,h in consumer_input['evidence'].items():assert sha(root/resolve(name,h))==h,name
    for name,row in explicit_headers.items():
        assert sha(root/name)==row['after_sha256']
        assert sha(root/resolve(name,row['before_sha256']))==row['before_sha256']
        assert row['consumers'] and len(set(row['consumers']))==len(row['consumers'])
        header_consumers.update(row['consumers'])
        seen_headers.add(name)
elif changed_headers:
    assert groups=={'kqueue'} and all(n.startswith('vendor/darling/src/external/libkqueue/') for n in changed_headers), 'Only the closed embedded-kqueue header group is supported'
for key in ['metadata_source_headers', 'source_list_headers']:
    for name, digest in d[key].items():
        current=sha(root/name)
        if current!=digest:
            assert name in changed_headers,name
            seen_headers.add(name);d[key][name]=current
assert seen_headers==changed_headers
for name,row in explicit_headers.items():
    d['metadata_source_headers'][name]=row['after_sha256']
assert groups<={row['group'] for row in d['sources']}
changes = set(a.changed_source)
assert len(changes) == len(a.changed_source)
historical_reused_sources={}
for row in d['sources']:
    current=sha(root/row['source'])
    if current!=row['sha256'] and row['source'] not in changes:
        assert a.reuse_recorded_source_snapshots and row['source'] not in header_consumers,row['source']
        sealed=root/resolve(row['source'],row['sha256']);assert sha(sealed)==row['sha256']
        historical_reused_sources[row['source']]=dict(recorded_sha256=row['sha256'],current_sha256=current,sealed_source=str(sealed.relative_to(root)))
    if a.reuse_recorded_source_snapshots:assert sha(root/resolve(row['source'],row['sha256']))==row['sha256']
assert {row['source'] for row in d['sources'] if sha(root / row['source']) != row['sha256']} - set(historical_reused_sources) == changes
assert header_consumers <= {row['source'] for row in d['sources']}
included = set(a.changed_included_source)
included_consumers = set()
include_root = 'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/include/'
for name in included:
    assert name.startswith(include_root) and name.endswith('.c')
    spelling = '<darling/emulation/' + name[len(include_root):] + '>'
    consumers = {row['source'] for row in d['sources'] if spelling in (root / row['source']).read_text()}
    assert consumers, name
    included_consumers.update(consumers)
for name, digest in d.get('included_source_inputs', {}).items():
    if name not in included: assert sha(root / name) == digest, name
d['included_source_inputs'] = {**d.get('included_source_inputs', {}), **{name: sha(root / name) for name in included}}
folder.mkdir()
objects = []
rows = copy.deepcopy(d['sources'])
commands = []
compiled_dependencies={}
sealed_objects=d.get('incremental_source_build',{}).get('objects',{})
if a.reuse_recorded_source_snapshots:assert len(sealed_objects)==len(rows), 'Sealed template object hashes are required'
for row in rows:
    obj = Path(row['command'][row['command'].index('-o') + 1])
    assert obj.is_file(), obj
    if a.reuse_recorded_source_snapshots:assert sha(obj)==sealed_objects[str(obj.relative_to(root))],obj
    if row['source'] in changes or row['source'] in included_consumers or row['group'] in groups or row['source'] in header_consumers:
        obj = folder / obj.name
        row['command'][row['command'].index('-o') + 1] = str(obj)
        if row['source'] in header_consumers:
            dependency_file=folder/(obj.stem+'.d')
            row['command']+=['-MMD','-MF',str(dependency_file)]
        commands.append(row['command'])
        with (folder / (obj.stem + '.compile.log')).open('w') as out:
            subprocess.run(row['command'], check=True, stdout=out, stderr=subprocess.STDOUT)
        row['sha256'] = sha(root / row['source'])
        if row['source'] in header_consumers:
            dependencies={}
            for name in shlex.split(dependency_file.read_text().split(':',1)[1].replace('\\\n',' ')):
                path=Path(name).resolve();dependencies[str(path.relative_to(root)) if path.is_relative_to(root) else str(path)]=sha(path)
            compiled_dependencies[row['source']]=dependencies
            for name,hdr in explicit_headers.items():
                if row['source'] in hdr['consumers']:assert dependencies.get(name)==hdr['after_sha256'],(name,row['source'])
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
link_environment=None
if a.configuration or a.private_procfs_stage:
    assert a.configuration and a.private_procfs_stage
    configuration=json.loads((root/a.configuration).read_text())
    assert configuration.get('runtime_mode')=='unified' and 'executables' not in configuration
    module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
    profile=module['profile'](stage=a.private_procfs_stage,configuration=a.configuration)
    assert not any(value.startswith('DARLING_DYLD_OVERRIDE_') for value in profile['command'])
    cmd=profile['command'][:-2]+cmd[2:]
    cmd[3]='120'
    link_environment=module['environment'](profile)
plan = dict(template=a.template_report, template_sha256=sha(template), tool_sha256=sha(Path(__file__)), explicit_changed_sources=sorted(changes), explicit_changed_headers=sorted(changed_headers), explicit_changed_included_sources=sorted(included), direct_include_consumers_recompiled=sorted(included_consumers), complete_recompiled_groups=sorted(groups), recompiled_objects=len(commands), reused_objects=len(objects)-len(commands), compile_commands=commands, link_command=cmd, objects={str(obj.relative_to(root)): sha(obj) for obj in objects}, recorded_headers_verified=True, all_header_dependencies_recorded=False)
if a.reuse_recorded_source_snapshots:
    plan.update(historical_reused_sources=historical_reused_sources,reused_template_object_identities_verified=True)
if a.configuration:
    plan.update(shared_runtime_configuration=a.configuration,shared_runtime_configuration_sha256=sha(root/a.configuration),private_procfs_stage=a.private_procfs_stage)
if explicit_headers:
    plan.update(header_consumers_file=a.header_consumers_file,header_consumers_file_sha256=sha(root/a.header_consumers_file),
                explicit_header_consumers=explicit_headers,compiled_consumer_dependency_sha256=compiled_dependencies,
                historical_reused_sources=historical_reused_sources,reused_template_object_identities_verified=a.reuse_recorded_source_snapshots)
(folder / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
if a.prepare_only:
    (folder/'deferred-build.json').write_text(json.dumps(dict(build=d,updated_sources=rows,native_link_not_executed=True,requested_report=a.report),indent=2)+'\n')
    print('KERNEL_SOURCE_DELTA_PLAN',str((folder/'plan.json').relative_to(root)),'recompiled',len(commands),'reused',len(objects)-len(commands),'native_link_executed=False')
    raise SystemExit(0)
with (folder / 'link.log').open('w') as out:
    subprocess.run(cmd, check=True, timeout=120, stdout=out, stderr=subprocess.STDOUT,env=link_environment)
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
