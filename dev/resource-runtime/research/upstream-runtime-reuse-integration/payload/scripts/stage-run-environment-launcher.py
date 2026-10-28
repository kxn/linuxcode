#!/usr/bin/env python3
"""Stage shared runtime paths before the first Mach-O process is created.

Reuse an existing namespace launcher and its mounts. Every clean environment
receives one run-level payload, including the initial server/launchd bootstrap.
The original stage and configuration are left unchanged; nothing is launched.
"""
from pathlib import Path
import argparse,hashlib,json,os,runpy,shutil,subprocess,tempfile

root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-stage',required=True)
p.add_argument('--runtime-stage',help='Materialize a matching full system root and independent writable prefix before bootstrap')
p.add_argument('--shared-profile-input',help='Unified profile metadata used only to resolve shared Developer/Apple provider inputs')
p.add_argument('--preinstall-common-security',action='store_true',help='Install the public Security framework and its common identity store into the shared image')
a=p.parse_args()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
parent_path=root/a.parent_stage;parent=json.loads(parent_path.read_text())
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in parent['files'].items():resolve(name,digest)
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
    removed=[]
    for name in ['.init.pid','.darlingserver.sock','.shellspawn.sock','private/var/run/shellspawn.sock']:
        path=prefix/name
        if path.exists() or path.is_symlink():
            assert not path.is_dir();path.unlink();removed.append(name)
    providers={
        'usr/lib/dyld':root/'runtime/dyld-vchroot-casefold-component-v2/dyld',
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
            destination=tree/target;destination.parent.mkdir(parents=True,exist_ok=True)
            assert destination.parent.resolve().is_relative_to(tree.resolve()),destination
            if destination.is_symlink() or destination.is_file():destination.unlink()
            elif destination.is_dir():shutil.rmtree(destination)
            if source.is_dir():shutil.copytree(source,destination,symlinks=True,copy_function=shutil.copy2)
            else:shutil.copy2(source,destination)
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
                      late_provider_mounts=0,remaining_late_mounts=['private Darwin temporary tmpfs','optional account database files'])
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
if materialized:stage['materialized_shared_runtime']=materialized
for path in [Path(__file__),parent_path,launcher,namespace]:stage['files'][str(path.relative_to(root))]=sha(path)
out=folder/'stage.json';out.write_text(json.dumps(stage,indent=2)+'\n')
report=dict(prepared=True,stage=str(out.relative_to(root)),launcher=stage['launcher'],namespace=stage['namespace'],
            old_stage_unmodified=sha(parent_path)==stage['parent_run_environment_stage_sha256'],
            configuration_modified=False,native_started=False,session_lock_acquired=False)
(folder/'prepared.json').write_text(json.dumps(report,indent=2)+'\n')
print('RUN_ENVIRONMENT_STAGE',out,flush=True)
