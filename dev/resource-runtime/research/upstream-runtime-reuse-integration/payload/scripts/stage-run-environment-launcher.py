#!/usr/bin/env python3
"""Stage shared runtime paths before the first Mach-O process is created.

Reuse an existing namespace launcher and its mounts. Every clean environment
receives one run-level payload, including the initial server/launchd bootstrap.
The original stage and configuration are left unchanged; nothing is launched.
"""
from pathlib import Path, PurePosixPath
import argparse,hashlib,json,os,re,runpy,shutil,subprocess,tempfile

root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-stage')
p.add_argument('--clone-image-stage',help='Clone an already materialized common image without reinstalling its providers')
p.add_argument('--host-resolver',default='/etc/resolv.conf',help='Host resolver configuration snapshotted for Linux and Darwin before bootstrap')
p.add_argument('--source-library-build',action='append',default=[],help='Preinstall an existing complete source-library report and its aliases in the shared image')
p.add_argument('--runtime-stage',help='Materialize a matching full system root and independent writable prefix before bootstrap')
p.add_argument('--shared-profile-input',help='Unified profile metadata used only to resolve shared Developer/Apple provider inputs')
p.add_argument('--preinstall-common-security',action='store_true',help='Install the public Security framework and its common identity store into the shared image')
p.add_argument('--service-cohort',help='Pinned common account and service files preinstalled in both trees before the first Mach-O')
p.add_argument('--dyld-build',help='Source loader build preinstalled for every process in the shared image')
a=p.parse_args()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
log_transport='''if [[ -n ${LINUXCODE_RUN_DARLING_OS_LOG_STDERR+x} ]]; then
    [[ $LINUXCODE_RUN_DARLING_OS_LOG_STDERR == 0 || $LINUXCODE_RUN_DARLING_OS_LOG_STDERR == 1 ]] || {
        echo "LINUXCODE_RUN_DARLING_OS_LOG_STDERR must be 0 or 1" >&2; exit 2;
    }
    run_environment+=("DARLING_OS_LOG_STDERR=$LINUXCODE_RUN_DARLING_OS_LOG_STDERR")
fi
'''
def optional_log_transport(text):
    if 'LINUXCODE_RUN_DARLING_OS_LOG_STDERR' in text:return text
    anchor='''if [[ -n ${LINUXCODE_RUN_OBJC_DISABLE_TAGGED_POINTERS+x} ]]; then
    run_environment+=("OBJC_DISABLE_TAGGED_POINTERS=$LINUXCODE_RUN_OBJC_DISABLE_TAGGED_POINTERS")
fi
'''
    assert text.count(anchor)==1
    return text.replace(anchor,anchor+log_transport,1)

def install_host_resolver(folder,system,prefix,text):
    source=Path(a.host_resolver).resolve(strict=True);data=source.read_bytes()
    assert source.is_file() and len(data)<=1024*1024 and b'\0' not in data
    snapshot=folder/'resolv.conf';snapshot.write_bytes(data);snapshot.chmod(0o444)
    for tree in [system,prefix]:
        destination=tree/'private/etc/resolv.conf'
        assert destination.parent.resolve().is_relative_to(tree.resolve())
        if destination.exists() or destination.is_symlink():
            assert not destination.is_dir();destination.unlink()
        destination.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        destination.write_bytes(data);destination.chmod(0o444)
        assert sha(destination)==sha(snapshot)
    assert (system/'etc').is_symlink() and os.readlink(system/'etc')=='private/etc'
    assert not (prefix/'etc').exists() or ((prefix/'etc').is_symlink() and os.readlink(prefix/'etc')=='private/etc')
    anchor='mount --bind "$project/runtime/home" "$rootfs/root"\n'
    assert text.count(anchor)==1
    relative=str(snapshot.relative_to(root))
    block=f'''# Linux native code and the Darwin image use one host resolver snapshot.
[[ -f "$rootfs/etc/resolv.conf" && ! -L "$rootfs/etc/resolv.conf" ]] || exit 2
mount --bind "$project/{relative}" "$rootfs/etc/resolv.conf"
mount -o remount,bind,ro "$rootfs/etc/resolv.conf"
'''
    # A cloned namespace already contains its parent's resolver block. Replace
    # that block rather than adding another bind each time the image is cloned.
    pattern=r'# Linux native code and the Darwin image use one host resolver snapshot\.\n\[\[ -f "\$rootfs/etc/resolv\.conf" && ! -L "\$rootfs/etc/resolv\.conf" \]\] \|\| exit 2\nmount --bind "\$project/[^"\n]+" "\$rootfs/etc/resolv\.conf"\nmount -o remount,bind,ro "\$rootfs/etc/resolv\.conf"\n'
    text=re.sub(pattern,'',text)
    text=text.replace(anchor,block+anchor,1)
    return text,dict(host_source=a.host_resolver,resolved_host_source=str(source),source_sha256=sha(snapshot),
        snapshot=relative,namespace_read_only_mount='/etc/resolv.conf',
        Darwin_effective_path='/etc/resolv.conf',Darwin_canonical_path='/private/etc/resolv.conf',
        installed_in_system_and_prefix=True,before_first_Mach_O=True,shared_network_namespace=True)

