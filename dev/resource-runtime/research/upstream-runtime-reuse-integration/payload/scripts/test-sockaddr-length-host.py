#!/usr/bin/env python3
"""Test actual sockaddr/vchroot source with real Linux AF_UNIX sockets under ASan."""
from pathlib import Path
import hashlib,json,runpy,subprocess,tempfile
ROOT=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='sockaddr-length-host-',dir=ROOT/'runtime'));prefix=folder/'root';prefix.mkdir();source=ROOT/'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/network/duct.c';vchroot=ROOT/'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/linux_premigration/vchroot_userspace.c';family=ROOT/'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/conversion/network/duct.c';support=ROOT/'fixtures/hello/sockaddr-length-host-support.h';harness=ROOT/'fixtures/hello/sockaddr-length-host.c';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
template=json.loads((ROOT/'artifacts/host-io-registry-kernel-v2-build.json').read_text());oldrow=next(r for r in template['sources'] if r['source']==str(source.relative_to(ROOT)));resolve=runpy.run_path(str(ROOT/'scripts/resolve-evidence-history.py'))['resolve'];baseline=ROOT/resolve(oldrow['source'],oldrow['sha256']);assert sha(baseline)==oldrow['sha256'] and sha(baseline)!=sha(source)
common=['gcc','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Wno-unused-function','-Wno-implicit-function-declaration','-include',str(support),'-I'+str(ROOT/'runtime/darlingserver-source-build/include'),'-I'+str(ROOT/'runtime/mach-msg2-kernel-v1/generated/include')]
commands=[];objects=[]
for label,path in [('vchroot',vchroot),('family',family),('test',harness)]:
 obj=folder/(label+'.o');command=[*common,*(['-DTEST','-Dmain=vchroot_unused_test_main'] if label=='vchroot' else []),'-x','c','-c',str(path),'-o',str(obj)];commands.append(command);subprocess.run(command,check=True);objects.append(obj)
results=[]
for label,path in [('baseline',baseline),('fixed',source)]:
 obj=folder/(label+'.o');command=[*common,'-x','c','-c',str(path),'-o',str(obj)];commands.append(command);subprocess.run(command,check=True);program=folder/label;command=['gcc','-fsanitize=address,undefined',*[str(o) for o in objects],str(obj),'-o',str(program)];commands.append(command);subprocess.run(command,check=True);result=subprocess.run([str(program),str(prefix),label],capture_output=True,text=True);(folder/(label+'.log')).write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr;results.append(dict(case=label,exit_status=result.returncode,output=result.stdout.strip()))
record=dict(verified=True,host_test_only=True,actual_source_translation_units=[str(p.relative_to(ROOT)) for p in [source,vchroot,family]],ASan_UBSan=True,real_Linux_UNIX_listener_connect_accept=True,old_non_NUL_negative_control=True,results=results,commands=commands,files={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),source,vchroot,family,support,harness,baseline]},native_Darling_execution=False,UPM_or_Unity_modified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(folder/'result.json');print(json.dumps(results,indent=2))
