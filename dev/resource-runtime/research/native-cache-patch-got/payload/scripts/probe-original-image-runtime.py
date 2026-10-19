#!/usr/bin/env python3
"""Load one pinned original image under the resource environment, independently of actool."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-stage', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--target', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='original-image-runtime-', dir=root/'runtime'))
sha = lambda p: hashlib.sha256((root/p).read_bytes()).hexdigest()
pin = json.loads((root/'config/coregraphics-image-pins.json').read_text())[args.target]
candidate = 'runtime/rebuilt-' + args.target + '/' + Path(pin['path']).name
reconstruction = str(Path(candidate).with_name('reconstruction.json'))
report = json.loads((root/reconstruction).read_text())
assert sha('runtime/fullsystem-libraries'+pin['path']) == pin['sha256'] == report['original_image_sha256']
assert sha(candidate) == report['staged_image_sha256']
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p = module['profile'](stage=args.runtime_stage, configuration=args.configuration)
command = list(p['command'][:-2])
for key, value in p['direct_resource_environment']['tool_environment'].items():
    indexes = [i for i, item in enumerate(command) if item.startswith(key+'=')]
    assert len(indexes) == 1
    command[indexes[0]] = key+'='+value
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = 'fixtures/hello/native-foundation-load.c'
object_file, binary = folder/'load.o', folder/'load'
build_commands = [
    ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O2',
     '-c', str(root/source), '-o', str(object_file)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
     '-syslibroot', str(sdk), '-lSystem', str(object_file), '-o', str(binary)]]
for build_command in build_commands: subprocess.run(build_command, check=True)
probe = str(binary.relative_to(root))
command += ['/Volumes/SystemRoot/workspace/'+probe, '/Volumes/SystemRoot/workspace/'+candidate]
command[3] = '90'
env = module['environment'](p)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']: env.pop(name, None)
log = folder/'load.log'
with log.open('w') as out:
    result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
text = log.read_text()
verified = result.returncode == 0 and 'NATIVE_FOUNDATION_PROBE_MAIN_ENTERED' in text and 'NATIVE_FOUNDATION_DLOPEN_COMPLETED' in text
record = dict(target=args.target, command=command, outer_status=result.returncode,
    build_commands=build_commands,
    dlopen_completed=verified, arbitrary_function_behavior_verified=False,
    original_resource_compilation_verified=False, runtime_stage=args.runtime_stage,
    configuration=args.configuration, log=str(log.relative_to(root)), log_sha256=sha(log),
    files={name: sha(name) for name in [str(Path(__file__).relative_to(root)),
        'fixtures/hello/native-foundation-load.c', probe, candidate, reconstruction,
        'scripts/direct-resource-tool-runtime-profile.py', args.runtime_stage, args.configuration]})
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text[-2500:])
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if verified else 1)
