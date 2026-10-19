#!/usr/bin/env python3
"""Capture the first Linux SIGSEGV in an unchanged resource tool with gdb."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--stem', required=True)
args = parser.parse_args()
assert args.stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.stem)
log = root/('logs/'+args.stem+'-driver.log')
report = root/('artifacts/'+args.stem+'.json')
assert not log.exists() and not report.exists()
target = b'/Applications/Xcode.app/Contents/Developer/usr/bin/actool'
command = ['python3', 'scripts/probe-direct-resource-tools.py', '--stage', args.stage,
           '--configuration', args.configuration]
capture = None
with log.open('w') as out:
    process = subprocess.Popen(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    deadline = time.monotonic()+180
    pid = None
    while process.poll() is None and time.monotonic() < deadline:
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                argv = (entry/'cmdline').read_bytes().split(b'\0')
                if argv[0] == target or (argv[0].endswith(b'/mldr') and target in argv):
                    pid = int(entry.name)
                    break
            except OSError:
                pass
        if pid is not None:
            break
        time.sleep(.005)
    if pid is not None:
        raw = root/('logs/'+args.stem+'.gdb.log')
        maps = root/('logs/'+args.stem+'.maps.log')
        assert not raw.exists() and not maps.exists()
        code = '''import gdb,struct
for thread in gdb.selected_inferior().threads():
 thread.switch();print('THREAD',thread.ptid)
 print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 frame=int(gdb.parse_and_eval('$rbp'))
 for i in range(50):
  try:following,pc=struct.unpack('<QQ',gdb.selected_inferior().read_memory(frame,16).tobytes())
  except Exception:break
  print('FRAME',hex(frame),hex(pc))
  if following<=frame or following>frame+0x100000:break
  frame=following
'''
        save_maps = ('python open('+repr(str(maps))+
            ", 'w').write(open('/proc/"+str(pid)+"/maps').read())")
        gdb = ['gdb', '-q', '-nx', '-batch', '-p', str(pid), '-ex', 'set pagination off',
            '-ex', 'handle SIGSEGV stop print nopass', '-ex', 'continue',
            '-ex', 'p $_siginfo', '-ex', 'info registers', '-ex', 'x/12i $rip',
            '-ex', save_maps, '-ex', 'python exec('+repr(code)+')']
        result = subprocess.run(gdb, cwd=root, capture_output=True, text=True, timeout=50)
        raw.write_text(result.stdout+result.stderr)
        capture = dict(pid=pid, gdb_status=result.returncode, gdb_log=str(raw.relative_to(root)),
                       maps=str(maps.relative_to(root)) if maps.exists() else None)
    status = process.wait(timeout=240)
record = dict(command=command, outer_status=status, capture=capture,
    log=str(log.relative_to(root)), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
report.write_text(json.dumps(record, indent=2)+'\n')
print(report.relative_to(root))
if capture:
    print((root/capture['gdb_log']).read_text()[-6000:])
