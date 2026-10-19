#!/usr/bin/env python3
"""Materialize a pinned Unity export and an original AFNetworking Pod in a fresh directory."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert re.fullmatch(r'[a-zA-Z0-9]+', args.tag)
config_path = root / 'config/unity-ios-cocoapods-project.json'
config = json.loads(config_path.read_text())
folder = root / ('runtime/unity-ios-cocoapods-' + args.tag)
report = root / ('artifacts/unity-ios-cocoapods-' + args.tag + '-project.json')
assert not folder.exists() and not report.exists()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
unity = root / config['unity']['checkout']
assert subprocess.check_output(['git', '-C', str(unity), 'rev-parse', 'HEAD'], text=True).strip() == config['unity']['commit']
engine = root / config['engine']['source']
assert engine.stat().st_size == config['engine']['bytes'] and sha(engine) == config['engine']['sha256']
dependency = root / config['pod']['checkout']
if not dependency.exists():
    dependency.mkdir()
    subprocess.run(['git', '-C', str(dependency), 'init', '-q'], check=True)
    subprocess.run(['git', '-C', str(dependency), 'fetch', '--depth', '1', config['pod']['repository'], config['pod']['commit']], check=True)
    subprocess.run(['git', '-C', str(dependency), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
assert subprocess.check_output(['git', '-C', str(dependency), 'rev-parse', 'HEAD'], text=True).strip() == config['pod']['commit']
assert not subprocess.check_output(['git', '-C', str(dependency), 'status', '--porcelain'], text=True).strip()
folder.mkdir()

def export(repo, commit, destination, subdirectory=None):
    archive = folder / (destination.name + '-input.tar')
    command = ['git', '-C', str(repo), 'archive', '--format=tar', commit]
    if subdirectory:
        command.append(subdirectory)
    with archive.open('wb') as out:
        subprocess.run(command, stdout=out, check=True)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter='data')
    return dict(command=command, archive=str(archive.relative_to(root)), sha256=sha(archive))

unity_export = export(unity, config['unity']['commit'], folder, config['unity']['subdirectory'])
project = folder / config['unity']['subdirectory']
before = {str(path.relative_to(project)): sha(path) for path in project.rglob('*') if path.is_file()}
destination = project / config['engine']['destination']
pointer = destination.read_text()
assert pointer.startswith('version https://git-lfs.github.com/spec/v1\n')
assert 'oid sha256:' + config['engine']['sha256'] in pointer
assert 'size ' + str(config['engine']['bytes']) in pointer
shutil.copy2(engine, destination)
assert sha(destination) == config['engine']['sha256']
pod = project / config['pod']['destination']
pod_export = export(dependency, config['pod']['commit'], pod)
podspec = pod / 'AFNetworking.podspec'
assert "s.version  = '4.0.1'" in podspec.read_text()
podfile = project / 'Podfile'
assert not podfile.exists()
podfile.write_text("platform :ios, '13.0'\n"
    "source 'file:///Volumes/SystemRoot/workspace/fixtures/CocoaPodsSmoke/LocalSpecs'\n"
    "project 'Unity-iPhone.xcodeproj'\n"
    "target 'UnityFramework' do\n"
    "  pod 'AFNetworking', :path => 'Dependencies/AFNetworking'\n"
    "end\n")
after = {name: sha(project / name) for name in before}
assert {name for name in before if before[name] != after[name]} == {config['engine']['destination']}
pbx = project / 'Unity-iPhone.xcodeproj/project.pbxproj'
record = dict(verified=True, project=str(project.relative_to(root)),
    config=str(config_path.relative_to(root)), config_sha256=sha(config_path),
    unity=config['unity'], engine=config['engine'], pod=config['pod'],
    unity_export=unity_export, pod_export=pod_export, original_project_files=before,
    original_project_bytes_modified=False, LFS_materialized_and_verified=True,
    pbx_before_pods_sha256=sha(pbx), podfile_sha256=sha(podfile), podspec_sha256=sha(podspec),
    sources={str(path.relative_to(root)): sha(path) for path in [Path(__file__), config_path]},
    CocoaPods_installation_verified=False, full_App_build_verified=False)
report.write_text(json.dumps(record, indent=2) + '\n')
print('PREPARED_PROJECT', project)
print('EVIDENCE', report)
