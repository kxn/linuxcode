#!/usr/bin/env python3
"""Deterministic Linux/ucontext regression for actual DarlingServer::Thread.

Compile current thread.cpp privately and link read-only copies of the configured
server objects. Historical C/C++ thread sources and matching C++ headers are
exact archived negative controls, including the rejected broad pending flag.
No shared build, installed server, Darling boot, or Mach-O program is run.
"""
from pathlib import Path
import hashlib
import argparse
import json
import runpy
import shlex
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
build = root / 'runtime/darlingserver-source-build'
folder = Path(tempfile.mkdtemp(prefix='thread-handoff-', dir=root / 'runtime'))
source = root / 'fixtures/hello/thread-resume-handoff.cpp'
c_source = root / 'fixtures/hello/thread-resume-handoff-c.c'
thread_source = root / 'vendor/darlingserver/src/thread.cpp'
c_thread_source = root / 'vendor/darlingserver/duct-tape/src/thread.c'
header = root / 'vendor/darlingserver/internal-include/darlingserver/thread.hpp'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
commands = []
inputs = {}

def execute(command):
    commands.append([str(p) for p in command])
    subprocess.run(command, cwd=build, check=True)

def ninja_command(target, endswith):
    output = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands', target], text=True)
    return next(shlex.split(line) for line in output.splitlines() if line.endswith(endswith))

compile_command = ninja_command('darlingserver/CMakeFiles/darlingserver.dir/src/thread.cpp.o',
                                ' -c ' + str(thread_source))
flags = compile_command[:compile_command.index('-MD')]
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
        shutil.copyfile(p, copy)
        assert sha(copy) == inputs[str(p.relative_to(root))]
        private_link.append(str(copy))
    else:
        private_link.append(item)
output_index = private_link.index('-o') + 1
c_compile = ninja_command('darlingserver/duct-tape/CMakeFiles/darlingserver_duct_tape.dir/src/thread.c.o',
                          ' -c ' + str(c_thread_source))
c_flags = c_compile[:c_compile.index('-MD')]
c_fixture_object = folder / 'c-fixture.o'
execute(c_flags + ['-c', str(c_source), '-o', str(c_fixture_object)])

stage_path = root / 'runtime/remap-diagnostic-server-9iz8voyg/stage.json'
stage = json.loads(stage_path.read_text())
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
historical = root / resolve('vendor/darlingserver/src/thread.cpp',
                            stage['source_files']['vendor/darlingserver/src/thread.cpp'])
historical_c = root / resolve('vendor/darlingserver/duct-tape/src/thread.c',
                              stage['source_files']['vendor/darlingserver/duct-tape/src/thread.c'])
historical_header = root / resolve('vendor/darlingserver/internal-include/darlingserver/thread.hpp',
                                   stage['source_files']['vendor/darlingserver/internal-include/darlingserver/thread.hpp'])
overbroad_stage_path = root / 'runtime/remap-diagnostic-server-zwefful3/stage.json'
overbroad_stage = json.loads(overbroad_stage_path.read_text())
overbroad = root / resolve('vendor/darlingserver/src/thread.cpp',
                           overbroad_stage['source_files']['vendor/darlingserver/src/thread.cpp'])
overbroad_header = root / resolve('vendor/darlingserver/internal-include/darlingserver/thread.hpp',
                                  overbroad_stage['source_files']['vendor/darlingserver/internal-include/darlingserver/thread.hpp'])
all_cases = ['wait-early-stackful', 'wait-early-continuation', 'wait-handoff-stackful',
             'wait-handoff-continuation', 'wait-rewait-early-continuation',
             'wait-rewait-handoff-continuation', 'consumed-wake-then-mutex', 'dead-active-call',
             'ordinary-stackful', 'ordinary-continuation', 'return-with-wake']
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cases', nargs='+', choices=all_cases, default=all_cases)
parser.add_argument('--variants', nargs='+', choices=['candidate', 'historical', 'overbroad'],
                    default=['candidate', 'historical', 'overbroad'])
arguments = parser.parse_args()
cases = arguments.cases
results = {}
implementations = dict(candidate=thread_source, historical=historical, overbroad=overbroad)
headers = dict(candidate=header, historical=historical_header, overbroad=overbroad_header)
for variant in arguments.variants:
    implementation = implementations[variant]
    obj = folder / (variant + '-thread.o')
    c_thread_object = folder / (variant + '-c-thread.o')
    fixture_object = folder / (variant + '-fixture.o')
    binary = folder / (variant + '-probe')
    include = folder / (variant + '-include')
    (include / 'darlingserver').mkdir(parents=True)
    shutil.copyfile(headers[variant], include / 'darlingserver/thread.hpp')
    variant_flags = flags[:1] + ['-I' + str(include)] + flags[1:]
    execute(variant_flags + ['-c', str(source), '-o', str(fixture_object)])
    execute(variant_flags + ['-x', 'c++', '-c', str(implementation), '-o', str(obj)])
    c_implementation = c_thread_source if variant == 'candidate' else historical_c
    execute(c_flags + ['-x', 'c', '-c', str(c_implementation), '-o', str(c_thread_object)])
    command = private_link[:]
    command[output_index] = str(binary)
    command[1:1] = [str(fixture_object), str(c_fixture_object), str(c_thread_object), str(obj), '-Wl,--wrap=setcontext',
        '-Wl,--wrap=_ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE',
        '-Wl,--wrap=dtape_task_create', '-Wl,--wrap=dtape_thread_create',
        '-Wl,--wrap=dtape_task_set_process_generation',
        '-Wl,--wrap=dtape_thread_dying',
        '-Wl,--wrap=libsimple_lock_lock',
        '-Wl,--wrap=dtape_thread_entering', '-Wl,--wrap=dtape_thread_exiting']
    execute(command)
    rows = []
    for case in cases:
        prefix = folder / (variant + '-' + case)
        prefix.mkdir()
        result = subprocess.run([str(binary), case, str(prefix)], cwd=folder,
                                capture_output=True, text=True, timeout=10)
        log = folder / (variant + '-' + case + '.log')
        log.write_text(result.stdout + result.stderr)
        rows.append(dict(case=case, status=result.returncode, output=log.read_text()))
        print(variant, case, result.returncode, log.read_text().strip(), flush=True)
    results[variant] = rows
    inputs[str(binary.relative_to(root))] = sha(binary)

expected_failures = dict(candidate=set(),
                         historical=set(all_cases[:6] + ['dead-active-call']),
                         overbroad={'consumed-wake-then-mutex', 'dead-active-call'})
verified = all(row['status'] == (1 if row['case'] in expected_failures[variant] else 0)
               for variant, rows in results.items() for row in rows)
for p in [source, c_source, thread_source, c_thread_source, header, historical, historical_c,
          historical_header, overbroad, overbroad_header,
          Path(__file__), stage_path, overbroad_stage_path]:
    inputs[str(p.relative_to(root))] = sha(p)
report = dict(verified=verified, results=results, commands=commands, files=inputs,
              scope='Actual C++ Thread doWork/suspend/resume, ucontext, StackPool; '
                    'actual XNU wait/block/unblock and duct-tape mutex; controlled enqueue '
                    'and XNU lifecycle; no kernelAsync, full server boot, or Mach-O integration coverage',
              negative_control='Exact archived pre-fix and overbroad C/C++ thread sources with matching '
                               'C++ headers, retaining current non-thread objects and mutex library; '
                               'not historical full-server binaries.',
              expected_failures={variant: sorted(expected_failures[variant]) for variant in results})
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
