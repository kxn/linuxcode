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


def select(profile, candidate_path, identity_store, *, prepare=True, session_directory=None):
    assert profile.get('direct_resource_environment', {}).get('runtime_mode') != 'unified', \
        'Legacy certificate client/daemon library scopes cannot be applied to a unified run'
    candidate = json.loads((r / candidate_path).read_text())
    inputs = candidate['inputs']
    for row in inputs.values(): assert sha(r / row['path']) == row['sha256']
    assert profile['private_procfs_stage'] == inputs['stage']['path']
    assert profile['direct_resource_environment']['configuration'] == inputs['configuration']['path']
    store = (r / identity_store).resolve(strict=True)
    assert store.is_relative_to(r / 'runtime') and store.is_file()
    assert not store.stat().st_mode & 0o077, 'local identity store must be private (mode 600)'
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
    trustd = None
    if 'trustd_build' in inputs:
        trustd = json.loads((r / inputs['trustd_build']['path']).read_text())
        assert trustd['full_trustd_source_build'] and trustd['ARC_for_all_ObjC_units']
        for key in ['binary', 'backend']: assert sha(r / trustd[key]) == trustd[key + '_sha256']
    for name, digest in candidate.get('service_templates', {}).items(): assert sha(r / name) == digest
    evidence = dict(candidate=candidate_path, candidate_sha256=sha(r / candidate_path),
                    identity_store=str(store.relative_to(r)), jobs=[], startup='', cleanup='',
                    identity_store_origin='caller-supplied read-only RSA identity store',
                    developer_provisioning_verified=False)
    selected = {**profile, 'command': command, 'native_certificate_runtime': evidence,
                '_certificate_daemon_environment': daemon, '_certificate_securityd_build': build,
                '_certificate_launchctl': inputs['launchctl']['path'], '_certificate_trustd_build': trustd}
    return prepare_services(selected, session_directory) if prepare else selected


def prepare_services(profile, session_directory=None, *, verbose=False):
    assert profile.get('direct_resource_environment', {}).get('runtime_mode') != 'unified', \
        'Unified services must inherit the common runtime without per-service library overrides'
    if session_directory is None:
        folder = Path(tempfile.mkdtemp(prefix='native-certificate-session-', dir=r / 'runtime'))
    else:
        folder = Path(session_directory).resolve()
        assert folder.is_relative_to(r / 'runtime')
        folder.mkdir(exist_ok=False)
    folder.chmod(0o700)
    evidence = dict(profile['native_certificate_runtime'])
    daemon = profile['_certificate_daemon_environment']
    build = profile['_certificate_securityd_build']
    inputs = json.loads((r / evidence['candidate']).read_text())['inputs']
    ctl = guest(r / inputs['launchctl']['path'])
    jobs = []; startup = []; cleanup = []
    for name in ['LaunchDaemons/com.apple.securityd.plist', 'LaunchDaemons/com.apple.trustd.plist', 'LaunchAgents/com.apple.trustd.agent.plist']:
        template = r / 'runtime/rootfs/usr/libexec/darling/System/Library' / name
        job = plistlib.loads(template.read_bytes()); label = job['Label']; env = dict(daemon)
        if label == 'com.apple.securityd':
            job['ProgramArguments'][0] = guest(r / build['binary'])
            env['DYLD_LIBRARY_PATH'] = guest((r / build['backend']).parent) + ':' + env['DYLD_LIBRARY_PATH']
        if label.startswith('com.apple.trustd') and profile.get('_certificate_trustd_build'):
            trustd = profile['_certificate_trustd_build']
            job['ProgramArguments'][0] = guest(r / trustd['binary'])
            env['DYLD_LIBRARY_PATH'] = guest((r / trustd['backend']).parent) + ':' + env['DYLD_LIBRARY_PATH']
        job['EnvironmentVariables'] = {**job.get('EnvironmentVariables', {}), **env}
        job.pop('LimitLoadToSessionType', None); job.pop('UserName', None); job['RunAtLoad'] = True
        job['ProgramArguments'] = ['/usr/bin/env', *[k + '=' + v for k, v in env.items()], *job['ProgramArguments']]
        job['StandardOutPath'] = job['StandardErrorPath'] = guest(folder / (label + '.log'))
        path = folder / (label + '.plist'); path.write_bytes(plistlib.dumps(job)); path.chmod(0o644)
        startup.extend([shlex.join([ctl, 'remove', label]) + ' >/dev/null 2>&1 || true',
                        shlex.join([ctl, 'load', guest(path)]), shlex.join([ctl, 'start', label])])
        if verbose: startup.append(shlex.join([ctl, 'list', label]))
        cleanup.append(shlex.join([ctl, 'remove', label]) + ' >/dev/null 2>&1 || true')
        jobs.append(dict(path=str(path.relative_to(r)), sha256=sha(path), label=label,
                         template=str(template.relative_to(r)), template_sha256=sha(template)))
    evidence.update(jobs=jobs, startup='\n'.join(startup) + '\n', cleanup='; '.join(reversed(cleanup)))
    (folder / 'prepared.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return {**profile, 'native_certificate_runtime': evidence}