def install_source_libraries(system,prefix):
    records=[];inputs={}
    resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
    for name in a.source_library_build:
        report_path=root/name;report=json.loads(report_path.read_text())
        assert any(value is True for key,value in report.items() if key.startswith('full_') and key.endswith('_source_build'))
        assert report['complete_source_files']==len(report['sources'])>0 and report['baseline_exports_preserved']>0
        assert not report.get('missing_original_exports',[])
        for row in report['sources']:resolve(row['source'],row['sha256'])
        for source,digest in {**report['source_headers'],**report['files']}.items():resolve(source,digest)
        library=(root/report['library']).resolve(strict=True)
        assert library.is_relative_to(root/'runtime') and sha(library)==report['library_sha256']
        output=subprocess.check_output(['llvm-objdump-19','--macho','--dylib-id',str(library)],text=True)
        names=[line.strip() for line in output.splitlines() if line.strip().startswith('/') and not line.strip().endswith(':')]
        assert len(names)==1;canonical=PurePosixPath(names[0])
        assert canonical.is_absolute() and '..' not in canonical.parts and str(canonical).startswith('/usr/lib/')
        assert canonical.name==library.name
        aliases=[path for path in library.parent.iterdir() if path.is_symlink() and path.resolve(strict=True)==library]
        for tree in [system,prefix]:
            destination=tree/str(canonical).lstrip('/');assert destination.parent.resolve().is_relative_to(tree.resolve())
            destination.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
            if destination.exists() or destination.is_symlink():assert not destination.is_dir();destination.unlink()
            shutil.copy2(library,destination);assert sha(destination)==report['library_sha256']
            for alias in aliases:
                target=destination.parent/alias.name
                if target.exists() or target.is_symlink():assert not target.is_dir();target.unlink()
                target.symlink_to(destination.name)
        inputs[name]=sha(report_path);inputs[report['library']]=report['library_sha256']
        records.append(dict(build=name,build_sha256=sha(report_path),canonical_path=str(canonical),
            library_sha256=report['library_sha256'],aliases=[str(canonical.parent/path.name) for path in aliases],
            complete_source_files=report['complete_source_files'],recompiled=False,installed_in_system_and_prefix=True))
    return records,inputs

