#!/usr/bin/env python3
"""Host-only actual checkout/checkin lifecycle regression using Linux pipe EOF.

Private C++ compilation and read-only copied server objects. Production monitor
callbacks are dispatched in chosen order; XNU lifecycle and output transport are
controlled. Exact stage107 source/header negative controls are retained.
"""
from pathlib import Path
import hashlib
import json
import resource
import runpy
import shlex
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
build = root / 'runtime/darlingserver-source-build'
folder = Path(tempfile.mkdtemp(prefix='exec-checkin-lifecycle-', dir=root / 'runtime'))
source = root / 'fixtures/hello/exec-checkin-lifecycle.cpp'
bridge = root / 'fixtures/hello/thread-resume-handoff-c.c'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
commands, inputs = [], {}
fixture_snapshot = folder / 'fixture.cpp'
shutil.copyfile(source, fixture_snapshot)
inputs[str(source.relative_to(root))] = sha(fixture_snapshot)

def execute(command):
    commands.append([str(p) for p in command])
    subprocess.run(command, cwd=build, check=True)

def compile_flags(target, source):
    output = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands', target], text=True)
    command = next(shlex.split(line) for line in output.splitlines()
                   if line.endswith(' -c ' + str(source)))
    return command[:command.index('-MD')]

implementations = {n: root / ('vendor/darlingserver/src/' + n + '.cpp')
                   for n in ['thread', 'process', 'call']}
flags = {n: compile_flags('darlingserver/CMakeFiles/darlingserver.dir/src/' + n + '.cpp.o', p)
         for n, p in implementations.items()}
c_flags = compile_flags('darlingserver/duct-tape/CMakeFiles/darlingserver_duct_tape.dir/src/thread.c.o',
                        root / 'vendor/darlingserver/duct-tape/src/thread.c')
link_output = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands',
                                     'darlingserver/darlingserver'], text=True).splitlines()[-1]
link = shlex.split(link_output.split(' && ')[1])
private_link = []
for item in link:
    if item.startswith('-Xlinker') or item.startswith('--dependency-file='):
        continue
    if any(item.endswith(n + '.cpp.o') for n in ['darlingserver', 'thread', 'process', 'call']):
        continue
    p = build / item
    if item.endswith(('.o', '.a')):
        inputs[str(p.relative_to(root))] = sha(p)
        copy = folder / p.name
        if copy.exists():
            assert sha(copy) == inputs[str(p.relative_to(root))], 'copy filename collision'
        else:
            shutil.copyfile(p, copy)
        private_link.append(str(copy))
    else:
        private_link.append(item)
output_index = private_link.index('-o') + 1
bridge_object = folder / 'bridge.o'
execute(c_flags + ['-c', str(bridge), '-o', str(bridge_object)])
stage_path = root / 'runtime/remap-diagnostic-server-scqr1r7d/stage.json'
stage = json.loads(stage_path.read_text())
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
historical = {n: root / resolve(str(p.relative_to(root)), stage['source_files'][str(p.relative_to(root))])
              for n, p in implementations.items()}
headers = {n: root / ('vendor/darlingserver/internal-include/darlingserver/' + n + '.hpp')
           for n in ['thread', 'process', 'call']}
historical_headers = {n: root / resolve(str(p.relative_to(root)), stage['source_files'][str(p.relative_to(root))])
                      for n, p in headers.items()}
cases = ['exec-main-before-monitor', 'exec-monitor-before-main', 'exec-double-late-monitors',
         'failed-exec', 'failed-exec-late-monitor', 'native-exec', 'disclaim-success',
         'pthread-not-fork', 'fork-once', 'initial-startup']
results = {}
for variant in ['candidate', 'historical']:
    include = folder / (variant + '-include')
    (include / 'darlingserver').mkdir(parents=True)
    for name, path in (headers if variant == 'candidate' else historical_headers).items():
        shutil.copyfile(path, include / 'darlingserver' / (name + '.hpp'))
        inputs[str(path.relative_to(root))] = sha(path)
    objects = []
    for name, path in (implementations if variant == 'candidate' else historical).items():
        snapshot = folder / (variant + '-' + name + '.cpp')
        shutil.copyfile(path, snapshot)
        inputs[str(path.relative_to(root))] = sha(snapshot)
        obj = folder / (variant + '-' + name + '.o')
        variant_flags = flags[name][:1] + ['-I' + str(include)] + flags[name][1:]
        execute(variant_flags + ['-x', 'c++', '-c', str(snapshot), '-o', str(obj)])
        objects.append(obj)
    fixture_object = folder / (variant + '-fixture.o')
    execute(flags['thread'][:1] + ['-I' + str(include)] + flags['thread'][1:] +
            ['-c', str(fixture_snapshot), '-o', str(fixture_object)])
    binary = folder / (variant + '-probe')
    command = private_link[:]
    command[output_index] = str(binary)
    command[1:1] = [str(fixture_object), str(bridge_object)] + [str(o) for o in objects] + [
        '-Wl,--wrap=' + name for name in [
            '_ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE',
            '_ZN13DarlingServer6Server11sendMessageEONS_7MessageE',
            '_ZN13DarlingServer6Thread11kernelAsyncESt8functionIFvvEE',
            'dtape_task_create', 'dtape_task_release', 'dtape_task_dying',
            'dtape_thread_create', 'dtape_thread_release', 'dtape_task_set_process_generation',
            'dtape_task_set_audit_identity', 'dtape_thread_dying', 'dtape_semaphore_create',
            'dtape_semaphore_destroy', 'dtape_semaphore_up', 'dtape_semaphore_down_simple']]
    execute(command)
    rows = []
    for case in cases:
        prefix = folder / (variant + '-' + case)
        prefix.mkdir()
        try:
            r = subprocess.run([str(binary), case, str(prefix)], cwd=folder, capture_output=True,
                               text=True, timeout=10,
                               preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            status, output = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired as error:
            status, output = 124, str(error)
        log = folder / (variant + '-' + case + '.log')
        log.write_text(output)
        rows.append(dict(case=case, status=status, log=str(log.relative_to(root)), output=output))
        print(variant, case, status, output.strip(), flush=True)
    results[variant] = rows
    inputs[str(binary.relative_to(root))] = sha(binary)
for p in [bridge, stage_path, Path(__file__), fixture_snapshot]:
    inputs[str(p.relative_to(root))] = sha(p)
negative_failures = {'exec-main-before-monitor', 'exec-double-late-monitors', 'disclaim-success',
                     'pthread-not-fork', 'fork-once', 'initial-startup'}
verified = all(row['status'] == 0 for row in results['candidate']) and all(
    row['status'] == (1 if row['case'] in negative_failures else 0) for row in results['historical'])
report = dict(verified=verified, results=results, commands=commands, files=inputs,
              expected_historical_failures=sorted(negative_failures),
              scope='Actual Call checkout/checkin, Process notifyCheckin and exec lifecycle, '
                    'Thread pushCallReply and registry; real Linux pipe success EOF/failure marker, '
                    'actual stored monitor callbacks dispatched in controlled order. Controlled '
                    'XNU construction/destruction and output transport; no full server event loop, '
                    'actual Linux exec, native Darling session, or Mach-O integration.',
              negative_control='Exact archived stage107 Thread/Process/Call sources with matching '
                               'private headers; current read-only copied non-replaced objects. '
                               'Not a historical complete-server binary.')
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
