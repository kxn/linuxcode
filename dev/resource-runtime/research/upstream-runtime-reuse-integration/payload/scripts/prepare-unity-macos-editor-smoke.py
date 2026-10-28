#!/usr/bin/env python3
"""Prepare (by default), or explicitly run, isolated original Mac Unity smoke gates."""
from pathlib import Path
import argparse, hashlib, json, os, re, runpy, shlex, shutil, subprocess, tempfile, time
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
    configuration = folder / 'resource-configuration.json'
    config['executables'] = list(dict.fromkeys([*config['executables'], guest(editor)]))
    configuration.write_text(json.dumps(config, indent=2) + '\n')
    relative_config = str(configuration.relative_to(ROOT))
    module, selected = profile(args.stage, relative_config)
    project = folder / 'project'
    fixture = ROOT / 'fixtures/UnityExportSmoke'
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
    guards = {str(path.relative_to(ROOT)): sha(path) for path in [HELPER, base, ROOT / args.stage, extraction, editor, configuration, *folder.glob('*-guest.sh'), *fixture.rglob('*')] if path.is_file()}
    record = dict(prepared=True, scope='Original macOS Intel Unity Editor only; no Linux licensing/export result inherited',
                  installation=str(install.relative_to(ROOT)), editor=str(editor.relative_to(ROOT)), editor_sha256=sha(editor),
                  stage=args.stage, configuration=relative_config, baseline_configuration=args.configuration,
                  source_runtime=selected['source_runtime'], tool_environment=selected['direct_resource_environment']['tool_environment'],
                  project=str(project.relative_to(ROOT)), export=str((folder / 'ios').relative_to(ROOT)), cases=cases, guards=guards,
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
        prior = json.loads((folder / (previous + '-result.json')).read_text())
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
    started = time.monotonic()
    with outer_log.open('w') as stream:
        process = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    text = outer_log.read_text(errors='replace')
    editor_log = folder / (case + '-Editor.log')
    combined = text + (editor_log.read_text(errors='replace') if editor_log.exists() else '')
    native = re.findall(r'^LINUXCODE_MACOS_EDITOR_STATUS (\d+)$', text, re.M)
    marker = {'version':'6000.3.27f1', 'batchmode':'LINUXCODE_MACOS_EDITOR_BATCHMODE_SUCCEEDED 6000.3.27f1', 'export':'LINUXCODE_UNITY_IOS_EXPORT_SUCCEEDED 6000.3.27f1'}[case]
    observed = bool(re.search(r'^6000\.3\.27f1(?:\s+\([0-9a-f]+\))?\s*$', combined, re.M)) if case == 'version' else marker in combined
    passed = process.returncode == 0 and native == ['0'] and observed
    result = dict(case=case, outer_status=process.returncode, native_status=native, expected_marker_observed=observed,
                  gate_passed=passed, elapsed_seconds=time.monotonic()-started, command=command,
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
    parser.add_argument('--run-prepared', type=Path)
    parser.add_argument('--case', choices=('version','batchmode','export'))
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
