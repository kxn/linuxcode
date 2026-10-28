#!/usr/bin/env python3
"""Host controls for actual Darwin network wrappers and Linux socket syscalls."""
from pathlib import Path
import hashlib,json,os,resource,runpy,subprocess,tempfile
ROOT=Path(__file__).resolve().parent.parent;folder=Path(tempfile.mkdtemp(prefix='network-optional-address-host-',dir=ROOT/'runtime'));runtime=folder/'root';runtime.mkdir();base=ROOT/'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src';network=base/'xnu_syscall/bsd/impl/network';fixture=ROOT/'fixtures/hello/network-optional-address-host.c';support=ROOT/'fixtures/hello/sockaddr-length-host-support.h';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();resolve=runpy.run_path(str(ROOT/'scripts/resolve-evidence-history.py'))['resolve'];template=json.load(open(ROOT/'artifacts/socketaddr-length-kernel-unified-v5-build.json'));sources=[network/(n+'.c') for n in ['accept','sendmsg','recvmsg','sendto','recvfrom','getpeername','getsockname']]+[base/'conversion/network/duct.c',base/'conversion/network/recvmsg.c',base/'xnu_syscall/bsd/helper/network/duct.c',base/'linux_premigration/vchroot_userspace.c',fixture];common=['gcc','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-ftrivial-auto-var-init=pattern','-Wno-unused-function','-Wno-implicit-function-declaration','-include',str(support),'-I'+str(ROOT/'runtime/darlingserver-source-build/include'),'-I'+str(ROOT/'runtime/mach-msg2-kernel-v1/generated/include')];commands=[];objects=[]
def compile(source,label):
 obj=folder/(label+'.o');cmd=[*common,*(['-DTEST','-Dmain=vchroot_unused_test_main'] if source.name=='vchroot_userspace.c' else []),'-x','c','-c',str(source),'-o',str(obj)];commands.append(cmd);subprocess.run(cmd,check=True);return obj
for i,source in enumerate(sources):objects.append(compile(source,str(i)+'-'+source.stem))
results=[]
for label,changed in [('fixed',None),('baseline-accept','accept'),('baseline-sendmsg','sendmsg'),('baseline-sendto','sendto')]:
 selected=list(objects)
 if changed:
  path=network/(changed+'.c');row=next(r for r in template['sources'] if r['source']==str(path.relative_to(ROOT)));old=ROOT/resolve(row['source'],row['sha256']);assert sha(old)==row['sha256'];selected[sources.index(path)]=compile(old,label)
 program=folder/label;cmd=['gcc','-fsanitize=address,undefined',*[str(o) for o in selected],'-o',str(program)];commands.append(cmd);subprocess.run(cmd,check=True)
 result=subprocess.run([str(program),str(runtime),label],capture_output=True,text=True,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)),timeout=8);(folder/(label+'.log')).write_text(result.stdout+result.stderr)
 if label=='baseline-accept':assert result.returncode!=0 and ('null pointer' in result.stderr or 'AddressSanitizer' in result.stderr)
 else:assert result.returncode==0,result.stdout+result.stderr
 # A crashing baseline leaves its owned Unix pathname; remove only this known path.
 (runtime/'s').unlink(missing_ok=True)
 results.append(dict(case=label,status=result.returncode,stdout=result.stdout.strip(),expected_old_null_pointer_failure=label=='baseline-accept'))
record=dict(verified=True,host_only=True,actual_Linux_socket_syscalls=True,ASan_UBSan=True,stack_pattern_initialization=True,results=results,commands=commands,files={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),fixture,support,*sources]},native_Darling_execution=False);(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(folder/'result.json');print(json.dumps(results,indent=2))
