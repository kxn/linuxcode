#!/usr/bin/env python3
"""Exercise actual duct-tape wait/block and contended lock code on Linux.

Only scheduler hooks belong to the fixture. No
waiting, locking, or wake implementation is copied into the test.
"""
from pathlib import Path
import hashlib, json, shlex, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
build = root / 'runtime/darlingserver-source-build'
folder = Path(tempfile.mkdtemp(prefix='microthread-pending-wait-', dir=root / 'runtime'))
source = root / 'fixtures/hello/microthread-pending-wait.c'
server = root / 'vendor/darlingserver/duct-tape/src/thread.c'
commands = subprocess.check_output([
    'ninja', '-C', str(build), '-t', 'commands',
    'darlingserver/duct-tape/CMakeFiles/darlingserver_duct_tape.dir/src/thread.c.o'
], text=True).splitlines()
command = next(shlex.split(line) for line in commands if line.endswith(' -c ' + str(server)))
flags = command[:command.index('-MD')]
compile_commands = [
    flags + ['-c', str(source), '-o', str(folder / 'fixture.o')],
    flags + ['-c', str(server), '-o', str(folder / 'thread.o')],
]
for cmd in compile_commands:
    subprocess.run(cmd, cwd=build, check=True, stdout=subprocess.DEVNULL)
link = [command[0], '-Wl,--gc-sections', str(folder / 'fixture.o'),
        str(folder / 'thread.o'),
        str(build / 'darlingserver/duct-tape/libdarlingserver_duct_tape.a'),
        str(build / 'libsimple/liblibsimple_darlingserver.a'),
        '-pthread', '-o', str(folder / 'probe')]
subprocess.run(link, cwd=build, check=True)
result = subprocess.run([str(folder / 'probe')], capture_output=True, text=True, timeout=10)
(folder / 'run.log').write_text(result.stdout + result.stderr)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
report = dict(verified=result.returncode == 0, status=result.returncode,
              scope='Host test of actual source functions with controlled scheduler; no full server boot or timer coverage',
              commands=compile_commands + [link],
              files={str(p.relative_to(root)): sha(p) for p in [source, server, Path(__file__), folder / 'probe', folder / 'run.log']})
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(result.stdout + result.stderr, end='')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(result.returncode)
