from pathlib import Path
import hashlib,json,shlex,subprocess
root=Path.cwd();folder=Path('runtime/common-services-unwind-gate-4b6dxxvp');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda name:'/Volumes/SystemRoot/workspace/'+name
build=json.loads((folder/'build-preparation.json').read_text());store=json.loads(Path('artifacts/diskarbitration-service-no-daemon-store-notification.json').read_text());null=json.loads(Path('runtime/managed-implicit-null-v15/result.json').read_text())
assert sha(Path(store['source']))==store['source_sha256'];assert sha(Path(store['binary']))==store['binary_sha256']
for name,digest in null['files'].items():
 if name.endswith(('ManagedImplicitNullSmoke.cs','ManagedImplicitNullSmoke.exe','libcoreclr.dylib')) or name=='runtime/unity-coreclr-mutex-68waptyq/probe':assert sha(Path(name))==digest
runtime='runtime/unity-macos-editor-6000.3.27f1-v1/Unity/Unity.app/Contents/Helpers/UnityLicensingClient.app/Contents/MacOS'
walk='runtime/unwind-sections-smoke-v13/probe';walk_bytes=Path(walk).read_bytes()
for marker in [b'UNWIND_SECTIONS_BEGIN',b'UNWIND_SECTIONS_AND_STATIC_WALK_OK',b'UNWIND_STATIC_FRAMES']:assert marker in walk_bytes
phases=[
 dict(name='diskarbitration',command=[guest(build['built']['diskarbitration'])],expected=['DA_SESSION_READY_NATIVE_OK'],source='fixtures/hello/diskarbitration-session-ready.c',source_provenance='Fresh micro-TU build: older da-client had no source-to-binary build record',recompiled=True),
 dict(name='systemconfiguration',command=[guest(store['binary'])],expected=['NATIVE_SYSTEMCONFIGURATION_REAL_CONFIGD_STORE_AND_NOTIFICATION_OK checks=16'],source=store['source'],source_provenance='Exact source and binary SHA match prior genuine store/notification result',evidence='artifacts/diskarbitration-service-no-daemon-store-notification.json',recompiled=False),
 dict(name='static-unwind-walk',command=[guest(walk)],expected=['UNWIND_ANONYMOUS_RECOGNIZED 0','UNWIND_SECTIONS_AND_STATIC_WALK_OK'],source='fixtures/hello/unwind-sections-smoke.cpp',source_provenance='Existing v13 successful binary reused and hash pinned now; historical result lacks build-source hash, current source/expected binary markers separately recorded',evidence='runtime/unwind-sections-smoke-v13/result.json',recompiled=False),
 dict(name='native-exceptions',command=[guest(build['built']['exceptions'])],expected=['UNWIND_CPP_AND_FOUNDATION_EXCEPTION_DESTRUCTORS_OK checks=4'],source='fixtures/hello/unwind-exceptions-smoke.mm',source_provenance='New self-owned ordinary C++ and Foundation NSException fixture',recompiled=True),
 dict(name='managed-implicit-null',command=[guest('runtime/unity-coreclr-mutex-68waptyq/probe'),guest(runtime),guest('runtime/managed-implicit-null-v15/ManagedImplicitNullSmoke.exe')],expected=['IMPLICIT_NULL_CAUGHT_WITH_JIT_STACK main-thread','IMPLICIT_NULL_CAUGHT_WITH_JIT_STACK threadpool','IMPLICIT_NULL_MACH_EXCEPTION_RESTORE_OK'],source='fixtures/hello/ManagedImplicitNullSmoke.cs',source_provenance='Exact source, assembly, original host and original runtime SHA match v15 proof',evidence='runtime/managed-implicit-null-v15/result.json',recompiled=False),
]
lines=['#!/bin/bash','set -euo pipefail','ulimit -c 0','run_phase() {','    phase=$1; shift','    printf "SVC_UNWIND_GATE_PHASE_BEGIN %s\\n" "$phase"','    if "$@"; then','        printf "SVC_UNWIND_GATE_PHASE_STATUS %s 0\\n" "$phase"','    else','        status=$?','        printf "SVC_UNWIND_GATE_PHASE_STATUS %s %s\\n" "$phase" "$status"','        exit "$status"','    fi','}']
for phase in phases:lines.append(shlex.join(['run_phase',phase['name'],*phase['command']]))
lines.append('printf "SVC_UNWIND_GATE_COMPLETE phases=5\\n"');script=folder/'guest.sh';script.write_text('\n'.join(lines)+'\n');subprocess.run(['bash','-n',str(script)],check=True)
files={str(script):sha(script),'fixtures/hello/original-coreclr-host.c':sha(Path('fixtures/hello/original-coreclr-host.c')),str(folder/'build-preparation.json'):sha(folder/'build-preparation.json'),runtime+'/libcoreclr.dylib':sha(Path(runtime)/'libcoreclr.dylib')}
for phase in phases:
 for name in [phase['source'],*[p.split('/workspace/',1)[1] for p in phase['command'] if p.startswith('/Volumes/SystemRoot/workspace/') and Path(p.split('/workspace/',1)[1]).is_file()]]:
  files[name]=sha(Path(name))
 if 'evidence' in phase:files[phase['evidence']]=sha(Path(phase['evidence']))
r=dict(prepared=True,native_execution_attempted=False,source_or_library_configuration_modified=False,service_builder_repeated=False,bootstrap_invocations=1,fail_fast=True,run_timeout_seconds=45,kill_grace_seconds=2,default_unwind_trace='No libunwind guest flag is enabled by this gate. The runner defaults whole-run host controls to 0 only when unset.',phases=phases,guest_script=str(script),files=files,build_commands=build['commands'],recompiled_translation_units=2,reused_native_binaries=2,reused_managed_assembly=True,source_truth_note='Static section/walk validation and actual exception throws are separate phases. No claim that unwind-sections-smoke.cpp throws.',no_external_debugger=True,no_other_process_memory_access=True,no_license_business_assembly_execution=True)
(folder/'prepared.json').write_text(json.dumps(r,indent=2)+'\n');print(folder/'prepared.json')
