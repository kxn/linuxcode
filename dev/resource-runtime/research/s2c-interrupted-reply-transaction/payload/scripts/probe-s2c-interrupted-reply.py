#!/usr/bin/env python3
"""Host-only regression of real S2C transactions with controlled wait interruption.

Private Thread compilation, read-only server objects and exact stage106 negative
control. Transport and semaphore waits are controlled; real reply parsing and
transaction functions execute. No shared build or Darling session is modified.
"""
from pathlib import Path
import hashlib
import json
import runpy
import resource
import shlex
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
build = root / 'runtime/darlingserver-source-build'
folder = Path(tempfile.mkdtemp(prefix='s2c-interrupted-reply-', dir=root / 'runtime'))
source = root / 'fixtures/hello/s2c-interrupted-reply.cpp'
bridge = root / 'fixtures/hello/thread-resume-handoff-c.c'
thread_source = root / 'vendor/darlingserver/src/thread.cpp'
header = root / 'vendor/darlingserver/internal-include/darlingserver/thread.hpp'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
commands, inputs = [], {}

def execute(command):
    commands.append([str(p) for p in command])
    subprocess.run(command, cwd=build, check=True)

def compile_flags(target, source):
    output = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands', target], text=True)
    command = next(shlex.split(line) for line in output.splitlines()
                   if line.endswith(' -c ' + str(source)))
    return command[:command.index('-MD')]

flags = compile_flags('darlingserver/CMakeFiles/darlingserver.dir/src/thread.cpp.o', thread_source)
c_flags = compile_flags('darlingserver/duct-tape/CMakeFiles/darlingserver_duct_tape.dir/src/thread.c.o',
                        root / 'vendor/darlingserver/duct-tape/src/thread.c')
link_output = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands',
                                     'darlingserver/darlingserver'], text=True).splitlines()[-1]
link = shlex.split(link_output.split(' && ')[1])
private_link = []
for item in link:
    if item.startswith('-Xlinker') or item.startswith('--dependency-file='):
        continue
    if item.endswith('darlingserver.cpp.o') or item.endswith('thread.cpp.o'):
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
fixture_object = folder / 'fixture.o'
execute(flags + ['-c', str(source), '-o', str(fixture_object)])
stage_path = root / 'runtime/remap-diagnostic-server-gez65ff_/stage.json'
stage = json.loads(stage_path.read_text())
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
historical = root / resolve('vendor/darlingserver/src/thread.cpp',
                            stage['source_files']['vendor/darlingserver/src/thread.cpp'])
candidate = folder / 'candidate-thread.cpp'
shutil.copyfile(thread_source, candidate)
inputs[str(thread_source.relative_to(root))] = sha(candidate)
results = {}
cases = ['normal', 'reply-interrupted', 'reply-before-interrupted',
         'repeated-interrupted', 'acquire-interrupted']
for variant, implementation in dict(candidate=candidate, historical=historical).items():
    obj, binary = folder / (variant + '-thread.o'), folder / (variant + '-probe')
    execute(flags + ['-x', 'c++', '-c', str(implementation), '-o', str(obj)])
    command = private_link[:]
    command[output_index] = str(binary)
    command[1:1] = [str(fixture_object), str(bridge_object), str(obj)] + [
        '-Wl,--wrap=' + name for name in [
            '_ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE',
            '_ZN13DarlingServer6Server11sendMessageEONS_7MessageE',
            'dtape_task_create', 'dtape_thread_create', 'dtape_task_set_process_generation',
            'dtape_task_set_audit_identity', 'dtape_thread_dying', 'dtape_semaphore_create',
            'dtape_semaphore_destroy', 'dtape_semaphore_up', 'dtape_semaphore_down_simple']]
    execute(command)
    rows = []
    for case in cases:
        prefix = folder / (variant + '-' + case)
        prefix.mkdir()
        r = subprocess.run([str(binary), case, str(prefix)], cwd=folder, capture_output=True,
                           text=True, timeout=10,
                           preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
        log = folder / (variant + '-' + case + '.log')
        log.write_text(r.stdout + r.stderr)
        rows.append(dict(case=case, status=r.returncode, log=str(log.relative_to(root)),
                         output=log.read_text()))
        print(variant, case, r.returncode, log.read_text().strip(), flush=True)
    results[variant] = rows
    inputs[str(binary.relative_to(root))] = sha(binary)
for p in [source, bridge, historical, header, stage_path, Path(__file__), candidate]:
    inputs[str(p.relative_to(root))] = sha(p)
verified = all(row['status'] == 0 for row in results['candidate']) and all(
    (row['status'] == 0 if row['case'] in ['normal', 'acquire-interrupted'] else
     row['status'] != 0 and
     ('Invalid S2C reply: unxpected size' if row['case'] == 'reply-before-interrupted' else
      'Received S2C reply but thread already had one pending') in row['output'])
    for row in results['historical'])
report = dict(verified=verified, results=results, commands=commands, files=inputs,
              scope='Actual C++ Thread::_s2cPerform/_mmap/_munmap, Call::callFromMessage, '
                    'Message, Registry, ucontext and StackPool; deterministic semaphore and '
                    'outbound transport boundary. No actual XNU semaphore blocking, full '
                    'server event loop, process death/exec coverage, or Mach-O integration.',
              negative_control='Exact archived stage106 Thread source, same current headers '
                               'and read-only copied non-thread objects; not a historical '
                               'complete server binary.')
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
