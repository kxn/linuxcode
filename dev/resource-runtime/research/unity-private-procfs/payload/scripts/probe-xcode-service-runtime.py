#!/usr/bin/env python3
"""Trace the original Xcode process or load the genuine per-user distnoted job."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, fcntl, hashlib, json, plistlib, re, runpy, shlex, subprocess, time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['version', 'showsdks', 'build'])
parser.add_argument('--trace-processes', action='store_true')
parser.add_argument('--distnoted-agent', action='store_true')
parser.add_argument('--distnoted-daemon', action='store_true')
parser.add_argument('--cfprefsd-daemon', action='store_true')
parser.add_argument('--cfprefsd-agent', action='store_true')
parser.add_argument('--log-pack', action='store_true')
parser.add_argument('--system-resources', action='store_true')
parser.add_argument('--mdns', action='store_true')
parser.add_argument('--mdns-library-only', action='store_true')
parser.add_argument('--security-cloud-rpc', action='store_true')
parser.add_argument('--typed-new-delete', action='store_true')
parser.add_argument('--sandbox-checks', action='store_true')
parser.add_argument('--expected-access', action='store_true')
parser.add_argument('--sandbox-policy', action='store_true')
parser.add_argument('--pid-generation', action='store_true')
parser.add_argument('--mobile-device', action='store_true')
parser.add_argument('--crypto-quarantine', action='store_true')
parser.add_argument('--quarantine-vfs', action='store_true')
parser.add_argument('--device-identity', action='store_true')
parser.add_argument('--cryptex', action='store_true')
parser.add_argument('--workqueue-stack', action='store_true')
parser.add_argument('--dispatch-workloop', action='store_true')
parser.add_argument('--diskmanagement', action='store_true')
parser.add_argument('--sent-messages', action='store_true')
parser.add_argument('--applearchive', action='store_true')
parser.add_argument('--corecrypto-hkdf', action='store_true')
parser.add_argument('--argument-parser', action='store_true')
parser.add_argument('--native-crypto', action='store_true')
parser.add_argument('--launchd-sandbox', action='store_true')
parser.add_argument('--sandbox-fs', action='store_true')
parser.add_argument('--fsevents-device', action='store_true')
parser.add_argument('--log-compose', action='store_true')
parser.add_argument('--iokitd-power', action='store_true')
parser.add_argument('--iokitd-matching', action='store_true')
parser.add_argument('--mount-flags', action='store_true')
parser.add_argument('--core-volume-diagnostic', action='store_true')
parser.add_argument('--s2c-lifecycle', action='store_true')
parser.add_argument('--xpc-activation', action='store_true')
parser.add_argument('--materialize-policy', action='store_true')
parser.add_argument('--mobileasset-query', action='store_true')
parser.add_argument('--icu-data', action='store_true')
parser.add_argument('--fatal-signal', action='store_true')
parser.add_argument('--system-version', action='store_true')
parser.add_argument('--swb-logging', action='store_true')
parser.add_argument('--swb-swift-logging', action='store_true')
parser.add_argument('--fsevents-history', action='store_true')
parser.add_argument('--corpse-map', action='store_true')
parser.add_argument('--global-fsevents', action='store_true')
parser.add_argument('--vchroot-links', action='store_true')
parser.add_argument('--metadata-root-name', action='store_true')
parser.add_argument('--tool-dispatch', action='store_true')
parser.add_argument('--resource-tool-dispatch-stage', type=Path)
parser.add_argument('--codesign-stage', type=Path)
parser.add_argument('--identity-stage', type=Path)
parser.add_argument('--identity-store', type=Path)
parser.add_argument('--derq-stage', type=Path)
parser.add_argument('--native-codesign-stage', type=Path)
parser.add_argument('--mldr-stage', type=Path)
parser.add_argument('--shared-remap-stage', type=Path)
parser.add_argument('--libsystem-kqueue-build', type=Path)
parser.add_argument('--loader-environment-stage', type=Path)
parser.add_argument('--private-procfs-stage', type=Path)
parser.add_argument('--filecoordination', action='store_true')
parser.add_argument('--timeout-seconds', type=int, default=60)
parser.add_argument('--xcode-arguments-file', type=Path)
parser.add_argument('--prebuild-command-file', type=Path)
parser.add_argument('--skip-uti-diagnostic', action='store_true')
parser.add_argument('--trace-sandbox', action='store_true')
args = parser.parse_args()
if args.resource_tool_dispatch_stage or args.codesign_stage:args.tool_dispatch=True
if args.native_codesign_stage:
    assert args.identity_store and not (args.codesign_stage or args.identity_stage or args.derq_stage)
    args.tool_dispatch=True
if args.identity_stage:
    assert args.identity_store and args.codesign_stage
if args.derq_stage:assert args.identity_stage
if args.tool_dispatch:args.metadata_root_name=True
if args.metadata_root_name:args.vchroot_links=True
if args.vchroot_links:args.global_fsevents=True
if args.global_fsevents:args.corpse_map=True
if args.corpse_map:args.fsevents_history=True
if args.fsevents_history:args.swb_swift_logging=True
if args.swb_swift_logging:args.swb_logging=True
if args.swb_logging:args.system_version=True
if args.system_version:args.fatal_signal=True
if args.fatal_signal:args.icu_data=True
if args.icu_data:args.mobileasset_query=True
if args.mobileasset_query:args.materialize_policy=True
if args.materialize_policy:args.xpc_activation=True
if args.xpc_activation:args.s2c_lifecycle=True
if args.core_volume_diagnostic or args.s2c_lifecycle:args.mount_flags=True
if args.mount_flags:args.iokitd_matching=True
if args.iokitd_matching:args.iokitd_power=True
if args.iokitd_power:args.log_compose=True
if args.log_compose:args.fsevents_device=True
if args.fsevents_device:args.sandbox_fs=True
if args.sandbox_fs:args.launchd_sandbox=True
if args.launchd_sandbox:args.native_crypto=True
if args.filecoordination:args.native_crypto=True
if args.native_crypto:args.argument_parser=True
if args.argument_parser:args.corecrypto_hkdf=True
if args.corecrypto_hkdf:args.applearchive=True
if args.applearchive:args.sent_messages=True
if args.sent_messages:args.diskmanagement=True
if args.diskmanagement:args.dispatch_workloop=True
if args.dispatch_workloop:args.workqueue_stack=True
if args.workqueue_stack:args.cryptex=True
if args.cryptex:args.device_identity=True
if args.device_identity:args.quarantine_vfs=True
if args.quarantine_vfs:args.crypto_quarantine=True
if args.crypto_quarantine:args.mobile_device=True
if args.mobile_device:args.pid_generation=True
if args.pid_generation:args.sandbox_policy=True
if args.sandbox_policy:args.expected_access=True
if args.expected_access:args.sandbox_checks=True
if args.skip_uti_diagnostic and not args.sandbox_checks:parser.error('UTI failure diagnosis requires --sandbox-checks')
if args.sandbox_checks:args.typed_new_delete=True
if args.typed_new_delete:args.security_cloud_rpc=True
if args.security_cloud_rpc:args.mdns=True
if args.mdns_library_only:args.mdns=True
digest = lambda path: hashlib.sha256((root / path).read_bytes()).hexdigest()
m = runpy.run_path(str(root / ('scripts/xcode-tool-dispatch-runtime-profile.py' if args.tool_dispatch else 'scripts/metadata-root-name-runtime-profile.py' if args.metadata_root_name else 'scripts/vchroot-links-runtime-profile.py' if args.vchroot_links else 'scripts/global-fsevents-runtime-profile.py' if args.global_fsevents else 'scripts/corpse-map-runtime-profile.py' if args.corpse_map else 'scripts/fsevents-history-profile.py' if args.fsevents_history else 'scripts/swb-swift-logging-runtime-profile.py' if args.swb_swift_logging else 'scripts/swb-logging-runtime-profile.py' if args.swb_logging else 'scripts/system-version-runtime-profile.py' if args.system_version else 'scripts/fatal-signal-runtime-profile.py' if args.fatal_signal else 'scripts/icu-data-runtime-profile.py' if args.icu_data else 'scripts/mobileasset-query-runtime-profile.py' if args.mobileasset_query else 'scripts/materialize-runtime-profile.py' if args.materialize_policy else 'scripts/xpc-activation-runtime-profile.py' if args.xpc_activation else 'scripts/s2c-lifecycle-runtime-profile.py' if args.s2c_lifecycle else 'scripts/mount-volumes-diagnostic-profile.py' if args.core_volume_diagnostic else 'scripts/mount-flags-runtime-profile.py' if args.mount_flags else 'scripts/iokitd-matching-runtime-profile.py' if args.iokitd_matching else 'scripts/iokitd-power-runtime-profile.py' if args.iokitd_power else 'scripts/log-compose-runtime-profile.py' if args.log_compose else 'scripts/fsevents-device-runtime-profile.py' if args.fsevents_device else 'scripts/sandbox-fs-runtime-profile.py' if args.sandbox_fs else 'scripts/launchd-sandbox-source-profile.py' if args.launchd_sandbox else 'scripts/commoncrypto-original-profile.py' if args.native_crypto else 'scripts/argument-parser-native-profile.py' if args.argument_parser else 'scripts/corecrypto-hkdf-profile.py' if args.corecrypto_hkdf else 'scripts/applearchive-native-profile.py' if args.applearchive else 'scripts/xpc-sent-message-runtime-profile.py' if args.sent_messages else 'scripts/diskmanagement-nserror-runtime-profile.py' if args.diskmanagement else 'scripts/dispatch-workloop-runtime-profile.py' if args.dispatch_workloop else 'scripts/workqueue-stack-runtime-profile.py' if args.workqueue_stack else 'scripts/cryptex-native-profile.py' if args.cryptex else 'scripts/device-identity-native-profile.py' if args.device_identity else 'scripts/quarantine-vfs-runtime-profile.py' if args.quarantine_vfs else 'scripts/crypto-quarantine-runtime-profile.py' if args.crypto_quarantine else 'scripts/mobile-device-native-profile.py' if args.mobile_device else 'scripts/pid-generation-source-profile.py' if args.pid_generation else 'scripts/sandbox-policy-source-profile.py' if args.sandbox_policy else 'scripts/expected-access-source-profile.py' if args.expected_access else 'scripts/sandbox-check-source-profile.py' if args.sandbox_checks else 'scripts/typed-new-delete-profile.py' if args.typed_new_delete else 'scripts/security-cloud-rpc-profile.py' if args.security_cloud_rpc else 'scripts/mdns-native-profile.py' if args.mdns else 'scripts/xcode-system-resources-profile.py' if args.system_resources else 'scripts/log-pack-profile.py' if args.log_pack else 'scripts/foundation-coherent-profile.py')))
p = m['profile'](diagnostic=args.core_volume_diagnostic) if args.s2c_lifecycle else m['profile'](include_system_resources=False) if args.mdns_library_only else m['profile']()
if args.resource_tool_dispatch_stage:
    m=runpy.run_path(str(root/'scripts/resource-tool-dispatch-profile.py'))
    p=m['profile'](diagnostic=args.core_volume_diagnostic,dispatch_stage=str(args.resource_tool_dispatch_stage))
if args.codesign_stage:
    m=runpy.run_path(str(root/'scripts/codesign-zsign-runtime-profile.py'))
    p=m['profile'](diagnostic=args.core_volume_diagnostic,codesign_stage=str(args.codesign_stage))
if args.identity_stage:
    m=runpy.run_path(str(root/'scripts/local-identity-store-profile.py'))
    p=m['profile'](diagnostic=args.core_volume_diagnostic,codesign_stage=str(args.codesign_stage),identity_stage=str(args.identity_stage),identity_store=str(args.identity_store),trace=True)
if args.derq_stage:
    m=runpy.run_path(str(root/'scripts/derq-runtime-profile.py'))
    p=m['profile'](derq_stage=str(args.derq_stage),diagnostic=args.core_volume_diagnostic,codesign_stage=str(args.codesign_stage),identity_stage=str(args.identity_stage),identity_store=str(args.identity_store),trace=True)
if args.native_codesign_stage:
    m=runpy.run_path(str(root/'scripts/native-codesign-runtime-profile.py'))
    p=m['profile'](native_codesign_stage=str(args.native_codesign_stage),identity_store=str(args.identity_store),diagnostic=args.core_volume_diagnostic)
if args.mldr_stage:
    p=runpy.run_path(str(root/'scripts/mldr-dynamic-rlimit-profile.py'))['select'](p,str(args.mldr_stage))
if args.shared_remap_stage:
    p=runpy.run_path(str(root/'scripts/shared-remap-runtime-profile.py'))['select'](p,str(args.shared_remap_stage))
if args.libsystem_kqueue_build:
    p=runpy.run_path(str(root/'scripts/libsystem-kqueue-runtime-profile.py'))['select'](p,str(args.libsystem_kqueue_build))
if args.loader_environment_stage:
    p=runpy.run_path(str(root/'scripts/loader-environment-runtime-profile.py'))['select'](p,str(args.loader_environment_stage))
if args.private_procfs_stage:
    p=runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))['select'](p,str(args.private_procfs_stage))
verified = json.loads((root / 'artifacts/native-lsd-foundation-coherent-probe.json').read_text())
assert verified['UTI_functional_execution_verified'] and verified['exit_status'] == 0
for key in ['source_objc', 'source_selector', 'foundation_coherent']:
    assert verified[key] == p[key]
if args.mdns:
    assert verified['source_runtime']==p['xpc_collections_runtime']['previous_source_runtime']
else:
    assert verified['source_runtime']==p['source_runtime']
if not (args.log_pack or args.system_resources or args.mdns):
    assert verified['source_fsevents'] == p['source_fsevents']
guest = '/Volumes/SystemRoot/workspace/'
build = root / 'runtime/xcode-service-runtime'
build.mkdir(parents=True, exist_ok=True)
stem = 'xcode-service-runtime-' + ('fsevents-device-' if args.fsevents_device else '') + ('sandbox-fs-' if args.sandbox_fs else '') + ('launchd-sandbox-' if args.launchd_sandbox else '') + ('coordination-' if args.filecoordination else '') + ('nativecrypto-' if args.native_crypto else '') + ('parser-' if args.argument_parser else '') + ('hkdf-' if args.corecrypto_hkdf else '') + ('archive-' if args.applearchive else '') + ('sent-' if args.sent_messages else '') + ('diskmanagement-' if args.diskmanagement else '') + ('dispatch-' if args.dispatch_workloop else '') + ('workqueue-' if args.workqueue_stack else '') + ('cryptex-' if args.cryptex else '') + ('device-' if args.device_identity else '') + ('vfs-' if args.quarantine_vfs else '') + ('crypto-' if args.crypto_quarantine else '') + ('extended-' if args.timeout_seconds!=60 else '') + ('mobile-' if args.mobile_device else '') + ('generation-' if args.pid_generation else '') + ('policy-' if args.sandbox_policy else '') + ('expected-' if args.expected_access else '') + ('sandbox-' if args.sandbox_checks else '') + ('typed-' if args.typed_new_delete else '') + ('cloud-base-' if args.security_cloud_rpc and args.mdns_library_only else 'cloud-' if args.security_cloud_rpc else 'mdns-base-' if args.mdns_library_only else 'mdns-' if args.mdns else 'resources-' if args.system_resources else 'pack-' if args.log_pack else '') + ('prefs-daemon-' if args.cfprefsd_daemon else '') + ('prefs-agent-' if args.cfprefsd_agent else '') + ('agent-' if args.distnoted_agent else '') + ('daemon-' if args.distnoted_daemon else '') + ('trace-' if args.trace_processes else '') + ('diagnostic-' if args.skip_uti_diagnostic else '') + args.mode
if args.fsevents_device:
    stem='xcode-service-runtime-'+('tool-dispatch-diagnostic-' if args.tool_dispatch and args.core_volume_diagnostic else 'tool-dispatch-' if args.tool_dispatch else 'metadata-root-name-diagnostic-' if args.metadata_root_name and args.core_volume_diagnostic else 'metadata-root-name-' if args.metadata_root_name else 'vchroot-links-diagnostic-' if args.vchroot_links and args.core_volume_diagnostic else 'vchroot-links-' if args.vchroot_links else 'global-fsevents-diagnostic-' if args.global_fsevents and args.core_volume_diagnostic else 'global-fsevents-' if args.global_fsevents else 'corpse-map-diagnostic-' if args.corpse_map and args.core_volume_diagnostic else 'corpse-map-' if args.corpse_map else 'fsevents-history-diagnostic-' if args.fsevents_history and args.core_volume_diagnostic else 'fsevents-history-' if args.fsevents_history else 'swb-swift-logging-diagnostic-' if args.swb_swift_logging and args.core_volume_diagnostic else 'swb-swift-logging-' if args.swb_swift_logging else 'swb-logging-diagnostic-' if args.swb_logging and args.core_volume_diagnostic else 'swb-logging-' if args.swb_logging else 'system-version-diagnostic-' if args.system_version and args.core_volume_diagnostic else 'system-version-' if args.system_version else 'fatal-signal-diagnostic-' if args.fatal_signal and args.core_volume_diagnostic else 'fatal-signal-' if args.fatal_signal else 'icu-data-diagnostic-' if args.icu_data and args.core_volume_diagnostic else 'icu-data-' if args.icu_data else 'mobileasset-query-diagnostic-' if args.mobileasset_query and args.core_volume_diagnostic else 'mobileasset-query-' if args.mobileasset_query else 'materialize-policy-diagnostic-' if args.materialize_policy and args.core_volume_diagnostic else 'materialize-policy-' if args.materialize_policy else 'xpc-activation-diagnostic-' if args.xpc_activation and args.core_volume_diagnostic else 'xpc-activation-' if args.xpc_activation else 's2c-lifecycle-diagnostic-' if args.s2c_lifecycle and args.core_volume_diagnostic else 's2c-lifecycle-' if args.s2c_lifecycle else 'core-volumes-diagnostic-' if args.core_volume_diagnostic else 'mount-flags-' if args.mount_flags else 'iokitd-matching-' if args.iokitd_matching else 'iokitd-power-' if args.iokitd_power else 'log-compose-' if args.log_compose else 'fsevents-device-')+args.mode+'-'+hashlib.sha256(json.dumps(vars(args),sort_keys=True,default=str).encode()).hexdigest()[:12]
# Preserve the preceding attempt before reusing its log/job/script names.
previous_report=root/('artifacts/'+stem+'.json')
if previous_report.exists():
    previous=json.loads(previous_report.read_text());report_sha=hashlib.sha256(previous_report.read_bytes()).hexdigest()
    archive=root/'artifacts/xcode-service-probe-history'/report_sha;archive.mkdir(parents=True,exist_ok=True)
    expected={str(previous_report.relative_to(root)):report_sha,previous['log']:previous['log_sha256'],previous['script']:previous['script_sha256'],**previous.get('service_logs',{})}
    expected.update({job['path']:job['sha256'] for job in previous.get('jobs',[])})
    manifest={}
    for name,sha in expected.items():
        data=(root/name).read_bytes();assert hashlib.sha256(data).hexdigest()==sha,'Previous probe evidence changed: '+name
        destination=archive/sha
        if not destination.exists():destination.write_bytes(data)
        manifest[name]={'sha256':sha,'archived':str(destination.relative_to(root))}
    (archive/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
jobs = []
account_manifest = {}
preference_service = {}
filecoordination_service = {}
with (root / 'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    selections = [('dirhelper', verified['paired_dirhelper_job']), ('lsd', verified['selected_job'])]
    if args.core_volume_diagnostic:
        native_services=[('configd','usr/libexec/configd','com.apple.configd.plist'),('diskarbitrationd','usr/libexec/diskarbitrationd','com.apple.diskarbitrationd.plist'),('coreservicesd','System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/CarbonCore.framework/Versions/A/Support/coreservicesd','com.apple.coreservicesd.plist')]
        prepared=[]
        for name,relative,plist_name in native_services:
            source='runtime/recovery/macOS Base System/'+relative
            dest=build/name;dest.write_bytes((root/source).read_bytes());dest.chmod(0o755)
            assert digest(source)==digest(str(dest.relative_to(root)))
            job=plistlib.loads((root/('runtime/recovery/macOS Base System/System/Library/LaunchDaemons/'+plist_name)).read_bytes())
            job.pop('Program',None);job['ProgramArguments']=[guest+str(dest.relative_to(root))]
            job['EnvironmentVariables']=dict(verified['selected_job']['EnvironmentVariables']);job['RunAtLoad']=True
            prepared.append((name,job))
        selections=prepared+selections
    if args.filecoordination:
        original='runtime/recovery/macOS Base System/usr/sbin/filecoordinationd'
        destination=build/'filecoordinationd';destination.write_bytes((root/original).read_bytes());destination.chmod(0o755)
        assert digest(original)==digest(str(destination.relative_to(root)))
        original_job='runtime/recovery/macOS Base System/System/Library/LaunchDaemons/com.apple.FileCoordination.plist'
        job=plistlib.loads((root/original_job).read_bytes());job['Program']=guest+str(destination.relative_to(root));job['EnvironmentVariables']=dict(verified['selected_job']['EnvironmentVariables'])
        selections.insert(0,('filecoordination',job))
        filecoordination_service=dict(original=original,original_sha256=digest(original),selected=str(destination.relative_to(root)),selected_sha256=digest(str(destination.relative_to(root))),original_job=original_job,original_job_sha256=digest(original_job),binary_modified=False)
    if args.cfprefsd_daemon or args.cfprefsd_agent:
        original = 'runtime/recovery/macOS Base System/usr/sbin/cfprefsd'
        destination = build/'cfprefsd'
        destination.write_bytes((root/original).read_bytes())
        destination.chmod(0o755)
        assert digest(original)==digest(str(destination.relative_to(root)))
        preference_service={'original':original,'sha256':digest(original),'selected':str(destination.relative_to(root)),'binary_modified':False}
        for enabled,name,location in [
            (args.cfprefsd_daemon,'cfprefsd-daemon','LaunchDaemons/com.apple.cfprefsd.xpc.daemon.plist'),
            (args.cfprefsd_agent,'cfprefsd-agent','LaunchAgents/com.apple.cfprefsd.xpc.agent.plist')]:
            if not enabled:continue
            job=plistlib.loads((root/'runtime/recovery/macOS Base System/System/Library'/location).read_bytes())
            job['ProgramArguments'][0]=guest+str(destination.relative_to(root))
            job['EnvironmentVariables']=dict(verified['selected_job']['EnvironmentVariables'])
            selections.insert(0,(name,job))
    if args.distnoted_agent or args.distnoted_daemon:
        original = 'runtime/recovery/macOS Base System/usr/sbin/distnoted'
        destination = build / 'distnoted'
        destination.write_bytes((root / original).read_bytes())
        destination.chmod(0o755)
        assert digest(original) == digest(str(destination.relative_to(root)))
        for enabled, name, location in [
            (args.distnoted_agent, 'distnoted-agent', 'LaunchAgents/com.apple.distnoted.xpc.agent.plist'),
            (args.distnoted_daemon, 'distnoted-daemon', 'LaunchDaemons/com.apple.distnoted.xpc.daemon.plist')]:
            if not enabled:
                continue
            job = plistlib.loads((root / 'runtime/recovery/macOS Base System/System/Library' / location).read_bytes())
            job['ProgramArguments'][0] = guest + str(destination.relative_to(root))
            job['EnvironmentVariables'] = {**verified['selected_job']['EnvironmentVariables'], **job['EnvironmentVariables']}
            if name == 'distnoted-daemon':
                # The legacy launchctl does not understand modern feature-flag
                # conditionals. This probe selects its actual System session.
                job['LimitLoadToSessionType'] = 'System'
            selections.insert(0, (name, job))
    if args.distnoted_daemon:
        account_dir = build / 'accounts'
        account_dir.mkdir(exist_ok=True)
        template = root / 'runtime/recovery/macOS Base System/System/Library/Templates/Data/private/etc'
        passwd = next(line for line in (template / 'passwd').read_text().splitlines() if line.startswith('_distnote:'))
        group = next(line for line in (template / 'group').read_text().splitlines() if line.startswith('_distnote:'))
        fields = passwd.split(':')
        assert fields[2:4] == ['241', '241'] and group.split(':')[2] == '241'
        master = ':'.join(fields[:4] + ['', '0', '0'] + fields[4:])
        for name, addition in [('passwd', passwd), ('master.passwd', master), ('group', group)]:
            original_text = (root / 'runtime/state/prefix/private/etc' / name).read_text()
            assert not any(line.startswith('_distnote:') for line in original_text.splitlines())
            file = account_dir / name
            file.write_text(original_text.rstrip('\n') + '\n' + addition + '\n')
            file.chmod(0o600 if name == 'master.passwd' else 0o644)
            account_manifest[str(file.relative_to(root))] = digest(str(file.relative_to(root)))
    for name, original_job in selections:
        job = dict(original_job)
        job['EnvironmentVariables'] = dict(job['EnvironmentVariables'])
        if args.trace_sandbox:job['EnvironmentVariables']['DARLING_SANDBOX_TRACE']='1'
        for arg in p['command']:
            if arg.startswith(('DYLD_LIBRARY_PATH=', 'DYLD_FRAMEWORK_PATH=')):
                key,value=arg.split('=',1)
                job['EnvironmentVariables'][key]=value
        job['StandardOutPath'] = job['StandardErrorPath'] = guest + 'logs/' + stem + '-' + name + '.log'
        file = build / (stem + '-' + name + '.plist')
        file.write_bytes(plistlib.dumps(job))
        file.chmod(0o644)
        (root / ('logs/' + stem + '-' + name + '.log')).write_text('')
        jobs.append(dict(name=name, path=str(file.relative_to(root)), sha256=digest(str(file.relative_to(root))), job=job))
script = build / (stem + '.sh')
uti_command=guest+'artifacts/uniform-type-identifiers-native\n'
if args.skip_uti_diagnostic:
    uti_command="printf 'SERVICE_RUNTIME_UTI_PREFLIGHT_SKIPPED_DIAGNOSTIC_ONLY\\n'\n"
else:
    uti_command+="printf 'SERVICE_RUNTIME_UTI_PREFLIGHT_OK\\n'\n"
prebuild_command=''
if args.prebuild_command_file:
    prebuild_argv=json.loads(args.prebuild_command_file.read_text())
    assert isinstance(prebuild_argv,list) and prebuild_argv and all(isinstance(v,str) for v in prebuild_argv)
    prebuild_command=shlex.join(prebuild_argv)+"\nprintf 'SERVICE_RUNTIME_PREBUILD_COMMAND_OK\\n'\n"
script.write_text('#!/bin/bash\nset -x\nset -e\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
                  ('launchctl remove com.apple.FileCoordination || true\n' if args.filecoordination else '') +
                  ('/usr/bin/id _distnote\n' if args.distnoted_daemon else '') +
                  '\n'.join('launchctl load ' + ('-S Background ' if j['name'] in ['distnoted-agent','cfprefsd-agent'] else '') + guest + j['path'] for j in jobs) + '\n' +
                  "trap '" + '; '.join('launchctl remove ' + j['job']['Label'] + ' >/dev/null 2>&1' for j in reversed(jobs)) + "' EXIT\n" +
                  '\n'.join('launchctl list ' + j['job']['Label'] for j in jobs) + '\n' +
                  uti_command + prebuild_command + 'set +e\n' +
                  "printf 'SERVICE_RUNTIME_XCODE_INVOCATION_BEGIN\\n'\n" +
                  '/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild "$@"\n' +
                  'status=$?\nprintf "SERVICE_RUNTIME_XCODE_STATUS %s\\n" "$status"\n' +
                  '\n'.join('launchctl list ' + j['job']['Label'] for j in jobs) + '\nexit "$status"\n')
xcode_args = ['-project', guest + 'fixtures/XcodeSmoke/XcodeSmoke.xcodeproj', '-scheme', 'XcodeSmoke', '-sdk', 'macosx', '-configuration', 'Debug', '-derivedDataPath', guest + 'runtime/xcode-service-runtime/DerivedData', 'CODE_SIGNING_ALLOWED=NO', 'build'] if args.mode == 'build' else ['-' + args.mode]
if args.xcode_arguments_file:
    xcode_args=json.loads(args.xcode_arguments_file.read_text())
    assert isinstance(xcode_args,list) and xcode_args and all(isinstance(v,str) for v in xcode_args)
command = p['command'][:-2] + ['/bin/bash', guest + str(script.relative_to(root)), *xcode_args]
assert 1 <= args.timeout_seconds <= 600
command[3]=str(args.timeout_seconds)
if args.trace_sandbox:command.insert(len(p['command'])-2,'DARLING_SANDBOX_TRACE=1')
trace_prefix = 'logs/' + stem + '.strace'
if args.trace_processes:
    command[3] = '180'
    command = [str(root / 'runtime/tools/strace-package/unpacked/usr/bin/strace'), '-ff', '-tt', '-s', '240', '-e', 'trace=process', '-e', 'signal=SIGABRT,SIGILL,SIGSEGV,SIGTERM,SIGKILL', '-o', str(root / trace_prefix), *command]
log = 'logs/' + stem + '.log'
environment = m['environment'](p)
gui_variables=['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']
for name in gui_variables:environment.pop(name,None)
prefix_accounts={str(path.relative_to(root)):digest(str(path.relative_to(root))) for path in (root/'runtime/state/prefix/private/etc').iterdir() if path.name in ['passwd','master.passwd','group']}
if args.distnoted_daemon:
    environment['LINUXCODE_ACCOUNT_DATABASE'] = str(build / 'accounts')
xcode_observations=[]
with (root / log).open('w') as stream:
    result = subprocess.Popen(command, cwd=root, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    # A target can start and then hang without producing a returned-status
    # marker. Observe the actual executable instead of equating return to start.
    while result.poll() is None:
        if not xcode_observations:
            for process in Path('/proc').iterdir():
                if not process.name.isdigit():continue
                try:
                    argv=process.joinpath('cmdline').read_bytes().split(b'\0')
                    if argv[0]!=b'/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild':continue
                    if [v.decode() for v in argv[1:] if v]!=xcode_args:continue
                    xcode_observations.append(dict(host_PID=int(process.name),argv=[v.decode() for v in argv if v],stat=process.joinpath('stat').read_text(),status=process.joinpath('status').read_text()))
                except (OSError,UnicodeDecodeError,IndexError):continue
        time.sleep(0.05)
text = (root / log).read_text()
has_marker=lambda marker:bool(re.search('^'+re.escape(marker)+'$',text,re.M))
native_statuses=re.findall(r'^SERVICE_RUNTIME_XCODE_STATUS ([0-9]+)$',text,re.M)
print(text[-9000:], flush=True)
for name,sha in prefix_accounts.items():assert digest(name)==sha,'Shared prefix account database changed: '+name
original_xcode = 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild'
assert digest(original_xcode) == digest('runtime/xcode-extract/Xcode.app/Contents/Developer/usr/bin/xcodebuild')
record = {**p, 'checked_at': datetime.now(timezone.utc).isoformat(), 'command': command,
          'exit_status': result.returncode, 'log': log, 'log_sha256': digest(log), 'jobs': jobs,
          'script': str(script.relative_to(root)), 'script_sha256': digest(str(script.relative_to(root))),
          'original_xcodebuild_sha256': digest(original_xcode), 'xcode_arguments': xcode_args,
          'gui_environment_removed':gui_variables,'native_xcode_status':native_statuses,
          'xcode_arguments_file':str(args.xcode_arguments_file) if args.xcode_arguments_file else None,
          'xcode_arguments_file_sha256':digest(args.xcode_arguments_file) if args.xcode_arguments_file else None,
          'UTI_preflight_verified': has_marker('SERVICE_RUNTIME_UTI_PREFLIGHT_OK'),
          'diagnostic_without_UTI_preflight':args.skip_uti_diagnostic,
          'xcode_process_started':bool(xcode_observations) or bool(native_statuses),
          'xcode_invocation_attempted':has_marker('SERVICE_RUNTIME_XCODE_INVOCATION_BEGIN'),
          'xcode_process_returned':bool(native_statuses),
          'xcode_live_observations':xcode_observations,
          'sandbox_query_trace_enabled':args.trace_sandbox,
          'trace_files': {str(f.relative_to(root)): digest(str(f.relative_to(root))) for f in (root / 'logs').glob(stem + '.strace.*')},
          'account_database': account_manifest,
          'prefix_accounts_unchanged': prefix_accounts,
          'distnoted_requested': args.distnoted_daemon or args.distnoted_agent,
          'original_preference_service':preference_service,
          'original_filecoordination_service':filecoordination_service,
          'core_volumes_diagnostic':p.get('mount_volumes_diagnostic'),
          'source_s2c_lifecycle':p.get('source_s2c_lifecycle'),
          'source_xpc_activation':p.get('source_xpc_activation'),
          'source_tool_dispatch':p.get('source_tool_dispatch'),
          'local_identity_stage':p.get('local_identity_stage'),
          'local_identity_store':p.get('local_identity_store'),
          'derq_stage':p.get('derq_stage'),
          'native_codesign_stage':p.get('native_codesign_stage'),
          'prebuild_command_verified':has_marker('SERVICE_RUNTIME_PREBUILD_COMMAND_OK'),
          'source_metadata_root_name':p.get('source_metadata_root_name'),
          'source_vchroot_links':p.get('source_vchroot_links'),
          'source_global_fsevents':p.get('source_global_fsevents'),
          'source_global_fsevents_framework':p.get('source_global_fsevents_framework'),
          'source_corpse_map_errors':p.get('source_corpse_map_errors'),
          'corpse_map_selected_runtime':p.get('corpse_map_selected_runtime'),
          'source_recursive_history_fsevents':p.get('source_recursive_history_fsevents'),
          'original_swb_swift_logging':p.get('original_swb_swift_logging'),
          'swb_swift_logging_selected_runtime':p.get('swb_swift_logging_selected_runtime'),
          'original_swb_logging':p.get('original_swb_logging'),
          'swb_logging_selected_runtime':p.get('swb_logging_selected_runtime'),
          'original_system_version':p.get('original_system_version'),
          'system_version_selected_runtime':p.get('system_version_selected_runtime'),
          'original_icu_data':p.get('original_icu_data'),
          'icu_data_selected_runtime':p.get('icu_data_selected_runtime'),
          'source_fatal_signal':p.get('source_fatal_signal'),
          'fatal_signal_selected_runtime':p.get('fatal_signal_selected_runtime'),
          'source_mobileasset_query':p.get('source_mobileasset_query'),
          'source_materialize_policy':p.get('source_materialize_policy'),
          'materialize_selected_runtime':p.get('materialize_selected_runtime'),
          'xpc_activation_selected_runtime':p.get('xpc_activation_selected_runtime'),
          's2c_selected_runtime':p.get('s2c_selected_runtime'),
          'legacy_volume_API_prewarm_used':False,
          'distnoted_protocol_execution_verified': False,
          'service_logs': {j['job']['StandardOutPath'].removeprefix(guest):digest(j['job']['StandardOutPath'].removeprefix(guest)) for j in jobs},
          'runtime_namespace_script_sha256': digest('scripts/runtime-ns.sh'),
          'full_xcode_build_ready': False, 'signing_ready': False}
if args.launchd_sandbox:record['source_launchd_sandbox']=p['source_launchd_sandbox']
if args.sandbox_fs:record['source_sandbox_fs']=p['source_sandbox_fs']
if args.mount_flags:record['source_mount_flags']=p['source_mount_flags']
if args.iokitd_matching:record['source_iokitd_matching']=p['source_iokitd_matching']
if args.iokitd_power:record['source_iokitd_power']=p['source_iokitd_power']
if args.log_compose:record['source_log_compose']=p['source_log_compose']
if args.fsevents_device:record.update(source_fsevents_device=p['source_fsevents_device'],probe_configuration=json.loads(json.dumps(vars(args),default=str)))
(root / ('artifacts/' + stem + '.json')).write_text(json.dumps(record, indent=2) + '\n')
raise SystemExit(result.returncode)
