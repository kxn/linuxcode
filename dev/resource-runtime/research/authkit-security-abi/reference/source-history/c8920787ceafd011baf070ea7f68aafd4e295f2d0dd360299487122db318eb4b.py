#!/usr/bin/env python3
"""Exercise actual restored original Security TLVs without calling authentication APIs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--target', required=True)
parser.add_argument('--objc-print-class-setup', action='store_true')
args = parser.parse_args()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
config = json.loads((root/args.configuration).read_text())
overlay = json.loads((root/config['resource_overlay_stage']).read_text())
assert overlay['original_security_target'] == args.target
candidate = 'runtime/rebuilt-'+args.target+'/Security'
report = json.loads((root/('runtime/rebuilt-'+args.target+'/reconstruction.json')).read_text())
assert sha(candidate) == report['staged_image_sha256']
rows = report['optimized_tlv_restoration']
assert len(rows) == 2 and {row['template_size'] for row in rows} == {64}
image = root/'runtime/fullsystem-libraries/System/Library/Frameworks/Security.framework/Versions/A/Security'
inspection = runpy.run_path(str(root/'scripts/inspect-preserved-patch-got.py'))
segments, _, _ = inspection['macho'](image.read_bytes())
base = next(row[1] for row in segments if row[0] == '__TEXT')
library = overlay['frameworks']+'/Security.framework/Versions/A/Security'
assert sha(library) == report['staged_image_sha256']
folder = Path(tempfile.mkdtemp(prefix='original-security-tlv-', dir=root/'runtime'))
executable = folder/'security-tlv'
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
    '-c', str(root/'fixtures/hello/security-tlv.c'), '-o', str(folder/'probe.o')], check=True)
subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-syslibroot', str(root/'runtime/rootfs/usr/libexec/darling'), '-lSystem',
    str(folder/'probe.o'), '-o', str(executable)], check=True)
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
scope = profile['direct_resource_environment']['tool_environment']
arguments = ['/Volumes/SystemRoot/workspace/'+str(executable.relative_to(root)),
             '/Volumes/SystemRoot/workspace/'+library]
for row in rows:
    arguments += [hex(int(row['slot'], 16)-base), str(row['variable_offset'])]
arguments.append('64')
script = folder/'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
    ('export OBJC_PRINT_CLASS_SETUP=YES\n' if args.objc_print_class_setup else '')+
    shlex.join(arguments)+'\nstatus=$?\nprintf "SECURITY_TLV_STATUS %s\\n" "$status"\nexit "$status"\n')
command = profile['command'][:-2]+[name+'='+scope[name] for name in ['DYLD_FRAMEWORK_PATH', 'DYLD_LIBRARY_PATH']]+[
    '/bin/bash', '/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
command[3] = '90'
environment = module['environment'](profile)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']: environment.pop(name, None)
log = folder/'run.log'
with log.open('w') as stream:
    result = subprocess.run(command, cwd=root, env=environment, stdout=stream, stderr=subprocess.STDOUT)
text = log.read_text()
statuses = re.findall(r'^SECURITY_TLV_STATUS (\d+)$', text, re.M)
verified = (result.returncode == 0 and statuses == ['0'] and
    'ORIGINAL_SECURITY_TLS_VERIFIED threads=4 descriptors=2 queries=2048 zero_fill=64' in text and
    '/'+library in text)
record = dict(verified=verified, target=args.target, configuration=args.configuration,
    candidate_sha256=sha(candidate), library=library, outer_status=result.returncode,
    native_status=statuses, command=command, actual_security_TLV_only=True,
    original_authentication_API_behavior_verified=False, log=str(log.relative_to(root)),
    log_sha256=sha(log.relative_to(root)), sources={name:sha(name) for name in [
        'fixtures/hello/security-tlv.c', 'scripts/probe-original-security-tlv.py']})
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text[-3500:])
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if verified else 1)
