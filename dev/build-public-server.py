#!/usr/bin/env python3
"""Fetch pinned public sources and build only Linux darlingserver; never run or install it."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
LOCK = HERE / 'locks/public-server.lock.json'
BUILD = Path('runtime/developer/server')


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(command, cwd=None):
    return subprocess.check_output(command, cwd=cwd, text=True, stderr=subprocess.PIPE).strip()


def load_lock():
    data = json.loads(LOCK.read_text())
    check(data['schema'] == 1, 'Unsupported public-source lock schema')
    for repo in data['repositories']:
        path = Path(repo['path'])
        check(not path.is_absolute() and '..' not in path.parts, 'Unsafe repository path')
        check(re.fullmatch('[0-9a-f]{40}', repo['commit']), 'Require full immutable source commits')
        check(repo['url'].startswith('https://github.com/'), 'Require explicit public HTTPS repository URL')
    return data


def gitlink(workspace, repo):
    if 'superproject' not in repo:
        return
    parent = workspace / repo['superproject']
    row = output(['git', '-C', str(parent), 'ls-tree', 'HEAD', repo['gitlink_path']]).split()
    check(row[:3] == ['160000', 'commit', repo['commit']], 'Public submodule pin mismatch: ' + repo['name'])
    url = output(['git', '-C', str(parent), 'config', '-f', '.gitmodules', '--get',
                  'submodule.' + repo['gitlink_path'] + '.url'])
    check(url.removesuffix('.git') == repo['url'].removesuffix('.git'), 'Public submodule URL mismatch: ' + repo['name'])


def source_snapshot(workspace, lock):
    records = []
    for repo in lock['repositories']:
        path = workspace / repo['path']
        head = output(['git', '-C', str(path), 'rev-parse', 'HEAD'])
        dirty = output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=all'])
        origin = output(['git', '-C', str(path), 'remote', 'get-url', 'origin'])
        alternate = Path(output(['git', '-C', str(path), 'rev-parse', '--git-path', 'objects/info/alternates']))
        alternate = alternate if alternate.is_absolute() else path / alternate
        check(head == repo['commit'] and not dirty, 'Public checkout changed: ' + repo['name'])
        check(origin == repo['url'] and not alternate.exists(), 'Checkout must use the public origin without local object alternates')
        gitlink(workspace, repo)
        records.append(dict(name=repo['name'], path=repo['path'], selected_commit=repo['commit'],
                            actual_head=head, dirty_status=dirty, origin=origin,
                            tree=output(['git', '-C', str(path), 'rev-parse', 'HEAD^{tree}']),
                            local_object_alternates=False))
    check(sha(workspace / 'build-support/darlingserver/CMakeLists.txt') == lock['build_support_sha256'],
          'Public build-support source checksum mismatch')
    return records


def dependency_audit(workspace, lock):
    build = workspace / BUILD
    deps = output(['ninja', '-C', str(build), '-t', 'deps'])
    paths = set()
    for line in deps.splitlines():
        if not line[:1].isspace() or not line.strip():
            continue
        path = Path(line.strip())
        paths.add((path if path.is_absolute() else build / path).resolve())
    check(paths, 'No compiler dependency evidence; complete the source build first')
    repos = sorted(lock['repositories'], key=lambda row: len(Path(row['path']).parts), reverse=True)
    tracked = {}
    for repo in repos:
        path = workspace / repo['path']
        raw = subprocess.check_output(['git', '-C', str(path), 'ls-files', '-z'])
        tracked[repo['name']] = set(raw.decode().split('\0'))
    counts = dict(public_source=0, generated_build=0, system_host=0)
    for path in paths:
        if path.is_relative_to(build):
            counts['generated_build'] += 1
            continue
        matched = False
        for repo in repos:
            source = workspace / repo['path']
            if path.is_relative_to(source):
                check(path.relative_to(source).as_posix() in tracked[repo['name']],
                      'Compiler consumed an untracked source input: ' + str(path))
                counts['public_source'] += 1
                matched = True
                break
        if not matched:
            check(any(path.is_relative_to(Path(prefix)) for prefix in ('/usr', '/lib', '/lib64')),
                  'Compiler dependency lies outside public checkout and host system: ' + str(path))
            counts['system_host'] += 1
    return dict(verified=True, distinct_paths=len(paths), categories=counts,
                local_vendor_or_private_Apple_inputs_found=False)


def inspect_build(workspace, lock):
    repositories = source_snapshot(workspace, lock)
    binary = workspace / BUILD / 'darlingserver/darlingserver'
    header = binary.read_bytes()[:64]
    check(header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', header, 18)[0] == 62,
          'Expected a Linux ELF64/x86_64 server, not a Mach-O image')
    legacy = json.loads((workspace / BUILD / 'build.json').read_text())
    check(sha(binary) == legacy['binary_sha256'], 'Build receipt does not match server bytes')
    return dict(verified=True, workspace=str(workspace), repositories=repositories,
                binary=str(BUILD / 'darlingserver/darlingserver'), binary_sha256=sha(binary),
                compiler_dependency_audit=dependency_audit(workspace, lock),
                legacy_developer_build_record=legacy,
                legacy_milestone_is_current_source_selection=False,
                authoritative_source_selection='repositories selected_commit/actual_head/dirty_status above',
                source_lock_sha256=sha(LOCK), host_only=True, server_executed=False,
                Apple_linker_executed=False, default_runtime_changed=False,
                session_lock_acquired=False, cold_Darling_Xcode_rebuild_ready=False,
                old_doctor_exact_checkpoint_asserted=False)


def environment(host_tools):
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(('DYLD_', 'LINUXCODE_')) or name in (
                'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'CPATH', 'C_INCLUDE_PATH',
                'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH', 'LD_LIBRARY_PATH', 'BISON_PKGDATADIR', 'M4'):
            env.pop(name)
    if host_tools:
        host_tools = host_tools.expanduser().resolve()
        check((host_tools / 'bin').is_dir(), '--host-tools must contain bin/')
        env['PATH'] = str(host_tools / 'bin') + os.pathsep + env.get('PATH', '')
        if ((host_tools / 'share/bison').is_dir() and
                shutil.which('bison', path=env['PATH']) == str(host_tools / 'bin/bison')):
            env['BISON_PKGDATADIR'] = str(host_tools / 'share/bison')
        if (host_tools / 'bin/m4').is_file():
            env['M4'] = str(host_tools / 'bin/m4')
    for name in ('git', 'cmake', 'ninja', 'clang-19', 'clang++-19', 'bison', 'flex', 'm4'):
        check(shutil.which(name, path=env.get('PATH')), 'Missing Linux host tool: ' + name)
    return env


def commands(workspace, lock, jobs):
    planned = []
    for repo in lock['repositories']:
        path = workspace / repo['path']
        sequence = [['git', 'init', '--quiet', str(path)],
                    ['git', '-C', str(path), 'remote', 'add', 'origin', repo['url']]]
        if repo.get('sparse_paths'):
            sequence += [['git', '-C', str(path), 'sparse-checkout', 'init', '--cone'],
                         ['git', '-C', str(path), 'sparse-checkout', 'set', '--skip-checks', *repo['sparse_paths']]]
        sequence += [['git', '-C', str(path), 'fetch', '--depth=1', '--filter=blob:none', 'origin', repo['commit']],
                     ['git', '-C', str(path), 'checkout', '--detach', 'FETCH_HEAD']]
        planned.append((repo, sequence))
    build = [sys.executable, str(HERE / 'linuxcode-dev'), '--workspace', str(workspace),
             'build', 'server', '--jobs', str(jobs)]
    return planned, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path, help='New private checkout; inspect may read an existing build')
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    parser.add_argument('--host-tools', type=Path, help='Optional existing Linux tool prefix containing bin/ and share/bison/')
    parser.add_argument('--plan', action='store_true', help='Print commands without network, files or build execution')
    parser.add_argument('--inspect', action='store_true', help='Read-only audit of an existing checkout/build against these pins')
    args = parser.parse_args()
    check(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'This component path supports Linux x86_64')
    lock = load_lock()
    workspace = args.workspace.expanduser().resolve()
    check(sha(HERE / 'linuxcode-dev') == lock['developer_tool_sha256'], 'Developer build driver differs from the verified published source')
    if args.inspect:
        print(json.dumps(inspect_build(workspace, lock), indent=2))
        return
    # A new checkout is the safety boundary; existing vendor/build roots are refused.
    check(not workspace.exists(), 'Workspace must be new; use --inspect for read-only existing evidence')
    planned, build = commands(workspace, lock, args.jobs)
    if args.plan:
        print(json.dumps(dict(workspace=str(workspace), repositories=lock['repositories'],
                              fetch_commands=[command for _, sequence in planned for command in sequence],
                              build_command=build, jobs=args.jobs, commands_executed=False,
                              cold_Darling_Xcode_rebuild_ready=False), indent=2))
        return
    env = environment(args.host_tools)
    workspace.mkdir(parents=True)
    logs = workspace / 'runtime/public-server-build'
    logs.mkdir(parents=True)
    steps = []
    report = dict(verified=False, workspace=str(workspace), jobs=args.jobs,
                  source_lock_sha256=sha(LOCK), host_only=True, server_executed=False,
                  Apple_linker_executed=False, session_lock_acquired=False,
                  default_runtime_changed=False, cold_Darling_Xcode_rebuild_ready=False)

    def run(command):
        name = f'step-{len(steps) + 1:03}.log'
        started = time.monotonic()
        with (logs / name).open('w') as stream:
            result = subprocess.run(command, cwd=workspace, env=env, stdout=stream, stderr=subprocess.STDOUT)
        steps.append(dict(command=command, status=result.returncode, elapsed_seconds=time.monotonic() - started,
                          log=str((logs / name).relative_to(workspace)), log_sha256=sha(logs / name)))
        check(result.returncode == 0, 'Command failed; inspect ' + str(logs / name))

    try:
        for repo, sequence in planned:
            gitlink(workspace, repo)
            (workspace / repo['path']).mkdir(parents=True, exist_ok=True)
            for command in sequence:
                run(command)
        report['sources_before_build'] = source_snapshot(workspace, lock)
        run(build)
        report.update(inspect_build(workspace, lock), fresh_public_sources_fetched=True,
                      local_vendor_sources_copied=False)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
        raise
    finally:
        report['steps'] = steps
        (logs / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print('EVIDENCE', logs / 'result.json', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('public server build: ' + str(error), file=sys.stderr)
        raise SystemExit(1) from None