if a.clone_image_stage:
    assert not any([a.parent_stage,a.preinstall_common_security,a.dyld_build])
    parent_path=root/a.clone_image_stage;stage=json.loads(parent_path.read_text())
    resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
    for name,digest in stage['files'].items():resolve(name,digest)
    image=stage['materialized_shared_runtime'];assert image['all_provider_bytes_installed_before_first_Darling']
    old_folder=(root/stage['namespace']).parent
    folder=Path(tempfile.mkdtemp(prefix='run-environment-launcher-',dir=root/'runtime'))
    system=folder/'darling-root';prefix=folder/'prefix';(folder/'prefix.workdir').mkdir()
    for name,target in [('whole_system_root',system),('shared_prefix',prefix)]:
        subprocess.run(['cp','-a','--reflink=always','--no-preserve=links',str(root/image[name]),str(target)],check=True)
    removed=[]
    for name in ['.init.pid','.darlingserver.sock','.shellspawn.sock','private/var/run/shellspawn.sock']:
        path=prefix/name
        if path.exists() or path.is_symlink():assert not path.is_dir();path.unlink();removed.append(name)
    for path in prefix.iterdir():
        if re.fullmatch(r'core(?:\.\d+)?',path.name) and path.is_file() and not path.is_symlink():path.unlink()
    namespace=folder/'runtime-ns.sh';launcher=folder/'darling'
    if a.runtime_stage:
        runtime_path=root/a.runtime_stage;runtime=json.loads(runtime_path.read_text())
        previous_runtime=json.loads((root/image['runtime_stage']).read_text())
        assert set(runtime['source_runtime'])==set(previous_runtime['source_runtime'])
        for name,digest in runtime['files'].items():resolve(name,digest)
        core={'LINUXCODE_LIBXPC':'usr/lib/system/libxpc.dylib','LINUXCODE_LAUNCHD':'sbin/launchd',
              'LINUXCODE_LIBSYSTEM_KERNEL':'usr/lib/system/libsystem_kernel.dylib',
              'LINUXCODE_QUARANTINE':'usr/lib/system/libquarantine.dylib',
              'LINUXCODE_SANDBOX':'usr/lib/system/libsystem_sandbox.dylib','LINUXCODE_LIBDYLD':'usr/lib/system/libdyld.dylib'}
        updates={}
        for key,row in runtime['source_runtime'].items():
            source=(root/row['path']).resolve(strict=True)
            assert source.is_relative_to(root/'runtime') and sha(source)==row['sha256']
            stage['files'][row['path']]=row['sha256']
            if key in core:
                target=core[key]
                for tree in [system,prefix]:
                    destination=tree/target;assert destination.parent.resolve().is_relative_to(tree.resolve())
                    assert destination.is_file() and not destination.is_symlink()
                    if sha(destination)!=row['sha256']:destination.unlink();shutil.copy2(source,destination)
                    assert sha(destination)==row['sha256']
                image['providers'][target]=dict(source=row['path'],files={'.':dict(sha256=row['sha256'])})
            if row['sha256']!=previous_runtime['source_runtime'][key]['sha256']:
                updates[key]=dict(before_sha256=previous_runtime['source_runtime'][key]['sha256'],**row)
        image.update(runtime_stage=a.runtime_stage,runtime_stage_sha256=sha(runtime_path),cloned_runtime_updates=updates)
        stage['files'][a.runtime_stage]=sha(runtime_path)
    library_updates,library_inputs=install_source_libraries(system,prefix)
    if a.service_cohort:
        cohort_path=root/a.service_cohort;cohort=json.loads(cohort_path.read_text())
        assert cohort['host_verified'] and not cohort['installed']
        for name,digest in cohort.get('input_evidence',{}).items():
            resolve(name,digest);stage['files'][name]=digest
        rows={row['destination']:row for category in ['prefix_files','system_files'] for row in cohort[category]}
        assert len(rows)==sum(len(cohort[category]) for category in ['prefix_files','system_files'])
        changed=cohort['clone_delta_files'];provider_changes=cohort.get('clone_delta_runtime_providers',[])
        assert (changed or provider_changes) and len(set(changed))==len(changed)
        assert len(set(provider_changes))==len(provider_changes)
        previous=image['service_cohort']['files']
        assert set(rows)==set(previous), 'Cloning a service cohort must preserve all account and service entries'
        assert {name for name,row in rows.items() if previous.get(name,{}).get('sha256')!=row['sha256']}==set(changed)
        for name in changed:
            relative=PurePosixPath(name);assert not relative.is_absolute() and name==relative.as_posix()
            assert all(part not in ('','.', '..') for part in name.split('/'))
            row=rows[name];source=(root/row['source']).resolve(strict=True)
            assert source.is_relative_to(root/'runtime') and source.is_file() and not (root/row['source']).is_symlink()
            assert sha(source)==row['sha256'] and not source.stat().st_mode & 0o7000
            for tree in [system,prefix]:
                destination=tree/name;assert destination.parent.resolve().is_relative_to(tree.resolve())
                assert destination.parent.is_dir() and not destination.is_dir()
                if destination.exists() or destination.is_symlink():destination.unlink()
                shutil.copy2(source,destination);assert sha(destination)==row['sha256']
            previous[name]=dict(source=row['source'],sha256=row['sha256'],installed_in_system_and_prefix=True,
                mode=oct(source.stat().st_mode & 0o777),
                original_Apple_service_or_plist=row['original_Apple_service_or_plist'])
            stage['files'][row['source']]=row['sha256']
        providers={row['destination']:row for row in cohort.get('runtime_providers',[])}
        assert set(provider_changes)<=set(providers)
        for name in provider_changes:
            relative=PurePosixPath(name);assert not relative.is_absolute() and name==relative.as_posix()
            assert all(part not in ('','.', '..') for part in name.split('/'))
            row=providers[name];source=(root/row['source']).resolve(strict=True)
            assert source.is_relative_to(root/'runtime') and not (root/row['source']).is_symlink()
            actual={}
            paths=source.rglob('*') if source.is_dir() else [source]
            for path in paths:
                key=str(path.relative_to(source)) if source.is_dir() else '.'
                if path.is_symlink():
                    assert path.resolve(strict=True).is_relative_to(source.resolve())
                    actual[key]=dict(symlink=os.readlink(path))
                elif path.is_file():
                    assert not path.stat().st_mode & 0o7000
                    actual[key]=dict(sha256=sha(path));stage['files'][str(path.relative_to(root))]=sha(path)
            assert actual==row['files'],name
            for tree in [system,prefix]:
                destination=tree/name
                assert destination.parent.resolve().is_relative_to(tree.resolve()) and destination.parent.is_dir()
                if destination.is_symlink() or destination.is_file():destination.unlink()
                elif destination.is_dir():shutil.rmtree(destination)
                if source.is_dir():shutil.copytree(source,destination,symlinks=True,copy_function=shutil.copy2)
                else:shutil.copy2(source,destination)
            image['providers'][name]=dict(source=row['source'],files=actual)
        image['service_cohort'].update(manifest=a.service_cohort,manifest_sha256=sha(cohort_path),
            cloned_service_delta_files=changed,cloned_runtime_provider_delta_files=provider_changes,
            runtime_provider_destinations=list(providers),modified_services_claim_original_Apple_signature=False)
        stage['files'][a.service_cohort]=sha(cohort_path)
    if a.shared_profile_input:
        shared_path=root/a.shared_profile_input;shared=json.loads(shared_path.read_text())
        assert shared['direct_resource_environment']['runtime_mode']=='unified'
        assert shared['source_runtime']==json.loads((root/image['runtime_stage']).read_text())['source_runtime']
        image.update(shared_profile_input=a.shared_profile_input,shared_profile_input_sha256=sha(shared_path))
        stage['files'][a.shared_profile_input]=sha(shared_path)
    text=(root/stage['namespace']).read_text().replace(str(old_folder.relative_to(root)),str(folder.relative_to(root)))
    text=optional_log_transport(text);text,resolver=install_host_resolver(folder,system,prefix,text)
    namespace.write_text(text)
    launcher.write_text((root/stage['launcher']).read_text().replace(stage['namespace'],str(namespace.relative_to(root))))
    for path in [launcher,namespace]:path.chmod(0o755);subprocess.run(['bash','-n',str(path)],check=True)
    image.update(whole_system_root=str(system.relative_to(root)),shared_prefix=str(prefix.relative_to(root)),
        private_workdir=str((folder/'prefix.workdir').relative_to(root)),shared_state_mount=str(folder.relative_to(root)),
        global_host_resolver=resolver,cloned_installed_image=a.clone_image_stage,
        cloned_installed_image_sha256=sha(parent_path),removed_cloned_session_IPC=removed)
    if library_updates:image['common_source_library_updates']=library_updates
    stage['files'].update(library_inputs)
    stage.update(launcher=str(launcher.relative_to(root)),namespace=str(namespace.relative_to(root)),
        runtime_execution_verified=False,full_goal_complete=False,cloned_installed_image=a.clone_image_stage,
        cloned_installed_image_sha256=sha(parent_path),optional_run_log_transport='LINUXCODE_RUN_DARLING_OS_LOG_STDERR')
    for path in [Path(__file__),parent_path,launcher,namespace,folder/'resolv.conf']:stage['files'][str(path.relative_to(root))]=sha(path)
    out=folder/'stage.json';out.write_text(json.dumps(stage,indent=2)+'\n');print('RUN_ENVIRONMENT_STAGE',out,flush=True)
    raise SystemExit(0)
