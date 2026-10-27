#!/usr/bin/env python3
"""Verify extracted RSA/P256 keys using independent OpenSSL signatures."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shlex, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--helper-build', required=True)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='coretls-modern-peer-key-', dir=root / 'runtime')); folder.chmod(0o700)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
guest = lambda p: '/Volumes/SystemRoot/workspace/' + str(p.relative_to(root))
build = json.loads((root / args.helper_build).read_text())
assert build['full_coretls_cfhelpers_source_build'] and sha(root / build['library']) == build['library_sha256']
tls = json.loads((root / build['coretls_build']).read_text())
content = folder / 'content.bin'; content.write_bytes(b'Independent OpenSSL signatures for the source CoreTLS peer certificate key')
with (folder / 'digest.bin').open('wb') as stream:
    subprocess.run(['openssl', 'dgst', '-sha256', '-binary', str(content)], stdout=stream, check=True)
for name, algorithm in [('rsa', ['-newkey', 'rsa:2048']), ('ec', ['-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256'])]:
    key, certificate = folder / (name + '.key'), folder / (name + '.pem')
    subprocess.run(['openssl', 'req', '-x509', *algorithm, '-nodes', '-keyout', str(key), '-out', str(certificate),
                    '-subj', '/CN=CoreTLS peer key fixture', '-days', '2'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    key.chmod(0o600)
    subprocess.run(['openssl', 'x509', '-in', str(certificate), '-outform', 'DER', '-out', str(folder / (name + '.der'))], check=True)
    subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key), '-out', str(folder / (name + '.sig')), str(content)], check=True)
source = root / 'fixtures/hello/coretls-modern-peer-key.c'
prototype = build['units'][0]['command']; flags = prototype[1:prototype.index('-MMD')]
flags = [x for x in flags if not x.startswith('-DNDEBUG')]
commands = [
    ['clang-19', *flags, '-DCCCBC_RETURN_INT', '-c', str(source), '-o', str(folder / 'test.o')],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot',
     str(root / 'runtime/rootfs/usr/libexec/darling'), '-lSystem', str(folder / 'test.o'), str(root / tls['backend']), '-o', str(folder / 'test')]]
with (folder / 'build.log').open('w') as stream:
    for command in commands: subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
command = list(profile['command']); scope = profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']:
    index = next(i for i, value in enumerate(command) if value.startswith(key + '=')); command[index] = key + '=' + scope[key]
profile = runpy.run_path(str(root / 'scripts/coretls-source-runtime-profile.py'))['select']({**profile, 'command': command}, build['coretls_build'])
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' + shlex.join([
    guest(folder / 'test'), guest(root / build['library']), guest(folder / 'digest.bin'),
    *[guest(folder / name) for name in ['rsa.der', 'rsa.sig', 'ec.der', 'ec.sig']]]) +
    '\ns=$?\nprintf "CORETLS_PEER_KEY_STATUS %s\\n" "$s"\nexit "$s"\n')
command = profile['command'][:-2] + ['/bin/bash', guest(script)]; command[3] = '70'
print('RUNNING', folder.relative_to(root), flush=True)
log = folder / 'run.log'
with log.open('w') as stream: result = subprocess.run(command, cwd=root, env=module['environment'](profile), stdout=stream, stderr=subprocess.STDOUT)
text = log.read_text(); statuses = re.findall(r'^CORETLS_PEER_KEY_STATUS (\d+)$', text, re.M)
verified = result.returncode == 0 and statuses == ['0'] and 'CORETLS_MODERN_PEER_KEYS_REAL_RSA_ECDSA_SIGNATURES_AND_MALFORMED_REJECTION_OK' in text
record = dict(verified=verified, outer_status=result.returncode, native_status=statuses, helper_build=args.helper_build,
              helper_build_sha256=sha(root / args.helper_build), stage=args.stage, configuration=args.configuration,
              commands=commands, command=command, log=str(log.relative_to(root)), log_sha256=sha(log),
              source_sha256=sha(source), driver_sha256=sha(Path(__file__)),
              independent_signature_generator='Host OpenSSL SHA256 RSA-PKCS1-v1.5 and P256 ECDSA',
              certificate_trust_evaluation_or_completed_TLS_handshake_verified=False, full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(text[-2400:]); print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
