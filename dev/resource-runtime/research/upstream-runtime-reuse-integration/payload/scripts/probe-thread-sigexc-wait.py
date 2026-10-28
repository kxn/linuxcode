#!/usr/bin/env python3
"""Actual XNU waitq and signal-entry host regression; no Darling session."""
from pathlib import Path
import argparse,hashlib,json,resource,runpy,shlex,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;build=root/'runtime/darlingserver-source-build'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--variants',nargs='+',choices=['candidate','historical'],default=['candidate','historical'])
a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='thread-sigexc-wait-',dir=root/'runtime'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inputs={};commands=[]
cpp=root/'fixtures/hello/thread-sigexc-wait.cpp';bridge=root/'fixtures/hello/thread-sigexc-wait-c.c'
csource=root/'vendor/darlingserver/duct-tape/src/thread.c'
def run(cmd):commands.append([str(x) for x in cmd]);subprocess.run(cmd,cwd=build,check=True)
def flags(target,src):
 text=subprocess.check_output(['ninja','-C',str(build),'-t','commands',target],text=True)
 command=next(shlex.split(l) for l in text.splitlines() if l.endswith(' -c '+str(src)))
 return command[:command.index('-MD')]
cflags=flags('darlingserver/duct-tape/CMakeFiles/darlingserver_duct_tape.dir/src/thread.c.o',csource)
cppflags=flags('darlingserver/CMakeFiles/darlingserver.dir/src/thread.cpp.o',root/'vendor/darlingserver/src/thread.cpp')
text=subprocess.check_output(['ninja','-C',str(build),'-t','commands','darlingserver/darlingserver'],text=True).splitlines()[-1]
link=shlex.split(text.split(' && ')[1]);private=[]
for item in link:
 if item.startswith('-Xlinker') or item.startswith('--dependency-file=') or item.endswith('darlingserver.cpp.o'):continue
 path=build/item
 if item.endswith(('.o','.a')):
  copy=folder/path.name
  if copy.exists():assert sha(copy)==sha(path)
  else:shutil.copyfile(path,copy)
  inputs[str(path.relative_to(root))]=sha(copy);private.append(str(copy))
 else:private.append(item)
oi=private.index('-o')+1
for source,fl,out in [(cpp,cppflags,folder/'fixture.o'),(bridge,cflags,folder/'bridge.o')]:
 snap=folder/source.name;shutil.copyfile(source,snap);inputs[str(source.relative_to(root))]=sha(snap)
 run(fl+['-c',str(snap),'-o',str(out)])
stagepath=root/'runtime/remap-diagnostic-server-scqr1r7d/stage.json';stage=json.loads(stagepath.read_text())
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
historical=root/resolve(str(csource.relative_to(root)),stage['source_files'][str(csource.relative_to(root))])
cases=['awaken-before-interrupt','interrupt-before-awaken','no-wait','uninterruptible'];codes=[14,16,11,19];results={}
for variant in a.variants:
 src=csource if variant=='candidate' else historical;snap=folder/(variant+'-thread.c');shutil.copyfile(src,snap)
 inputs[str(src.relative_to(root))]=sha(snap);obj=folder/(variant+'-thread.o');binary=folder/(variant+'-probe')
 run(cflags+['-x','c','-c',str(snap),'-o',str(obj)])
 cmd=private[:];cmd[oi]=str(binary)
 cmd[1:1]=[str(folder/'fixture.o'),str(folder/'bridge.o'),str(obj)]+['-Wl,--wrap='+n for n in [
 '_ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE','dtape_task_create','dtape_thread_create',
 'dtape_task_set_process_generation','dtape_thread_dying']]
 run(cmd);rows=[]
 for case in cases:
  prefix=folder/(variant+'-'+case);prefix.mkdir()
  r=subprocess.run([str(binary),case,str(prefix)],cwd=folder,capture_output=True,text=True,timeout=10,
                   preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
  output=r.stdout+r.stderr;(folder/(variant+'-'+case+'.log')).write_text(output)
  rows.append(dict(case=case,status=r.returncode,output=output));print(variant,case,r.returncode,output.strip(),flush=True)
 results[variant]=rows;inputs[str(binary.relative_to(root))]=sha(binary)
verified=all(row['status']==0 if v=='candidate' else row['status']==1 and ('code='+str(codes[i])+' ') in row['output']
             for v,rows in results.items() for i,row in enumerate(rows))
for source in [stagepath,Path(__file__)]:inputs[str(source.relative_to(root))]=sha(source)
report=dict(verified=verified,results=results,commands=commands,files=inputs,
 scope='Actual dtape_thread_sigexc_enter, XNU waitq_init/assert_wait/wakeup/pull, clear_wait_internal, thread_go/unblock and thread_block_parameter, actual C++ microthread scheduler/ucontext. Opaque task lifecycle/enqueue controlled; no full C++ InterruptEnter RPC, actual Mach semaphore transaction, native server, or Mach-O coverage.',
 negative_control='Exact stage107 C thread source (same sigexc implementation as stage108), linked with current read-only server objects. TH_UNINT state explicitly constructed because thread_mark_wait_locked currently ignores interruptibility; no claim to fix that separate API.')
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
