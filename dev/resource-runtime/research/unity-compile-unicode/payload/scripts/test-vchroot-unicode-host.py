#!/usr/bin/env python3
"""Exercise the actual Darling vchroot translation unit against Linux files."""
from pathlib import Path
import errno,hashlib,json,os,subprocess,tempfile,unicodedata
root=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='vchroot-unicode-host-',dir=root/'runtime'))
program=folder/'test';source=root/'fixtures/hello/vchroot-unicode-host.c'
command=['clang-19','-O2','-Wall','-Wno-unused-function','-fstack-usage','-I',str(root/'runtime/darlingserver-source-build/include'),'-I',str(root/'runtime/mach-msg2-kernel-v1/generated/include'),str(source),'-o',str(program)]
subprocess.run(command,check=True)
prefix=folder/'root';prefix.mkdir();checks=[]
def run(request,expected,status=0,case=1,follow=1):
    result=subprocess.run([os.fsencode(program),os.fsencode(prefix),os.fsencode(request),str(case).encode(),str(follow).encode()],check=True,stdout=subprocess.PIPE)
    lines=result.stdout.splitlines();actual=int(lines[0]);path=lines[1]
    assert actual==status,(request,actual,status,path)
    if status==0:assert path==os.fsencode(expected),(request,path,os.fsencode(expected))
    checks.append(dict(request=os.fsdecode(request),case_insensitive=case,follow=follow,status=actual,expected=os.fsdecode(expected)))
for i,name in enumerate(['café','レズ','한글','Ångström','a\u0301\u0323','ṩ','K']):
    d=prefix/str(i);d.mkdir();actual=unicodedata.normalize('NFC',name);(d/actual).mkdir();(d/actual/'tail').write_text('payload')
    variants={name,unicodedata.normalize('NFC',name),unicodedata.normalize('NFD',name)}
    for variant in variants:
        for case in [0,1]:run('/'+str(i)+'/'+variant+'/tail',d/actual/'tail',case=case)
    os.symlink(actual,d/'relative');os.symlink('/'+str(i)+'/'+actual,d/'absolute')
    run('/'+str(i)+'/relative/tail',d/actual/'tail');run('/'+str(i)+'/absolute/tail',d/actual/'tail')
# A decomposed lookup can exceed NAME_MAX although the stored NFC name fits.
long=prefix/'long';long.mkdir();(long/('é'*100)).write_text('long')
run('/long/'+('e\u0301'*100),long/('é'*100))
# Corrected spelling must be followed as a symlink and retain loop bounds.
links=prefix/'links';links.mkdir();(links/'file').write_text('x')
os.symlink('file',links/'café');run('/links/cafe\u0301',links/'file');run('/links/cafe\u0301',links/'café',follow=0)
os.symlink('lóp',links/'lóp');run('/links/lo\u0301p','',status=-errno.ELOOP)
for i in range(32):os.symlink('file' if i==31 else f'café{i+1}',links/f'café{i}')
run('/links/cafe\u03010',links/'file');os.symlink('café0',links/'extra');run('/links/extra','',status=-errno.ELOOP)
# Exact byte spelling wins when Linux contains canonically equivalent aliases.
amb=prefix/'amb';amb.mkdir();(amb/'Å').write_text('one');(amb/'A\u030a').write_text('two')
run('/amb/Å',amb/'Å');run('/amb/A\u030a',amb/'A\u030a');run('/amb/Å','',status=-errno.ENOENT)
# Normalization is canonical, never compatibility folding; invalid bytes remain opaque.
(amb/'①').write_text('circle');run('/amb/1',amb/'1')
invalid=os.fsencode(amb)+b'/bad\xff';fd=os.open(invalid,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
run(b'/amb/bad\xff',invalid);run(b'/amb/bad\xfe',os.fsencode(amb)+b'/bad\xfe')
(amb/'MiXeD').write_text('case');run('/amb/mixed',amb/'MiXeD');run('/amb/mixed',amb/'mixed',case=0)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=dict(verified=True,checks=checks,check_count=len(checks),compile_command=command,source_files={str(p.relative_to(root)):sha(p) for p in [source,Path(__file__),root/'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/linux_premigration/vchroot_userspace.c']},host_test_only=True,native_darling_execution=False)
(folder/'result.json').write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n');print('VERIFIED',len(checks),'checks',folder/'result.json')
