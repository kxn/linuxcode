#!/usr/bin/env python3
"""Capture the original simulator IBAgent's first fault or Linux exit syscall."""
from pathlib import Path
import argparse, hashlib, json, subprocess, time
root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
for name in ['stage', 'configuration', 'stem']: p.add_argument('--' + name, required=True)
p.add_argument('--probe-timeout', type=int, default=240)
a = p.parse_args(); assert 30 <= a.probe_timeout <= 600; assert a.stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
folder = root / 'runtime' / a.stem; assert not folder.exists(); folder.mkdir()
command = ['python3', 'scripts/probe-original-storyboard.py', '--stage', a.stage,
           '--configuration', a.configuration, '--with-disk-services', '--trace-launch-jobs', '--timeout', str(a.probe_timeout)]
capture = None
with (folder / 'probe.log').open('w') as out:
    probe = subprocess.Popen(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + min(180, a.probe_timeout); pid = None
    while probe.poll() is None and time.monotonic() < deadline:
        for path in Path('/proc').glob('[0-9]*/cmdline'):
            try: argv = path.read_bytes().split(b'\0')
            except OSError: continue
            if argv[0].endswith(b'/IBAgent-iOS') or (argv[0].endswith(b'/mldr') and any(s.endswith(b'/IBAgent-iOS') for s in argv[1:])):
                pid = int(path.parent.name); break
        if pid: break
        time.sleep(.005)
    if pid:
        maps = folder / 'agent.maps'; raw = folder / 'agent.gdb.log'
        code = '''import gdb,struct
inf=gdb.selected_inferior()
for thread in inf.threads():
 thread.switch(); print('THREAD',thread.ptid)
 print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 frame=int(gdb.parse_and_eval('$rbp'))
 for i in range(60):
  try: following,pc=struct.unpack('<QQ',inf.read_memory(frame,16).tobytes())
  except Exception: break
  print('FRAME',hex(frame),hex(pc))
  if following<=frame or following>frame+0x100000: break
  frame=following
'''
        script = folder / 'capture.gdb'
        script.write_text('set pagination off\nset confirm off\nset print thread-events off\n'
            'handle SIGUSR1 SIGUSR2 SIGPWR nostop noprint pass\n'
            'handle SIGSEGV SIGILL SIGABRT stop print pass\ncatch syscall exit_group\ncontinue\n'
            'p $_siginfo\ninfo registers\nx/16i $rip\nx/24gx $rsp\n'
            + 'python open(' + repr(str(maps)) + ", 'w').write(open('/proc/" + str(pid) + "/maps').read())\n"
            + 'python exec(' + repr(code) + ')\ndetach\n')
        try:
            r = subprocess.run(['sudo', '-n', 'gdb', '-q', '-nx', '-batch', '-p', str(pid), '-x', str(script)],
                               cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            raw.write_text(r.stdout); capture = dict(pid=pid, gdb_status=r.returncode, log=str(raw.relative_to(root)),
                                                  maps=str(maps.relative_to(root)) if maps.exists() else None)
        except subprocess.TimeoutExpired as e:
            raw.write_bytes(e.stdout or b''); capture = dict(pid=pid, timed_out=True, log=str(raw.relative_to(root)))
    status = probe.wait(timeout=a.probe_timeout+30)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
record = dict(command=command, probe_status=status, capture=capture, stage=a.stage, configuration=a.configuration,
              files={str(path.relative_to(root)): sha(path) for path in folder.iterdir() if path.is_file()},
              tool_sha256=sha(Path(__file__)), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
if capture: print((root / capture['log']).read_text()[-6500:])
