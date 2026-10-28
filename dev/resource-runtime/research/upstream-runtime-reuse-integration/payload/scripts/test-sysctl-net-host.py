#!/usr/bin/env python3
"""Exercise the real routing sysctl source with Darwin ABI headers and Linux interfaces."""
from pathlib import Path
import hashlib,json,runpy,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='sysctl-net-host-',dir=root/'runtime'))
source='vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/misc/sysctl_net.c'
template_path='artifacts/socketaddr-length-kernel-unified-v5-build.json'
template=json.loads((root/template_path).read_text());row=next(r for r in template['sources'] if r['source']==source)
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve'];baseline=resolve(source,row['sha256'])
command=list(row['command']);command[command.index('-target')+1]='x86_64-unknown-linux-gnu'
command[1:1]=['-x','c']
command+=['-D__APPLE__=1','-D__MACH__=1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-O1']
commands=[]
def compile(path,label):
    c=list(command);c[c.index('-c')+1]=str(root/path);c[c.index('-o')+1]=str(folder/(label+'.o'));commands.append(c);subprocess.run(c,check=True);return folder/(label+'.o')
prefix='vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/'
objects=[compile(prefix+'xnu_syscall/bsd/helper/misc/readline.c','readline'),compile(prefix+'conversion/errno.c','errno'),compile('fixtures/hello/sysctl-net-host.c','test')]
support=folder/'linux.o';c=['clang-19','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-c',str(root/'fixtures/hello/sysctl-net-host-linux.c'),'-o',str(support)];commands.append(c);subprocess.run(c,check=True);objects.append(support)
results=[]
for label,path in [('baseline',baseline),('candidate',source)]:
    obj=compile(path,label);output=folder/label;c=['gcc','-fsanitize=address,undefined',*[str(p) for p in objects],str(obj),'-ldl','-o',str(output)];commands.append(c);subprocess.run(c,check=True);result=subprocess.run([str(output),label],capture_output=True,text=True);(folder/(label+'.log')).write_text(result.stdout+result.stderr);print(label,result.returncode,result.stdout,result.stderr,flush=True);assert result.returncode==0
    results.append(dict(case=label,status=result.returncode,output=result.stdout.strip()))
files=[source,baseline,'fixtures/hello/sysctl-net-host.c','fixtures/hello/sysctl-net-host-support.h','fixtures/hello/sysctl-net-host-linux.c',str(Path(__file__).relative_to(root))]
report=dict(verified=True,host_only=True,native_Darling_execution=False,actual_source=source,actual_Darwin_SDK_routing_headers=True,real_Linux_libc_interface_enumeration=True,ASan_UBSan=True,results=results,commands=commands,files={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files})
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'result.json')
