#!/usr/bin/env python3
"""Resume a diagnostic signer and capture real native OSStatus -50 throws."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess,time
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--driver-log',required=True);p.add_argument('--stem',required=True);a=p.parse_args();assert re.fullmatch('[a-z0-9-]+',a.stem)
w=r/'runtime'/a.stem;assert not w.exists();w.mkdir();deadline=time.monotonic()+70;pid=None
while time.monotonic()<deadline:
    log=r/a.driver_log
    match=re.search(r'^RUNNING (runtime/[^\n]+)$',log.read_text() if log.exists() else '',re.M)
    if match:
        app='/Volumes/SystemRoot/workspace/'+match[1]+'/iOSCocoaPodsSmoke.app'
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:args=(proc/'cmdline').read_bytes().split(b'\0');status=(proc/'status').read_text()
            except OSError:continue
            if args[0].endswith(b'/codesign-original') and app.encode() in args and re.search(r'^State:\s+T',status,re.M):pid=int(proc.name);break
    if pid:break
    time.sleep(.2)
assert pid,'No confirmed stopped original signer'
maps=subprocess.check_output(['sudo','-n','cat',f'/proc/{pid}/maps'],text=True);(w/'process.maps').write_text(maps)
rows=[line.split(maxsplit=5) for line in maps.splitlines()];rows=[v for v in rows if len(v)==6 and v[5].endswith('/libDarlingLocalIdentitySecurityBackend.dylib')];assert rows
row=min(rows,key=lambda v:int(v[2],16));slide=int(row[0].split('-')[0],16)-int(row[2],16)
path=r/row[5].removeprefix('/workspace/');assert path.is_relative_to(r/'runtime');data=path.read_bytes();assert data[:8]==bytes.fromhex('cffaedfe07000001');at=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
    cmd,size=struct.unpack_from('<II',data,at)
    if cmd==2:table=struct.unpack_from('<IIII',data,at+8)
    at+=size
symoff,count,stroff,strsize=table;values=[];wanted=b'__ZN8Security10MacOSError7throwMeEi';all_throws=[]
for i in range(count):
    no,kind,section,desc,value=struct.unpack_from('<IBBHQ',data,symoff+16*i)
    if kind&0xe0 or kind&0xe!=0xe:continue
    end=data.index(0,stroff+no,stroff+strsize)
    name=data[stroff+no:end]
    if name==wanted:values.append(value)
    if name.startswith(b'__ZN8Security') and b'Error7throwMeE' in name:all_throws.append((name.decode(),value))
assert len(values)==1,values;address=slide+values[0]
capture='''import gdb,struct
inf=gdb.selected_inferior();print('PC',hex(int(gdb.parse_and_eval('$rip'))));frame=int(gdb.parse_and_eval('$rbp'))
for i in range(48):
 try:following,pc=struct.unpack('<QQ',inf.read_memory(frame,16).tobytes())
 except Exception:break
 print('FRAME',hex(frame),hex(pc))
 if following<=frame or following>frame+0x100000:break
 frame=following
'''
script=w/'capture.gdb';script.write_text('set pagination off\nset confirm off\nset print thread-events off\nhandle SIGSTOP nostop noprint nopass\n'+''.join('break *'+hex(slide+value)+'\ncommands\nsilent\nprintf "CODE_SIGNER_STATUS_THROW %d '+name+'\\n", $edi\npython exec('+repr(capture)+')\ncontinue\nend\n' for name,value in all_throws)+'signal SIGCONT\n')
with (w/'process.gdb.log').open('w') as out:res=subprocess.run(['sudo','-n','gdb','-q','-nx','-batch','-p',str(pid),'-x',str(script)],stdout=out,stderr=subprocess.STDOUT,timeout=45)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();(w/'result.json').write_text(json.dumps(dict(pid=pid,source_driver=a.driver_log,gdb_status=res.returncode,backend=str(path.relative_to(r)),backend_sha256=sha(path),symbol=wanted.decode(),symbol_vmaddr=hex(values[0]),breakpoint=hex(address),files={str(p.relative_to(r)):sha(p) for p in [script,w/'process.maps',w/'process.gdb.log']},debugger_breakpoints_only_no_binary_file_changes=True),indent=2)+'\n');print(w/'result.json')
