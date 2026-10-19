#!/usr/bin/env python3
"""Run original Darwin CocoaPods on the materialized Unity export and inspect its project changes."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project-report', required=True)
parser.add_argument('--stage', default='artifacts/private-procfs-v5-stage.json')
args = parser.parse_args()
prepared = json.loads((root / args.project_report).read_text())
assert prepared['verified'] and prepared['LFS_materialized_and_verified']
project = root / prepared['project']
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
pbx = project / 'Unity-iPhone.xcodeproj/project.pbxproj'
assert sha(pbx) == prepared['pbx_before_pods_sha256']
assert not (project / 'Pods').exists()
folder = Path(tempfile.mkdtemp(prefix='unity-ios-pod-install-', dir=root / 'runtime'))
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
inspector = root / 'scripts/inspect-unity-pods-project.rb'
script = folder / 'run.sh'
before, after, pods = [folder / (name+'.json') for name in ['before', 'after', 'pods']]
script.write_text('#!/bin/bash\nset -e\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
    'cd ' + shlex.quote(guest(project)) + '\n' +
    shlex.join(['/usr/bin/ruby', guest(inspector), guest(pbx.parent), guest(before)]) + '\n' +
    'set +e\npod install --no-repo-update\nstatus=$?\nprintf "UNITY_POD_INSTALL_STATUS %s\\n" "$status"\n' +
    'if [ "$status" -ne 0 ]; then exit "$status"; fi\nset -e\n' +
    shlex.join(['/usr/bin/ruby', guest(inspector), guest(pbx.parent), guest(after)]) + '\n' +
    shlex.join(['/usr/bin/ruby', guest(inspector), guest(project / 'Pods/Pods.xcodeproj'), guest(pods)]) + '\n')
module = runpy.run_path(str(root / 'scripts/private-procfs-runtime-profile.py'))
p = module['profile'](stage=args.stage)
# Ruby retains its matched system libraries; the Xcode-specific framework set
# remains scoped to Xcode's process tree as in the previous real pod fixture.
command = [arg for arg in p['command'][:-2] if not arg.startswith(('DYLD_LIBRARY_PATH=', 'DYLD_FRAMEWORK_PATH='))] + ['/bin/bash', guest(script)]
command[3] = '300'
env = module['environment'](p)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(name, None)
with (folder / 'run.log').open('w') as out:
    result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
text = (folder / 'run.log').read_text()
files = [project / name for name in ['Podfile', 'Podfile.lock', 'Pods/Manifest.lock', 'Pods/Pods.xcodeproj/project.pbxproj',
    'Unity-iPhone.xcodeproj/project.pbxproj', 'Unity-iPhone.xcworkspace/contents.xcworkspacedata']]
metadata_error = None
preserved = False
pod_sources = []
try:
    original = json.loads(before.read_text())['targets']
    integrated = {row['uuid']: row for row in json.loads(after.read_text())['targets']}
    for target in original:
        selected = integrated[target['uuid']]
        assert target['name'] == selected['name'] and target['product_type'] == selected['product_type']
        assert set(target['sources']).issubset(selected['sources'])
        phases = {row['uuid']: row['script_sha256'] for row in selected['shell_phases']}
        assert all(phases.get(row['uuid']) == row['script_sha256'] for row in target['shell_phases'])
    pod_target = next(row for row in json.loads(pods.read_text())['targets'] if row['name'] == 'AFNetworking')
    pod_sources = pod_target['sources']
    assert any('AFURLSessionManager.m' in name for name in pod_sources)
    assert (project / 'Podfile.lock').read_bytes() == (project / 'Pods/Manifest.lock').read_bytes()
    assert 'AFNetworking (4.0.1)' in (project / 'Podfile.lock').read_text()
    preserved = True
except (OSError, ValueError, AssertionError, KeyError, StopIteration) as error:
    metadata_error = str(error) or type(error).__name__
changed = [name for name, digest in prepared['original_project_files'].items()
    if name != prepared['engine']['destination'] and (not (project / name).is_file() or sha(project / name) != digest)]
assert all(name.startswith('Unity-iPhone.xcodeproj/') for name in changed), changed
verified = result.returncode == 0 and re.findall(r'^UNITY_POD_INSTALL_STATUS (\d+)$', text, re.M) == ['0'] and preserved and all(path.is_file() for path in files)
record = dict(verified=verified, project_report=args.project_report, project=prepared['project'], runtime_stage=args.stage,
    command=command, outer_status=result.returncode, original_targets_sources_and_shell_scripts_preserved=preserved,
    CocoaPods_generated_project_changes=changed, metadata_error=metadata_error, AFNetworking_sources=pod_sources,
    original_Unity_App_build_verified=False, Ruby_Xcode_framework_overrides=False,
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), inspector, root / args.project_report, root / args.stage, *files, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text[-6000:], 'EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
