#!/usr/bin/env python3
"""Capture workloop registrations until the original client receives a negative syscall result."""
from pathlib import Path
import argparse, hashlib, json, re, struct, subprocess, time
root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
for name in ['stage', 'configuration', 'stem']: p.add_argument('--' + name, required=True)
a = p.parse_args(); assert a.stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in a.stem)
folder = root / 'runtime' / a.stem; assert not folder.exists(); folder.mkdir()
stage = json.loads((root / a.stage).read_text())
objc = root / stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path']
data = objc.read_bytes(); assert data[:4] == bytes.fromhex('cffaedfe')
slice_offset = 0
symbols = subprocess.check_output(['llvm-nm-19', str(objc)], text=True)
lock_offset = int(re.search(r'^([0-9a-f]+)\s+[Tt]\s+_sys_kevent_id$', symbols, re.M)[1], 16)
command = ['python3', 'scripts/probe-original-storyboard.py', '--stage', a.stage, '--configuration', a.configuration,
           '--with-disk-services', '--trace-launch-jobs', '--timeout', '150']
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
                if '/usr/lib/system/libsystem_kernel.dylib' in line and 'r-x' in parts[1]:
                    base = int(parts[0].split('-')[0], 16) - int(parts[2], 16) + slice_offset
                    address = base + lock_offset; break
            if address:
                (folder / 'initial.maps').write_text(maps); break
        time.sleep(.002)
    if address:
        raw = folder / 'watch.gdb.log'; final_maps = folder / 'final.maps'
        code = '''import gdb,struct
inf=gdb.selected_inferior()
expected=bytes.fromhex('EXPECTED')
assert inf.read_memory(ADDRESS,len(expected)).tobytes()==expected
class Returned(gdb.FinishBreakpoint):
 def __init__(self, frame, call):
  super().__init__(frame, internal=True); self.call=call
 def stop(self):
  rv=int(gdb.parse_and_eval('$rax')); rv=rv-(1<<64) if rv>=(1<<63) else rv
  print('WORKLOOP_RESULT',self.call,rv)
  return rv<0
class Entered(gdb.Breakpoint):
 count=0
 def stop(self):
  self.count+=1
  regs={name:int(gdb.parse_and_eval('$'+name)) for name in ['rdi','rsi','rdx','rcx','r8','r9','rsp']}
  stack=struct.unpack('<QQQ',inf.read_memory(regs['rsp'],24).tobytes())
  print('WORKLOOP_CALL',self.count,regs,'available',hex(stack[1]),'flags',hex(stack[2]))
  for i in range(min(regs['rdx'],8)):
   try: fields=struct.unpack('<QhHiQIIqQQQQ',inf.read_memory(regs['rsi']+72*i,72).tobytes()); print('WORKLOOP_CHANGE',i,fields)
   except Exception as e:print('WORKLOOP_CHANGE_UNREADABLE',str(e))
  Returned(gdb.newest_frame(),self.count)
  return self.count>=64
Entered('*ADDRESS')
'''.replace('EXPECTED', data[lock_offset:lock_offset+12].hex()).replace('ADDRESS',hex(address))
        script = folder / 'capture.gdb'
        script.write_text('set pagination off\nset confirm off\nset print thread-events off\n'
            'handle SIGUSR1 SIGUSR2 SIGPWR nostop noprint pass\n'
            'handle SIGSEGV SIGILL SIGABRT stop print pass\npython\n' + code + '\nend\ncontinue\n'
            'info registers\n'
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
              source_kernel=str(objc.relative_to(root)), source_kernel_sha256=sha(objc),
              files={str(path.relative_to(root)):sha(path) for path in folder.iterdir() if path.is_file()},
              tool_sha256=sha(Path(__file__)), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
if capture: print((root / capture['log']).read_text()[-8000:])
