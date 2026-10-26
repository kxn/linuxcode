#!/usr/bin/env python3
"""Recover a timed-out final link without recompiling unchanged complete objects.

The preceding successful plan must match every source except explicitly recorded
changes. This does not replace the original failed log or claim a fresh build.
"""
from pathlib import Path
import argparse,fcntl,hashlib,json,re,shutil,subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for name in ['template-report','failed-dir','failed-log','variant-base','report']:p.add_argument('--'+name,required=True)
p.add_argument('--changed-source',action='append',default=[]);a=p.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
d=json.loads((root/a.template_report).read_text());old=str(Path(d['variant_root']).parent);build=root/a.failed_dir
assert build.is_relative_to(root/'runtime') and not (root/a.report).exists()
manifest=[];objects=[];changes={};generated_changes={}
for row in d['sources']:
 row=dict(row);row['source']=row['source'].replace(old,a.failed_dir);row['command']=[x.replace(old,a.failed_dir) for x in row['command']]
 source=root/row['source'];actual=sha(source)
 if actual!=row['sha256']:
  if row['source'].startswith(a.failed_dir+'/generated/'):
   previous=root/row['source'].replace(a.failed_dir,old,1)
   normalize=lambda data:re.sub(rb'^ \* stub generated [^\n]*\n',b' * stub generated TIMESTAMP\n',data,flags=re.M)
   assert sha(previous)==row['sha256'] and normalize(previous.read_bytes().replace(old.encode(),a.failed_dir.encode()))==normalize(source.read_bytes()),row['source']
   generated_changes[row['source']]={'old':row['sha256'],'new':actual,'only_build_directory_or_MIG_timestamp_comment_changed':True}
  else:
   assert row['source'] in a.changed_source,row['source'];changes[row['source']]={'old':row['sha256'],'new':actual}
  row['sha256']=actual
 obj=Path(row['command'][row['command'].index('-o')+1]);assert obj.is_file();objects.append(obj);manifest.append(row)
assert set(changes)==set(a.changed_source)
filelist=build/'objects.filelist';guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
assert filelist.read_text()==''.join(guest(x)+'\n' for x in objects)
assert 'Compiled 901 / 906' in (root/a.failed_log).read_text() and 'TimeoutExpired' in (root/a.failed_log).read_text()
output=build/'libsystem_kernel.dylib';pending=build/'libsystem_kernel.relink-v1.dylib';assert not output.exists() and not pending.exists()
ld='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld';sdk='/Volumes/SystemRoot/usr/libexec/darling'
command=[str(root/'bin/darling'),'shell',ld,'-dylib','-arch','x86_64','-platform_version','macos','11','11','-bind_at_load','-no_compact_unwind','-install_name','/usr/lib/system/libsystem_kernel.dylib','-compatibility_version','1.0.0','-syslibroot',sdk,'-L',sdk+'/usr/lib/system','-lsystem_c','-lcompiler_rt','-ldyld','-lsystem_pthread','-lsystem_malloc','-lsystem_platform','-filelist',guest(filelist),'-o',guest(pending)]
recovery=dict(template=a.template_report,template_sha256=sha(root/a.template_report),failed_compile_log=a.failed_log,failed_compile_log_sha256=sha(root/a.failed_log),reconstructed_from_identical_preceding_compile_commands=True,explicit_source_changes=changes,generated_build_path_changes=generated_changes,objects={str(x.relative_to(root)):sha(x) for x in objects},link_command=command,tool_sha256=sha(Path(__file__)))
(build/'relink-v1-plan.json').write_text(json.dumps(recovery,indent=2)+'\n')
with (build/'relink-v1.log').open('w') as out:subprocess.run(command,check=True,timeout=120,stdout=out,stderr=subprocess.STDOUT)
assert pending.is_file();pending.replace(output)
variant=build/'darling-root';assert not variant.exists()
with (root/'runtime/session.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);subprocess.run(['cp','-a','--reflink=auto',str(root/a.variant_base),str(variant)],check=True);shutil.copy2(output,variant/'usr/lib/system/libsystem_kernel.dylib')
 for name in ['libquarantine.dylib','libsystem_sandbox.dylib','libdyld.dylib']:shutil.copy2(variant/'usr/lib/system'/name,build/name)
# Preserve the successful preceding export contract and check the recovered link.
import re
exports=lambda path:set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(path)],text=True),re.M))
old_binary=root/old/'libsystem_kernel.dylib';assert exports(old_binary)==exports(output)
d.update(sources=manifest,binary_sha256=sha(output),variant_root=str(variant.relative_to(root)),runtime_execution_verified=False,recovered_final_link=recovery)
(root/a.report).write_text(json.dumps(d,indent=2)+'\n');print('RECOVERED',a.report)
