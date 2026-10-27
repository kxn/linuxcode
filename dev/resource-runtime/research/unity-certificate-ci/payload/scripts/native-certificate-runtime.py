#!/usr/bin/env python3
"""Compose the proven headless native certificate client and daemon scopes."""
from pathlib import Path
import hashlib
import json
import plistlib
import runpy
import shlex
import tempfile

r = Path(__file__).resolve().parent.parent
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(r))


def select(profile, candidate_path, identity_store):
    candidate = json.loads((r / candidate_path).read_text())
    inputs = candidate['inputs']
    for row in inputs.values(): assert sha(r / row['path']) == row['sha256']
    assert profile['private_procfs_stage'] == inputs['stage']['path']
    assert profile['direct_resource_environment']['configuration'] == inputs['configuration']['path']
    store = (r / identity_store).resolve(strict=True)
    assert store.is_relative_to(r / 'runtime')
    folder = Path(tempfile.mkdtemp(prefix='native-certificate-session-', dir=r / 'runtime'))
    folder.chmod(0o700)
    command = list(profile['command'])
    normal = dict(v.split('=', 1) for v in command if v.startswith(('DYLD_LIBRARY_PATH=', 'DYLD_FRAMEWORK_PATH=')))
    resolve = runpy.run_path(str(r / 'scripts/resolve-evidence-history.py'))['resolve']
    def scope(key):
        stage = json.loads((r / inputs[key]['path']).read_text())
        for name, digest in stage['files'].items(): resolve(name, digest)
        return {env: guest(r / stage['root'] / leaf) + ':' + normal[env]
                for env, leaf in [('DYLD_LIBRARY_PATH', 'libraries'), ('DYLD_FRAMEWORK_PATH', 'frameworks')]}
    client = scope('identity_stage')
    daemon = {**scope('trustd_identity_stage'), 'LINUXCODE_IDENTITY_STORE': guest(store), 'LINUXCODE_IDENTITY_TRACE': '1'}
    for key, value in {**client, 'LINUXCODE_IDENTITY_STORE': guest(store)}.items():
        index = next(i for i, arg in enumerate(command) if arg.startswith(key + '='))
        command[index] = key + '=' + value
    build = json.loads((r / inputs['securityd_build']['path']).read_text())
    assert build['full_securityd_source_build']
    for key in ['binary', 'backend']: assert sha(r / build[key]) == build[key + '_sha256']
    ctl = guest(r / inputs['launchctl']['path'])
    jobs = []; startup = []; cleanup = []
    for name in ['LaunchDaemons/com.apple.securityd.plist', 'LaunchDaemons/com.apple.trustd.plist', 'LaunchAgents/com.apple.trustd.agent.plist']:
        template = r / 'runtime/rootfs/usr/libexec/darling/System/Library' / name
        job = plistlib.loads(template.read_bytes()); label = job['Label']; env = dict(daemon)
        if label == 'com.apple.securityd':
            job['ProgramArguments'][0] = guest(r / build['binary'])
            env['DYLD_LIBRARY_PATH'] = guest((r / build['backend']).parent) + ':' + env['DYLD_LIBRARY_PATH']
        job['EnvironmentVariables'] = {**job.get('EnvironmentVariables', {}), **env}
        job.pop('LimitLoadToSessionType', None); job.pop('UserName', None); job['RunAtLoad'] = True
        job['ProgramArguments'] = ['/usr/bin/env', *[k + '=' + v for k, v in env.items()], *job['ProgramArguments']]
        job['StandardOutPath'] = job['StandardErrorPath'] = guest(folder / (label + '.log'))
        path = folder / (label + '.plist'); path.write_bytes(plistlib.dumps(job)); path.chmod(0o644)
        startup.extend([shlex.join([ctl, 'remove', label]) + ' || true', shlex.join([ctl, 'load', guest(path)]),
                        shlex.join([ctl, 'start', label]), shlex.join([ctl, 'list', label])])
        cleanup.append(shlex.join([ctl, 'remove', label]) + ' >/dev/null 2>&1')
        jobs.append(dict(path=str(path.relative_to(r)), sha256=sha(path), label=label,
                         template=str(template.relative_to(r)), template_sha256=sha(template)))
    evidence = dict(candidate=candidate_path, candidate_sha256=sha(r / candidate_path),
                    identity_store=str(store.relative_to(r)), jobs=jobs,
                    self_generated_identity_only=True, developer_provisioning_verified=False,
                    startup='\n'.join(startup) + '\n', cleanup='; '.join(reversed(cleanup)))
    (folder / 'prepared.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return {**profile, 'command': command, 'native_certificate_runtime': evidence}
