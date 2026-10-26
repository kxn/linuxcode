#!/usr/bin/env python3
"""Trace original iOS selector-lock writes before its reported recursive lock fault."""
from pathlib import Path
import argparse, hashlib, json, re, struct, subprocess, time
root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
for name in ['stage', 'configuration', 'stem']: p.add_argument('--' + name, required=True)
a = p.parse_args(); assert a.stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
folder = root / 'runtime' / a.stem; assert not folder.exists(); folder.mkdir()
objc = root / 'runtime/ios265-simulator-extracted-v1/Library/Developer/CoreSimulator/Profiles/Runtimes/iOS 26.5.simruntime/Contents/Resources/RuntimeRoot/usr/lib/libobjc.A.dylib'
data = objc.read_bytes(); assert data[:4] == bytes.fromhex('cafebabe')
slices = [struct.unpack_from('>IIIII', data, 8 + 20*i) for i in range(struct.unpack_from('>I', data, 4)[0])]
slice_offset = next(row[2] for row in slices if row[0] == 0x1000007)
symbols = subprocess.check_output(['llvm-nm-19', '--arch=x86_64', str(objc)], text=True)
lock_offset = int(re.search(r'^([0-9a-f]+)\s+b\s+_selLock$', symbols, re.M)[1], 16)
command = ['python3', 'scripts/probe-original-storyboard.py', '--stage', a.stage, '--configuration', a.configuration,
           '--with-disk-services', '--trace-launch-jobs', '--timeout', '240']
capture = None
with (folder / 'probe.log').open('w') as out:
    probe = subprocess.Popen(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 150; pid = None; address = None
    while probe.poll() is None and time.monotonic() < deadline:
        if pid is None:
            for path in Path('/proc').glob('[0-9]*/cmdline'):
                try: argv = path.read_bytes().split(b'\0')
                except OSError: continue
                if argv[0].endswith(b'/IBAgent-iOS') or (argv[0].endswith(b'/mldr') and any(x.endswith(b'/IBAgent-iOS') for x in argv[1:])):
                    pid = int(path.parent.name); break
        if pid:
            try: maps = Path(f'/proc/{pid}/maps').read_text()
            except OSError: break
            for line in maps.splitlines():
                parts = line.split()
                if 'RuntimeRoot/usr/lib/libobjc.A.dylib' in line and 'r-x' in parts[1]:
                    base = int(parts[0].split('-')[0], 16) - int(parts[2], 16) + slice_offset
                    address = base + lock_offset; break
            if address:
                (folder / 'initial.maps').write_text(maps); break
        time.sleep(.002)
    if address:
        raw = folder / 'watch.gdb.log'; final_maps = folder / 'final.maps'
        code = '''import gdb,struct
inf=gdb.selected_inferior()
def frames():
 print('PC',hex(int(gdb.parse_and_eval('$rip'))))
 frame=int(gdb.parse_and_eval('$rbp'))
 for i in range(24):
  try: following,pc=struct.unpack('<QQ',inf.read_memory(frame,16).tobytes())
  except Exception: break
  print('FRAME',hex(frame),hex(pc))
  if following<=frame or following>frame+0x100000: break
  frame=following
class Changed(gdb.Breakpoint):
 def __init__(self):
  super().__init__('*(unsigned int*)ADDRESS',type=gdb.BP_WATCHPOINT,wp_class=gdb.WP_WRITE)
  self.count=0
 def stop(self):
  self.count+=1
  print('SELECTOR_LOCK_WRITE',self.count,hex(int(gdb.parse_and_eval('*(unsigned int*)ADDRESS'))))
  frames()
  return self.count>=16
try: print('SELECTOR_LOCK_INITIAL',hex(int(gdb.parse_and_eval('*(unsigned int*)ADDRESS'))))
except Exception as e: print('SELECTOR_LOCK_INITIAL_UNMAPPED',str(e))
Changed()
class Returned(gdb.Breakpoint):
 def __init__(self,at): super().__init__('*'+hex(at),internal=True,temporary=True)
 def stop(self):
  print('SELECTOR_UNLOCK_RETURN_VALUE',hex(int(gdb.parse_and_eval('*(unsigned int*)ADDRESS'))))
  return False
class Unlocking(gdb.Breakpoint):
 def stop(self):
  if int(gdb.parse_and_eval('$rdi')) != ADDRESS: return False
  print('SELECTOR_UNLOCK_CALL_VALUE',hex(int(gdb.parse_and_eval('*(unsigned int*)ADDRESS'))))
  slot=BASE+0x3b310
  target=struct.unpack('<Q',inf.read_memory(slot,8).tobytes())[0]
  print('SELECTOR_UNLOCK_BOUND_TARGET',hex(target));print(gdb.execute('x/12i '+hex(target),to_string=True))
  frames()
  ret=struct.unpack('<Q',inf.read_memory(int(gdb.parse_and_eval('$rsp')),8).tobytes())[0]
  Returned(ret); return False
Unlocking('*'+hex(BASE+0x2a2b2))
'''.replace('ADDRESS', hex(address)).replace('BASE',hex(base))
        script = folder / 'capture.gdb'
        script.write_text('set pagination off\nset confirm off\nset print thread-events off\n'
            'handle SIGUSR1 SIGUSR2 SIGPWR nostop noprint pass\n'
            'handle SIGSEGV SIGILL SIGABRT stop print pass\npython\n' + code + '\nend\ncontinue\n'
            'p $_siginfo\ninfo registers\nx/16i $rip\npython frames()\n'
            + 'python open(' + repr(str(final_maps)) + ", 'w').write(open('/proc/" + str(pid) + "/maps').read())\n"
            + 'detach\n')
        try:
            r = subprocess.run(['sudo', '-n', 'gdb', '-q', '-nx', '-batch', '-p', str(pid), '-x', str(script)],
                               cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            raw.write_text(r.stdout); capture = dict(pid=pid, status=r.returncode, selector_lock=address, log=str(raw.relative_to(root)))
        except subprocess.TimeoutExpired as e:
            raw.write_bytes(e.stdout or b''); capture = dict(pid=pid, timed_out=True, selector_lock=address, log=str(raw.relative_to(root)))
    status = probe.wait(timeout=260)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
record = dict(command=command, probe_status=status, capture=capture, stage=a.stage, configuration=a.configuration,
              original_objc=str(objc.relative_to(root)), original_objc_sha256=sha(objc),
              files={str(path.relative_to(root)):sha(path) for path in folder.iterdir() if path.is_file()},
              tool_sha256=sha(Path(__file__)), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
if capture: print((root / capture['log']).read_text()[-8000:])
