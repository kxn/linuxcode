#!/usr/bin/env python3
"""Reuse a complete failed-link build and recompile only explicit changed translation units.

The failed builder invocation, complete object list, source/header hashes and pinned
repositories must agree with a successful template. This is link recovery, not a
fresh full rebuild; original failure logs and objects are retained.
"""
from pathlib import Path
import argparse,fcntl,hashlib,json,re,shutil,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for n in ['template-report','failed-dir','failed-log','variant-base','report']:p.add_argument('--'+n,required=True)
p.add_argument('--changed-source',action='append',required=True);a=p.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
template=root/a.template_report;d=json.loads(template.read_text());old=str(Path(d['variant_root']).parent);build=root/a.failed_dir
assert build.is_relative_to(root/'runtime') and not (root/a.report).exists()
recovery=build/'source-link-recovery-v1';assert not recovery.exists();recovery.mkdir()
failed=root/a.failed_log;log=failed.read_text();total=d['complete_source_files']
assert f'Compiled {1+75*((total-1)//75)} / {total}' in log and 'Undefined symbols for architecture x86_64' in log and 'Source compilation failed' not in log
for name,commit in d['actual_source_repositories'].items():assert subprocess.check_output(['git','-C',str(root/name),'rev-parse','HEAD'],text=True).strip()==commit,name
for key in ['metadata_source_headers','source_list_headers']:
 for name,h in d[key].items():assert sha(root/name)==h,name
rows=[];objects=[];changes={};generated={};old_objects=[]
normalize=lambda b:re.sub(rb'^ \* stub generated [^\n]*\n',b' * stub generated TIMESTAMP\n',b,flags=re.M)
for row in d['sources']:
 row=dict(row);row['source']=row['source'].replace(old,a.failed_dir);row['command']=[s.replace(old,a.failed_dir) for s in row['command']];source=root/row['source'];h=sha(source)
 obj=Path(row['command'][row['command'].index('-o')+1]);assert obj.is_file();old_objects.append(obj)
 if h!=row['sha256']:
  if row['source'].startswith(a.failed_dir+'/generated/'):
   prev=root/row['source'].replace(a.failed_dir,old,1);assert sha(prev)==row['sha256'] and normalize(prev.read_bytes().replace(old.encode(),a.failed_dir.encode()))==normalize(source.read_bytes()),row['source'];generated[row['source']]=dict(old=row['sha256'],new=h)
  else:
   assert row['source'] in a.changed_source,row['source'];changes[row['source']]=dict(template_sha256=row['sha256'],current_sha256=h,failed_object_sha256=sha(obj))
   revised=recovery/obj.name;row['command'][row['command'].index('-o')+1]=str(revised)
   with (recovery/(obj.stem+'.compile.log')).open('w') as out:subprocess.run(row['command'],check=True,stdout=out,stderr=subprocess.STDOUT)
   obj=revised
  row['sha256']=h
 objects.append(obj);rows.append(row)
assert set(changes)==set(a.changed_source)
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
assert (build/'objects.filelist').read_text()==''.join(guest(p)+'\n' for p in old_objects)
filelist=recovery/'objects.filelist';filelist.write_text(''.join(guest(p)+'\n' for p in objects))
output=build/'libsystem_kernel.dylib';pending=recovery/'libsystem_kernel.dylib';assert not output.exists()
sdk='/Volumes/SystemRoot/usr/libexec/darling';cmd=[str(root/'bin/darling'),'shell','/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld','-dylib','-arch','x86_64','-platform_version','macos','11','11','-bind_at_load','-no_compact_unwind','-install_name','/usr/lib/system/libsystem_kernel.dylib','-compatibility_version','1.0.0','-syslibroot',sdk,'-L',sdk+'/usr/lib/system','-lsystem_c','-lcompiler_rt','-ldyld','-lsystem_pthread','-lsystem_malloc','-lsystem_platform','-filelist',guest(filelist),'-o',guest(pending)]
record=dict(template=a.template_report,template_sha256=sha(template),failed_log=a.failed_log,failed_log_sha256=sha(failed),explicit_source_changes=changes,generated_path_and_timestamp_only_changes=generated,reused_objects=len(objects)-len(changes),recompiled_objects=len(changes),objects={str(p.relative_to(root)):sha(p) for p in objects},link_command=cmd,tool_sha256=sha(Path(__file__)))
(recovery/'plan.json').write_text(json.dumps(record,indent=2)+'\n')
with (recovery/'link.log').open('w') as out:subprocess.run(cmd,check=True,timeout=120,stdout=out,stderr=subprocess.STDOUT)
exports=lambda p:set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(p)],text=True),re.M))
assert exports(root/old/'libsystem_kernel.dylib')==exports(pending)
pending.replace(output);variant=build/'darling-root';assert not variant.exists()
with (root/'runtime/session.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);subprocess.run(['cp','-a','--reflink=auto',str(root/a.variant_base),str(variant)],check=True);shutil.copy2(output,variant/'usr/lib/system/libsystem_kernel.dylib')
 for n in ['libquarantine.dylib','libsystem_sandbox.dylib','libdyld.dylib']:shutil.copy2(variant/'usr/lib/system'/n,build/n)
d.update(sources=rows,binary_sha256=sha(output),variant_root=str(variant.relative_to(root)),runtime_execution_verified=False,recovered_source_link=record)
(root/a.report).write_text(json.dumps(d,indent=2)+'\n');print('RECOVERED',a.report)
