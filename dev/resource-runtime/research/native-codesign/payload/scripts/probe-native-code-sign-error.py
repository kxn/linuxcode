#!/usr/bin/env python3
"""Locate the actual native Unix error during genuine local code signing."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,shutil,subprocess,tempfile,time
a=argparse.ArgumentParser();a.add_argument("--xattr-stage");args=a.parse_args()
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='native-code-sign-error-',dir=r/'runtime'))
src=r/'fixtures/hello/native-code-sign-error.c';sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';obj=w/'test.o';binary=w/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O0','-g','-fno-omit-frame-pointer','-c',str(src),'-o',str(obj)],check=True);subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','Security','-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
app=w/'iOSCocoaPodsSmoke.app';shutil.copytree(r/'runtime/ios-cocoapods-build/DerivedData/Build/Products/Debug-iphoneos/iOSCocoaPodsSmoke.app',app);guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r))
m=runpy.run_path(str(r/('scripts/xattr-runtime-profile.py' if args.xattr_stage else 'scripts/derq-runtime-profile.py')));p=m['profile'](**({'xattr_stage':args.xattr_stage} if args.xattr_stage else {}),derq_stage='artifacts/derq-original-v1-stage.json',identity_stage='artifacts/local-identity-store-readonly-v2-stage.json',identity_store='runtime/local-identity-xcode-empty-v1/store.plist',codesign_stage='artifacts/codesign-zsign-adhoc-v2-stage.json')
command=p['command'][:-2]+[guest(binary),guest(app)];command[3]='100';closure=json.loads((r/'artifacts/original-codesign-closure-native-local-signer-v1-stage.json').read_text())
for n,d in closure['files'].items():assert hashlib.sha256((r/n).read_bytes()).hexdigest()==d,n
for prefix,leaf in [('DYLD_FRAMEWORK_PATH=','frameworks'),('DYLD_LIBRARY_PATH=','libraries')]:
    i=next(i for i,v in enumerate(command) if v.startswith(prefix));command[i]=prefix+guest(r/closure['root']/leaf)+':'+command[i].split('=',1)[1]
env=m['environment'](p)
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
log=w/'run.log';capture=False;capture_status=None;pid=None
with log.open('w') as out:
    process=subprocess.Popen(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT);start=time.monotonic()
    while process.poll() is None and time.monotonic()-start<75:
        text=log.read_text();match=re.search(r'^NATIVE_SIGNER_ADD_ADDRESS (0x[0-9a-f]+) OWNER (.+)$',text,re.M)
        if match:
            pids=[]
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:
                    if (proc/'cmdline').read_bytes().split(b'\0')[0]==guest(binary).encode():pids.append(proc.name)
                except OSError:pass
            assert len(pids)==1;p_pid=pids[0];pid=int(p_pid)
            # Both symbols are in the identical thin native Security backend.
            nm=subprocess.check_output(['llvm-nm-19','--defined-only',str(r/'runtime/local-identity-store-readonly-v2/libraries/libDarlingLocalIdentitySecurityBackend.dylib')],text=True);symbols={s[2]:int(s[0],16) for l in nm.splitlines() if len(s:=l.split())==3}
            address=int(match[1],16)+symbols['__ZN8Security9UnixError7throwMeEi']-symbols['_SecCodeSignerAddSignatureWithErrors']
            maps=Path('/proc/'+p_pid+'/maps').read_text();(w/'maps.log').write_text(maps)
            code="import gdb,struct\nprint('UNIX_ERROR_NUMBER',int(gdb.parse_and_eval('$edi')))\nprint('PC',hex(int(gdb.parse_and_eval('$rip'))))\nf=int(gdb.parse_and_eval('$rbp'))\nfor i in range(50):\n try:n,pc=struct.unpack('<QQ',gdb.selected_inferior().read_memory(f,16).tobytes())\n except Exception:break\n print('FRAME',hex(f),hex(pc))\n if n<=f or n>f+0x100000:break\n f=n"
            cmd=['gdb','-q','-batch','-ex','set pagination off','-ex','break *'+hex(address),'-ex','continue','-ex','python exec('+repr(code)+')','-p',p_pid]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(w/'capture.log').write_text(result.stdout+result.stderr);capture=True;capture_status=result.returncode;break
        time.sleep(.05)
    process.wait(timeout=110)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();record=dict(native_process_status=process.returncode,capture_attempted=capture,capture_status=capture_status,observed_pid=pid,log=str(log.relative_to(r)),log_sha256=sha(log),source_sha256=sha(src),test_driver_sha256=sha(__file__),signing_success_verified=False)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(log.read_text()[-3500:]);print('EVIDENCE',w/'result.json');print((w/'capture.log').read_text()[-4500:] if capture else 'No capture')