assert a.parent_stage
cohort_path=None;cohort_rows=[];cohort_providers=[]
if a.service_cohort:
    assert a.runtime_stage and a.shared_profile_input
    cohort_path=(root/a.service_cohort).resolve(strict=True)
    assert cohort_path.is_relative_to(root/'runtime') and cohort_path.is_file()
    cohort=json.loads(cohort_path.read_text());assert cohort['host_verified'] and not cohort['installed']
    seen=set()
    for category in ['prefix_files','system_files']:
        for item in cohort[category]:
            name=item['destination'];relative=PurePosixPath(name)
            assert name and not relative.is_absolute() and name==relative.as_posix()
            assert all(part not in ('','.', '..') for part in name.split('/'))
            assert name not in seen;seen.add(name)
            spelling=PurePosixPath(item['source'])
            assert not spelling.is_absolute() and '..' not in spelling.parts
            source=(root/item['source']).resolve(strict=True)
            assert source.is_relative_to(root/'runtime') and source.is_file() and not (root/item['source']).is_symlink()
            assert sha(source)==item['sha256'],item['source']
            assert not source.stat().st_mode & 0o7000
            cohort_rows.append((name,source,item['sha256']))
    for item in cohort.get('runtime_providers',[]):
        name=item['destination'];relative=PurePosixPath(name)
        assert name and not relative.is_absolute() and name==relative.as_posix()
        assert all(part not in ('','.', '..') for part in name.split('/'))
        assert name not in seen;seen.add(name)
        spelling=PurePosixPath(item['source'])
        assert not spelling.is_absolute() and '..' not in spelling.parts
        source=(root/item['source']).resolve(strict=True)
        assert source.is_relative_to(root/'runtime') and not (root/item['source']).is_symlink()
        files={}
        for path in (source.rglob('*') if source.is_dir() else [source]):
            key=str(path.relative_to(source)) if source.is_dir() else '.'
            if path.is_symlink():
                target=os.readlink(path)
                assert not PurePosixPath(target).is_absolute()
                assert path.resolve(strict=True).is_relative_to(source)
                files[key]=dict(symlink=target)
            elif path.is_file():
                assert not path.stat().st_mode & 0o7000
                files[key]=dict(sha256=sha(path))
        assert files and files==item['files'],name
        cohort_providers.append((name,source))
    if cohort.get('common_security_build'):
        build_name=PurePosixPath(cohort['common_security_build'])
        assert not build_name.is_absolute() and '..' not in build_name.parts
        build_path=(root/cohort['common_security_build']).resolve(strict=True)
        assert build_path.is_relative_to(root/'runtime')
        assert sha(build_path)==cohort['common_security_build_sha256']
