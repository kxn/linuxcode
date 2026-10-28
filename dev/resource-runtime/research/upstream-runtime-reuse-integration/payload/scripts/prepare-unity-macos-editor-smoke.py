#!/usr/bin/env python3
"""Prepare (by default), or explicitly run, isolated original Mac Unity smoke gates."""
from pathlib import Path
import argparse, hashlib, json, os, pwd, re, runpy, shlex, shutil, subprocess, tempfile, time
ROOT = Path(__file__).resolve().parent.parent
HELPER = Path(__file__).resolve()

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def guest(path):
    return '/Volumes/SystemRoot/workspace/' + str(path.resolve().relative_to(ROOT))

def profile(stage, configuration):
    module = runpy.run_path(str(ROOT / 'scripts/direct-resource-tool-runtime-profile.py'))
    return module, module['profile'](stage=stage, configuration=configuration)

def prepare(args):
    install = args.installation.resolve(strict=True)
    extraction = install / 'extraction.json'
    evidence = json.loads(extraction.read_text())
    assert evidence['host_payload_extraction_verified'] and not evidence['editor_launched']
    editor = Path(evidence['editor']).resolve(strict=True)
    assert editor.is_relative_to(install) and sha(editor) == evidence['editor_sha256']
    base = ROOT / args.configuration
    config = json.loads(base.read_text())
    folder = Path(tempfile.mkdtemp(prefix='unity-macos-editor-smoke-', dir=ROOT / 'runtime'))
    if config.get('runtime_mode') == 'unified':
        configuration = base  # Reuse the common system configuration unchanged.
    else:
        configuration = folder / 'resource-configuration.json'
        config['executables'] = list(dict.fromkeys([*config['executables'], guest(editor)]))
        configuration.write_text(json.dumps(config, indent=2) + '\n')
    relative_config = str(configuration.relative_to(ROOT))
    module, selected = profile(args.stage, relative_config)
    fixture = ROOT / 'fixtures/UnityExportSmoke'
    reused_project = None
    if args.reuse_project_from:
        previous_path = args.reuse_project_from.resolve(strict=True)
        previous = json.loads(previous_path.read_text())
        assert previous['editor_sha256'] == sha(editor) and previous['editor'] == str(editor.relative_to(ROOT))
        project = (ROOT / previous['project']).resolve(strict=True)
        assert project.is_relative_to(ROOT / 'runtime') and not (ROOT / previous['project']).is_symlink()
        for source in fixture.rglob('*'):
            if source.is_file():
                assert sha(project / source.relative_to(fixture)) == sha(source), 'Existing project fixture changed'
        smoke = project / 'Assets/Editor/MacOSSmoke.cs'
        assert 'LINUXCODE_MACOS_EDITOR_BATCHMODE_SUCCEEDED ' in smoke.read_text()
        assert 'RuntimePlatform.OSXEditor' in smoke.read_text()
        reused_project = dict(prepared=str(previous_path.relative_to(ROOT)), prepared_sha256=sha(previous_path),
                              project=str(project.relative_to(ROOT)), caches_reused=True,
                              previous_managed_or_export_success_inherited=False)
    else:
        project = folder / 'project'
        shutil.copytree(fixture, project)
        (project / 'Packages').mkdir()
        (project / 'Packages/manifest.json').write_text('{"dependencies":{}}\n')
        (project / 'ProjectSettings').mkdir()
        (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.27f1\nm_EditorVersionWithRevision: 6000.3.27f1 (672d562a42a7)\n')
        (project / 'Assets/Editor/MacOSSmoke.cs').write_text('''using System;
using UnityEngine;
namespace Linuxcode.CI {
 public static class MacOSSmoke {
  public static void Run() {
   if (Application.platform != RuntimePlatform.OSXEditor) throw new InvalidOperationException("Original macOS Editor required");
   Debug.Log("LINUXCODE_MACOS_EDITOR_BATCHMODE_SUCCEEDED " + Application.unityVersion);
  }
 }
}
''')
    cases = {}
    for name in ('version', 'batchmode', 'export'):
        args_list = ['-version'] if name == 'version' else ['-batchmode', '-nographics', '-quit', '-projectPath', guest(project), '-executeMethod', 'Linuxcode.CI.MacOSSmoke.Run' if name == 'batchmode' else 'Linuxcode.CI.IOSExport.Run', '-logFile', guest(folder / (name + '-Editor.log'))]
        if name == 'export':
            args_list += ['-buildTarget', 'iOS']
        script = folder / (name + '-guest.sh')
        script.write_text('#!/bin/bash\nulimit -c 0\ncd ' + shlex.quote(guest(project)) + '\nexport LINUXCODE_UNITY_EXPORT_PATH=' + shlex.quote(guest(folder / 'ios')) + '\n' + shlex.join([guest(editor), *args_list]) + '\nstatus=$?\nprintf "LINUXCODE_MACOS_EDITOR_STATUS %s\\n" "$status"\nexit "$status"\n')
        cases[name] = dict(guest_script=str(script.relative_to(ROOT)), argv=[guest(editor), *args_list])
        runner = folder / ('run-' + name + '.sh')
        runner.write_text('#!/bin/bash\nset -euo pipefail\nexec ' + shlex.join(['python3', str(HELPER), '--run-prepared', str(folder / 'prepared.json'), '--case', name]) + '\n')
        runner.chmod(0o755)
    historical = None
    if args.prior_version_result:
        prior_path=args.prior_version_result.resolve(strict=True);prior=json.loads(prior_path.read_text());prior_prepared_path=prior_path.parent/'prepared.json';prior_prepared=json.loads(prior_prepared_path.read_text())
        assert prior['case']=='version' and prior['gate_passed'] and prior['outer_status']==0 and prior['native_status']==['0']
        assert prior_prepared['editor_sha256']==sha(editor) and prior_prepared['editor']==str(editor.relative_to(ROOT))
        historical=dict(path=str(prior_path.relative_to(ROOT)),sha256=sha(prior_path),prepared=str(prior_prepared_path.relative_to(ROOT)),prepared_sha256=sha(prior_prepared_path),same_original_editor_sha256=sha(editor),reexecuted_in_this_runtime=False)
    guards = {str(path.relative_to(ROOT)): sha(path) for path in [HELPER, base, ROOT / args.stage, extraction, editor, configuration, *folder.glob('*-guest.sh'), *fixture.rglob('*'), *project.glob('Assets/**/*.cs'), project/'Packages/manifest.json', project/'ProjectSettings/ProjectVersion.txt'] if path.is_file()}
    record = dict(prepared=True, scope='Original macOS Intel Unity Editor only; no Linux licensing/export result inherited',
                  installation=str(install.relative_to(ROOT)), editor=str(editor.relative_to(ROOT)), editor_sha256=sha(editor),
                  stage=args.stage, configuration=relative_config, baseline_configuration=args.configuration,
                  source_runtime=selected['source_runtime'], tool_environment=selected['direct_resource_environment']['tool_environment'],
                  project=str(project.relative_to(ROOT)), export=str((folder / 'ios').relative_to(ROOT)), cases=cases, guards=guards, historical_version_gate=historical, reused_project=reused_project,
                  configuration154_modified=False, original_fixture_modified=False, native_session_started=False,
                  macos_editor_batchmode_verified=False, macos_editor_licensing_verified=False, macos_editor_ios_export_verified=False)
    (folder / 'prepared.json').write_text(json.dumps(record, indent=2) + '\n')
    print(folder / 'prepared.json')

def run(args):
    path = args.run_prepared.resolve(strict=True)
    record = json.loads(path.read_text())
    for name, digest in record['guards'].items():
        assert sha(ROOT / name) == digest, 'Prepared input changed: ' + name
    folder = path.parent
    case = args.case
    # A version result is only a loader gate. Batchmode must run the managed marker.
    if case in ('batchmode', 'export'):
        previous = 'version' if case == 'batchmode' else 'batchmode'
        previous_path=folder/(previous+'-result.json')
        if previous=='version' and not previous_path.exists() and record.get('historical_version_gate'):
            history=record['historical_version_gate'];previous_path=ROOT/history['path'];assert sha(previous_path)==history['sha256'];assert sha(ROOT/history['prepared'])==history['prepared_sha256'];assert history['same_original_editor_sha256']==record['editor_sha256']
        prior = json.loads(previous_path.read_text())
        assert prior['gate_passed'], 'First establish preceding Editor smoke gate: ' + previous
    result_path = folder / (case + '-result.json')
    assert not result_path.exists(), 'One evidence record per case; prepare a fresh run for retries'
    module, selected = profile(record['stage'], record['configuration'])
    assert selected['source_runtime'] == record['source_runtime']
    assert selected['direct_resource_environment']['tool_environment'] == record['tool_environment']
    command = selected['command'][:-2] + ['/usr/bin/env', '-u', 'DISPLAY', '-u', 'WAYLAND_DISPLAY', '-u', 'XAUTHORITY', '/bin/bash', guest(ROOT / record['cases'][case]['guest_script'])]
    command[3] = str(args.timeout_seconds)
    environment = module['environment'](selected)
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
        environment.pop(key, None)
    outer_log = folder / (case + '-private-native.log')
    execution_command=command
    diagnostic_trace=None
    if args.trace_socket_io:
        tracer=ROOT/'runtime/tools/strace-package/unpacked/usr/bin/strace'
        assert tracer.is_file() and tracer.open('rb').read(4)==b'\x7fELF'
        trace=folder/(case+'-socket-private.strace');trace.touch(mode=0o600,exist_ok=False)
        calls='socket,socketpair,bind,connect,listen,accept,accept4,getsockopt,setsockopt,getsockname,getpeername,shutdown,fcntl,ioctl,poll,ppoll,select,pselect6,epoll_ctl,epoll_wait,epoll_pwait,read,write,readv,writev,sendto,recvfrom,sendmsg,recvmsg'
        raw='read,write,readv,writev,sendto,recvfrom,sendmsg,recvmsg'
        execution_command=['sudo','-n','-E',str(tracer),'-u',pwd.getpwuid(os.getuid()).pw_name,'-f','-ttt','-T','-s','160','-yy','-e','trace='+calls,'-e','raw='+raw,'-o',str(trace),*command]
        diagnostic_trace=dict(private_file=str(trace.relative_to(ROOT)),tracer=str(tracer.relative_to(ROOT)),tracer_sha256=sha(tracer),payload_syscalls_raw=raw.split(','),tracee_host_uid_preserved=os.getuid(),runtime_configuration_unchanged=True,publishable=False)
    # Preserve only the known UPM log as private evidence, never licensing data.
    # A common run has its own prefix; the old default prefix is not its log.
    upm_source = None
    upm_before = None
    configuration = json.loads((ROOT / record['configuration']).read_text())
    if configuration.get('run_launcher_stage'):
        run_stage = json.loads((ROOT / configuration['run_launcher_stage']).read_text())
        upm_source = ROOT / Path(run_stage['launcher']).parent / 'prefix/Users/root/Library/Logs/Unity/upm.log'
        if upm_source.is_file():
            upm_before = dict(sha256=sha(upm_source), bytes=upm_source.stat().st_size)
    started = time.monotonic()
    with outer_log.open('w') as stream:
        process = subprocess.run(execution_command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    if diagnostic_trace:
        diagnostic_trace['sha256']=sha(trace);diagnostic_trace['bytes']=trace.stat().st_size
    text = outer_log.read_text(errors='replace')
    editor_log = folder / (case + '-Editor.log')
    combined = text + (editor_log.read_text(errors='replace') if editor_log.exists() else '')
    native = re.findall(r'^LINUXCODE_MACOS_EDITOR_STATUS (\d+)$', text, re.M)
    marker = {'version':'6000.3.27f1', 'batchmode':'LINUXCODE_MACOS_EDITOR_BATCHMODE_SUCCEEDED 6000.3.27f1', 'export':'LINUXCODE_UNITY_IOS_EXPORT_SUCCEEDED 6000.3.27f1'}[case]
    observed = bool(re.search(r'^6000\.3\.27f1(?:\s+\([0-9a-f]+\))?\s*$', combined, re.M)) if case == 'version' else marker in combined
    passed = process.returncode == 0 and native == ['0'] and observed
    upm_evidence = None
    if upm_source and upm_source.is_file():
        upm_copy = folder / (case + '-UPM-private.log')
        shutil.copyfile(upm_source, upm_copy)
        upm_copy.chmod(0o600)
        upm_evidence = dict(private_file=str(upm_copy.relative_to(ROOT)), sha256=sha(upm_copy),
                            source=str(upm_source.relative_to(ROOT)), before=upm_before,
                            changed_during_run=not upm_before or sha(upm_copy) != upm_before['sha256'], publishable=False)
    result = dict(case=case, outer_status=process.returncode, native_status=native, expected_marker_observed=observed,
                  gate_passed=passed, elapsed_seconds=time.monotonic()-started, command=command, execution_command=execution_command, diagnostic_trace=diagnostic_trace, private_UPM_log=upm_evidence,
                  private_outer_log=str(outer_log.relative_to(ROOT)), private_outer_log_sha256=sha(outer_log),
                  private_editor_log=str(editor_log.relative_to(ROOT)) if editor_log.exists() else None,
                  logs_publishable=False, license_activation_requested_by_runner=False,
                  full_editor_startup_verified=case=='batchmode' and passed,
                  ios_export_verified=case=='export' and passed, App_build_verified=False)
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('case','outer_status','native_status','expected_marker_observed','gate_passed')}, indent=2))
    print(result_path)
    raise SystemExit(0 if passed else 1)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path)
    parser.add_argument('--stage')
    parser.add_argument('--configuration', default='config/direct-resource-tool-environment-v154.json')
    parser.add_argument('--reuse-project-from', type=Path, help='Reuse the explicit prior private Mac Editor project/cache without copying or inheriting its gate results')
    parser.add_argument('--prior-version-result',type=Path,help='Explicit historical version-only gate for this identical original Editor; never inherits managed/license/export status')
    parser.add_argument('--run-prepared', type=Path)
    parser.add_argument('--case', choices=('version','batchmode','export'))
    parser.add_argument('--trace-socket-io',action='store_true',help='Private syscall metadata; socket payload calls always raw, with the exact same shared runtime')
    parser.add_argument('--timeout-seconds', type=int, default=180)
    args = parser.parse_args()
    assert 1 <= args.timeout_seconds <= 7200
    if args.run_prepared:
        assert args.case
        run(args)
    else:
        assert args.installation and args.stage and not args.case
        prepare(args)

if __name__ == '__main__':
    main()
