#!/usr/bin/env python3
"""Exercise existing path lookup with dyld ASCII fallback and poisoned locale API."""
from pathlib import Path
import errno, hashlib, json, os, subprocess, tempfile
root = Path(__file__).resolve().parent.parent
folder = Path(tempfile.mkdtemp(prefix='vchroot-dyld-casefold-host-', dir=root/'runtime'))
source = root/'fixtures/hello/vchroot-dyld-casefold-host.c'
command = ['clang-19','-O2','-Wall','-Wno-unused-function','-I'+str(root/'runtime/darlingserver-source-build/include'),'-I'+str(root/'runtime/mach-msg2-kernel-v1/generated/include'),str(source),'-o',str(folder/'lookup')]
subprocess.run(command, check=True)
prefix = folder/'root';prefix.mkdir();cases=[]
def run(request, expected, status=0, mode=1, exists=None):
    result = subprocess.run([os.fsencode(folder/'lookup'),os.fsencode(prefix),os.fsencode(request),str(mode).encode(),b'1'],check=True,capture_output=True)
    code, path = result.stdout.splitlines()
    assert int(code)==status,(request,code,path)
    if status==0:
        assert path==os.fsencode(expected),(request,path,expected)
        if exists is not None:assert Path(os.fsdecode(path)).exists()==exists
    cases.append(dict(request=os.fsdecode(request),status=int(code),resolved=os.fsdecode(path),icase_enabled=bool(mode)))
frameworks=prefix/'Frameworks';frameworks.mkdir();(frameworks/'libPcre2-8.0.dylib').write_bytes(b'unchanged filename fixture')
run('/Frameworks/libpcre2-8.0.dylib',frameworks/'libpcre2-8.0.dylib',mode=0,exists=False)
run('/Frameworks/libpcre2-8.0.dylib',frameworks/'libPcre2-8.0.dylib',exists=True)
run('/Frameworks/notfound.dylib',frameworks/'notfound.dylib',exists=False)
(frameworks/'libpcre2-8.0.dylib').write_bytes(b'exact spelling wins')
run('/Frameworks/libpcre2-8.0.dylib',frameworks/'libpcre2-8.0.dylib',exists=True)
run('/Frameworks/LIBPCRE2-8.0.DYLIB','',status=-errno.ENOENT)
(frameworks/'café').write_bytes(b'unicode');run('/Frameworks/cafe\u0301',frameworks/'café',exists=True)
(frameworks/'Straße').write_bytes(b'sharp s');run('/Frameworks/STRASSE',frameworks/'STRASSE',exists=False)
(frameworks/'Å').write_bytes(b'A ring');run('/Frameworks/å',frameworks/'å',exists=False)
(frameworks/'[name').write_bytes(b'punctuation');run('/Frameworks/{name',frameworks/'{name',exists=False)
(frameworks/'Library').write_bytes(b'prefix');run('/Frameworks/lib',frameworks/'lib',exists=False)
for name in (b'bad\xff',b'bad\xfe'):
    fd=os.open(os.fsencode(frameworks)+b'/'+name,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
run(b'/Frameworks/bad\xff',os.fsencode(frameworks)+b'/bad\xff',exists=True)
run(b'/Frameworks/BAD\xff',os.fsencode(frameworks)+b'/bad\xff',exists=True)
run(b'/Frameworks/BAD\xfd',os.fsencode(frameworks)+b'/BAD\xfd',exists=False)
os.symlink('Library',frameworks/'LiNk');run('/Frameworks/link',frameworks/'Library',exists=True)
os.symlink('LoOp',frameworks/'LoOp');run('/Frameworks/loop','',status=-errno.ELOOP)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(verified=True,case_count=len(cases),cases=cases,compile_command=command,
            locale_comparator_poisoned=True,source_harness_reused='fixtures/hello/vchroot-unicode-host.c',
            dyld_variant=True,host_test_only=True,native_darling_execution=False,
            files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source,root/'fixtures/hello/vchroot-unicode-host.c',root/'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/linux_premigration/vchroot_userspace.c']})
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(folder/'result.json')