parent_path=root/a.parent_stage;parent=json.loads(parent_path.read_text())
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in parent['files'].items():resolve(name,digest)
dyld_build=None
dyld_provider=root/'runtime/dyld-vchroot-casefold-component-v2/dyld'
if a.dyld_build:
    assert a.runtime_stage and a.shared_profile_input
    dyld_path=(root/a.dyld_build).resolve(strict=True)
    assert dyld_path.is_relative_to(root/'runtime')
    dyld_build=json.loads(dyld_path.read_text())
    assert dyld_build['old_ImageLoader_ABI_preserved'] and dyld_build['source_component_update']
    assert dyld_build['original_prefix_globals_preserved']
    assert dyld_build['component_dynamic_imports']==dyld_build['component_rebases']==dyld_build['component_writable_segments']==0
    for name,digest in dyld_build['files'].items():resolve(name,digest)
    dyld_provider=(root/dyld_build['loader']).resolve(strict=True)
    assert dyld_provider.is_relative_to(root/'runtime') and sha(dyld_provider)==dyld_build['loader_sha256']
namespace_text=(root/parent['namespace']).read_text()
needle='rootfs="$project/runtime/rootfs"\n'
assert namespace_text.count(needle)==1
payload='''# One shared runtime selection must exist before launchd or any helper loads.
[[ -n ${LINUXCODE_RUN_DYLD_LIBRARY_PATH:-} && -n ${LINUXCODE_RUN_DYLD_FRAMEWORK_PATH:-} ]] || {
    echo "Shared runtime library and framework paths are required before bootstrap" >&2
    exit 2
}
for scoped_variable in "${!DARLING_DYLD_OVERRIDE_@}"; do
    echo "Program-specific runtime selection is not allowed: $scoped_variable" >&2
    exit 2
done
run_environment=(
    "DYLD_LIBRARY_PATH=$LINUXCODE_RUN_DYLD_LIBRARY_PATH"
    "DYLD_FRAMEWORK_PATH=$LINUXCODE_RUN_DYLD_FRAMEWORK_PATH"
)
if [[ -n ${LINUXCODE_RUN_OBJC_DISABLE_TAGGED_POINTERS+x} ]]; then
    run_environment+=("OBJC_DISABLE_TAGGED_POINTERS=$LINUXCODE_RUN_OBJC_DISABLE_TAGGED_POINTERS")
fi
'''
namespace_text=namespace_text.replace(needle,needle+payload,1)
namespace_text=optional_log_transport(namespace_text)
clean_environments=namespace_text.count('/usr/bin/env -i ')
assert clean_environments==5
namespace_text=namespace_text.replace('/usr/bin/env -i ','/usr/bin/env -i "${run_environment[@]}" ')
shutdown='/usr/bin/env DPREFIX="$DPREFIX" /usr/bin/darling shutdown'
assert namespace_text.count(shutdown)==1
namespace_text=namespace_text.replace(shutdown,'/usr/bin/env "${run_environment[@]}" DPREFIX="$DPREFIX" /usr/bin/darling shutdown',1)
workspace_mount='mount --bind "$project" "$rootfs/workspace"\n'
assert namespace_text.count(workspace_mount)==1
alias='''# The first Mach-O vchroot has not established its Darwin virtual root yet.
# Expose the same workspace spelling in Linux's private namespace as well.
mkdir -p "$rootfs/Volumes/SystemRoot/workspace"
mount --bind "$project" "$rootfs/Volumes/SystemRoot/workspace"
'''
namespace_text=namespace_text.replace(workspace_mount,workspace_mount+alias,1)
folder=Path(tempfile.mkdtemp(prefix='run-environment-launcher-',dir=root/'runtime'))
launcher=folder/'darling';namespace=folder/'runtime-ns.sh'
materialized={}
if a.runtime_stage:
    assert a.shared_profile_input
    runtime_path=root/a.runtime_stage;runtime=json.loads(runtime_path.read_text())
    shared_path=root/a.shared_profile_input;shared=json.loads(shared_path.read_text())
    assert shared['direct_resource_environment']['runtime_mode']=='unified'
    assert shared['source_runtime']==runtime['source_runtime']
    assert not any(v.startswith('DARLING_DYLD_OVERRIDE_') for v in shared['command'])
    base=(root/runtime['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent/'darling-root'
    system=folder/'darling-root';prefix=folder/'prefix';workdir=folder/'prefix.workdir';workdir.mkdir()
    for source,target in [(base,system),(root/'runtime/state/prefix',prefix)]:
        print('REFLINK_COPY',source,target,flush=True)
        subprocess.run(['cp','-a','--reflink=always','--no-preserve=links',str(source),str(target)],check=True)
    created_install_directories=[]
    def install_directory(destination,tree):
        """Create only missing image directories with the lower system mode.

        A host umask of 002 must not create a group-writable upper directory
        which hides a safe lower LaunchDaemons/LaunchAgents directory.
        Existing prefix/project directories retain their original permissions.
        """
        relative=destination.relative_to(tree)
        current=tree
        for part in relative.parts:
            current=current/part
            assert current.resolve().is_relative_to(tree.resolve()),current
            if current.exists():
                assert current.is_dir(),current
                continue
            lower=base/current.relative_to(tree)
            mode=(lower.stat().st_mode & 0o7777) if lower.is_dir() else 0o755
            current.mkdir(mode=mode)
            # mkdir applies the caller's umask; restore the selected mode only
            # on the directory just created, never on existing user content.
            current.chmod(mode)
            created_install_directories.append(dict(tree=str(tree.relative_to(root)),
                directory=str(current.relative_to(tree)),mode=oct(mode),
                inherited_from_lower=str(lower.relative_to(root)) if lower.is_dir() else None))
    # A runtime prefix is not an archive of earlier debugging sessions. Keep
    # the original evidence in place; discard only our newly cloned copies.
    excluded_count=excluded_bytes=0
    for path in prefix.iterdir():
        if re.fullmatch(r'core(?:\.\d+)?',path.name) and path.is_file() and not path.is_symlink():
            excluded_bytes+=path.stat().st_size;excluded_count+=1;path.unlink()
    removed=[]
    for name in ['.init.pid','.darlingserver.sock','.shellspawn.sock','private/var/run/shellspawn.sock']:
        path=prefix/name
        if path.exists() or path.is_symlink():
            assert not path.is_dir();path.unlink();removed.append(name)
    providers={
        'usr/lib/dyld':dyld_provider,
        'System/Library/PrivateFrameworks/PlugInKit.framework':root/parent['canonical_provider'],
        'usr/lib/swift/libswiftC6.dylib':root/'runtime/signed-compat-runtime-2083wv0o/libswiftC6.dylib',
        'usr/bin/codesign':root/'runtime/native-codesign-ci-v3/codesign',
        'usr/bin/codesign_allocate':root/'runtime/native-codesign-ci-v3/codesign_allocate-original',
        'System/Library/CoreServices/SystemVersion.plist':root/runtime['system_version_binding'],
    }
    core={'LINUXCODE_LIBXPC':'usr/lib/system/libxpc.dylib','LINUXCODE_LAUNCHD':'sbin/launchd',
          'LINUXCODE_LIBSYSTEM_KERNEL':'usr/lib/system/libsystem_kernel.dylib','LINUXCODE_QUARANTINE':'usr/lib/system/libquarantine.dylib',
          'LINUXCODE_SANDBOX':'usr/lib/system/libsystem_sandbox.dylib','LINUXCODE_LIBDYLD':'usr/lib/system/libdyld.dylib'}
    for key,target in core.items():
        row=runtime['source_runtime'][key];assert sha(root/row['path'])==row['sha256'];providers[target]=root/row['path']
    mdns=shared['native_mdns'];developer=mdns['developer_overlay'] if shared['use_original_developer_overlay'] else ''
    apple=mdns['mobile_device']['payload_root'] if shared['use_original_developer_overlay'] else ''
    if developer:providers['Library/Developer']=root/developer
    if apple:providers['Library/Apple']=root/apple
    if a.preinstall_common_security:
        common_environment=shared['direct_resource_environment']['tool_environment']
        def common_provider(key,suffix):
            for directory in common_environment[key].split(':'):
                spelling='/Volumes/SystemRoot/workspace/'
                if not directory.startswith(spelling):
                    continue
                candidate=root/directory[len(spelling):]/suffix
                if candidate.exists():
                    return candidate
            raise ValueError('Common runtime provider was not selected: '+suffix)
        providers['System/Library/Frameworks/Security.framework']=common_provider('DYLD_FRAMEWORK_PATH','Security.framework')
        providers['usr/lib/libDarlingCommonIdentityStore.dylib']=common_provider('DYLD_LIBRARY_PATH','libDarlingCommonIdentityStore.dylib')
    for target,source in cohort_providers:
        assert target not in providers,target
        providers[target]=source
    inventory={}
    for target,source in providers.items():
        assert source.exists();files={}
        if source.is_dir():
            for path in source.rglob('*'):
                if path.is_symlink():files[str(path.relative_to(source))]=dict(symlink=os.readlink(path))
                elif path.is_file():files[str(path.relative_to(source))]=dict(sha256=sha(path))
        else:files['.']=dict(sha256=sha(source))
        inventory[target]=dict(source=str(source.relative_to(root)),files=files)
        for tree in [system,prefix]:
            destination=tree/target;install_directory(destination.parent,tree)
            assert destination.parent.resolve().is_relative_to(tree.resolve()),destination
            if destination.is_symlink() or destination.is_file():destination.unlink()
            elif destination.is_dir():shutil.rmtree(destination)
            if source.is_dir():shutil.copytree(source,destination,symlinks=True,copy_function=shutil.copy2)
            else:shutil.copy2(source,destination)
    cohort_inventory={}
    for target,source,digest in cohort_rows:
        for tree in [system,prefix]:
            destination=tree/target
            assert destination.parent.resolve().is_relative_to(tree.resolve()),destination
            install_directory(destination.parent,tree)
            assert not destination.is_symlink() and not destination.is_dir(),destination
            shutil.copy2(source,destination)
            assert sha(destination)==digest
        cohort_inventory[target]=dict(source=str(source.relative_to(root)),sha256=digest,
                                      installed_in_system_and_prefix=True,mode=oct(source.stat().st_mode & 0o777))
    library_updates,library_inputs=install_source_libraries(system,prefix)
    if cohort_path:
        home=cohort.get('user',{}).get('home')
        if home:
            home_path=PurePosixPath(home)
            assert home_path.is_absolute() and '..' not in home_path.parts
            for tree in [system,prefix]:
                destination=tree/str(home_path).lstrip('/')
                assert destination.parent.resolve().is_relative_to(tree.resolve()),destination
                install_directory(destination,tree)
        # A complete cohort cannot be overridden by a post-bootstrap account mount.
        start=namespace_text.index('# Validate optional account fixtures before entering the Linux rootfs.')
        end=namespace_text.index('# The selected original Xcode package',start)
        namespace_text=namespace_text[:start]+'''[[ -z ${LINUXCODE_ACCOUNT_DATABASE:-} ]] || {
    echo "Accounts are already installed in the common image before bootstrap" >&2; exit 2;
}
account_database_relative=''
'''+namespace_text[end:]
        late_accounts='''    if [[ -n ${account_database_relative:-} ]]; then
        for account_file in passwd master.passwd group; do
            /usr/bin/nsenter --target "$account_server_pid" --mount \\
                /usr/bin/mount --bind "/workspace/$account_database_relative/$account_file" "/state/prefix/private/etc/$account_file"
        done
    fi
'''
        assert namespace_text.count(late_accounts)==1
        namespace_text=namespace_text.replace(late_accounts,'',1)
    # All former binary/framework substitutions are already present in both
    # physical trees; an overlay lookup must never see an old shadow inode.
    for variable in ['developer_overlay_relative','apple_overlay_relative']:
        start=namespace_text.index('    if [[ -n ${'+variable+':-} ]]; then\n')
        end=namespace_text.index('    fi\n',start)+len('    fi\n')
        namespace_text=namespace_text[:start]+namespace_text[end:]
    start=namespace_text.index('# Preserve the system location; DVT scans DYLD_FRAMEWORK_PATH for plugins.')
    end=namespace_text.index('if [[ -n $system_version_relative ]]; then',start)
    namespace_text=namespace_text[:start]+namespace_text[end:]
    start=namespace_text.index('if [[ -n $system_version_relative ]]; then',namespace_text.index('export DPREFIX='))
    end=namespace_text.index('\nfi\n',start)+len('\nfi\n')
    namespace_text=namespace_text[:start]+namespace_text[end:]
    bind='mount --bind "$project/runtime/state" "$rootfs/state"\n'
    assert namespace_text.count(bind)==1
    private_root=str(system.relative_to(root));private_state=str(folder.relative_to(root))
    block=f'''# The complete selected image and upper prefix exist before the first Mach-O.
[[ ${{developer_overlay_relative:-}} == {developer!r} && ${{apple_overlay_relative:-}} == {apple!r} ]] || {{
    echo "Shared image provider inputs differ from the prepared cohort" >&2; exit 2;
}}
mount --bind "$project/{private_root}" "$rootfs/usr/libexec/darling"
# Overlay upperdir and workdir must resolve within the same vfsmount.
mount --bind "$project/{private_state}" "$rootfs/state"
'''
    namespace_text=namespace_text.replace(bind,block,1)
    namespace_text,resolver=install_host_resolver(folder,system,prefix,namespace_text)
    bootstrap='''    /usr/bin/env -i "${run_environment[@]}" HOME=/root USER=root LOGNAME=root \\
        PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \\
        LANG=en_US.UTF-8 DPREFIX="$DPREFIX" /usr/bin/darling shell /usr/bin/true
'''
    assert namespace_text.count(bootstrap)==1
    bootstrap_wait='''    # Darling's first client waits only 15 seconds for shellspawn. A complete
    # shared image can still be loading launchctl at that deadline. Keep the
    # same server alive and wait for its actual socket, without changing any
    # provider or restarting a failed server.
    if ! '''+bootstrap.strip()+'''; then
        bootstrap_server_pid=$(cat /state/prefix/.init.pid)
        [[ $bootstrap_server_pid =~ ^[0-9]+$ ]] || exit 2
        bootstrap_deadline=$((SECONDS + 75))
        until /usr/bin/nsenter --target "$bootstrap_server_pid" --mount \\
            /usr/bin/test -S /state/prefix/var/run/shellspawn.sock; do
            kill -0 "$bootstrap_server_pid" || exit 1
            if (( SECONDS >= bootstrap_deadline )); then
                echo "Shared runtime bootstrap did not create shellspawn within 90 seconds" >&2
                exit 1
            fi
            sleep 1
        done
'''+bootstrap+'''    fi
'''
    namespace_text=namespace_text.replace(bootstrap,bootstrap_wait,1)
    first=namespace_text.index('/usr/bin/darling shell')
    late=namespace_text[first:]
    assert '/usr/bin/mount --bind' not in late.replace('/usr/bin/mount --bind "/workspace/$account_database_relative/$account_file" "/state/prefix/private/etc/$account_file"','')
    assert 'dyld-bootstrap-fcntl-component-v5/dyld" /state/prefix' not in namespace_text
    materialized=dict(whole_system_root=str(system.relative_to(root)),shared_prefix=str(prefix.relative_to(root)),
                      private_workdir=str(workdir.relative_to(root)),shared_state_mount=str(folder.relative_to(root)),
                      upper_and_workdir_same_mount=True,runtime_stage=a.runtime_stage,runtime_stage_sha256=sha(runtime_path),
                      shared_profile_input=a.shared_profile_input,shared_profile_input_sha256=sha(shared_path),
                      prefix_source='runtime/state/prefix',prefix_source_modified=False,reflink_independent_inodes=True,
                      removed_cloned_session_IPC=removed,providers=inventory,all_provider_bytes_installed_before_first_Darling=True,
                      excluded_cloned_diagnostics=dict(root_numeric_core_files=excluded_count,logical_bytes=excluded_bytes,original_evidence_modified=False),
                      late_provider_mounts=0,remaining_late_mounts=['private Darwin temporary tmpfs']+([] if cohort_path else ['optional account database files']))
    materialized['global_host_resolver']=resolver
    if library_updates:materialized['common_source_library_updates']=library_updates
    materialized['created_install_directories']=created_install_directories
    if cohort_path:
        materialized['service_cohort']=dict(manifest=str(cohort_path.relative_to(root)),manifest_sha256=sha(cohort_path),
                                           files=cohort_inventory,runtime_provider_destinations=[name for name,_ in cohort_providers],
                                           service_home=home,all_files_installed_before_first_Mach_O=True)
namespace.write_text(namespace_text)
launcher_text=(root/parent['launcher']).read_text()
assert launcher_text.count(parent['namespace'])==1
launcher.write_text(launcher_text.replace(parent['namespace'],str(namespace.relative_to(root)),1))
for path in [launcher,namespace]:path.chmod(0o755)
subprocess.run(['bash','-n',str(launcher)],check=True)
subprocess.run(['bash','-n',str(namespace)],check=True)
stage={**parent,'launcher':str(launcher.relative_to(root)),'namespace':str(namespace.relative_to(root)),
       'files':dict(parent['files']),'run_environment_shared_from_bootstrap':True,
       'shared_clean_environment_invocations':namespace_text.count('/usr/bin/env -i '),
       'run_environment_inputs':['LINUXCODE_RUN_DYLD_LIBRARY_PATH','LINUXCODE_RUN_DYLD_FRAMEWORK_PATH',
                                 'LINUXCODE_RUN_OBJC_DISABLE_TAGGED_POINTERS'],
       'run_environment_guest_keys':['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH','OBJC_DISABLE_TAGGED_POINTERS'],
       'pre_vchroot_workspace_alias':dict(guest_and_bootstrap_path='/Volumes/SystemRoot/workspace',
                                        source='$project',private_mount_namespace=True,before_first_Darling_start=True),
       'parent_run_environment_stage':a.parent_stage,'parent_run_environment_stage_sha256':sha(parent_path),
       'runtime_execution_verified':False,'full_goal_complete':False}
stage['optional_run_log_transport']='LINUXCODE_RUN_DARLING_OS_LOG_STDERR'
if materialized:
    stage['materialized_shared_runtime']=materialized
    stage['files'][str((folder/'resolv.conf').relative_to(root))]=sha(folder/'resolv.conf')
    stage['files'].update(library_inputs)
if dyld_build:
    stage['bootstrap_component_build']=a.dyld_build
    stage['files'].update(dyld_build['files'])
    stage['files'][a.dyld_build]=sha(root/a.dyld_build)
for path in [Path(__file__),parent_path,launcher,namespace]:stage['files'][str(path.relative_to(root))]=sha(path)
if cohort_path:
    stage['files'][str(cohort_path.relative_to(root))]=sha(cohort_path)
    for _,source,digest in cohort_rows:stage['files'][str(source.relative_to(root))]=digest
    for _,source in cohort_providers:
        for path in (source.rglob('*') if source.is_dir() else [source]):
            if path.is_file() and not path.is_symlink():stage['files'][str(path.relative_to(root))]=sha(path)
out=folder/'stage.json';out.write_text(json.dumps(stage,indent=2)+'\n')
report=dict(prepared=True,stage=str(out.relative_to(root)),launcher=stage['launcher'],namespace=stage['namespace'],
            old_stage_unmodified=sha(parent_path)==stage['parent_run_environment_stage_sha256'],
            configuration_modified=False,native_started=False,session_lock_acquired=False)
(folder/'prepared.json').write_text(json.dumps(report,indent=2)+'\n')
print('RUN_ENVIRONMENT_STAGE',out,flush=True)
