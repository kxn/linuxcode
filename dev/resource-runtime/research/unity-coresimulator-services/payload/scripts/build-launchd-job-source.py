#!/usr/bin/env python3
"""Build all launchd units into a fresh root, preserving a selected source runtime."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shutil, subprocess
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-stage',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--report',required=True);a=p.parse_args()
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
config=json.loads((root/'config/launchd-source-build.json').read_text());parent=json.loads((root/a.parent_stage).read_text())
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for n,d in parent['files'].items():resolve(n,d)
darling=root/config['darling_source']
assert subprocess.check_output(['git','-C',str(darling),'rev-parse','HEAD'],text=True).strip()==config['darling_commit']
for n,c in config['header_repositories'].items():assert subprocess.check_output(['git','-C',str(root/n),'rev-parse','HEAD'],text=True).strip()==c
assert sha(root/config['original_launchd'])==config['original_launchd_sha256']
build=root/a.output_dir;report=root/a.report
assert build.is_relative_to(root/'runtime') and not build.exists() and not report.exists();build.mkdir()
source=darling/'src/launchd/src';sdk=darling/'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
apple=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip());mig=root/'runtime/darlingserver-source-build/build-mig'
common=['-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc','-DDARLING','-DPRIVATE','-Dxpc_domain_server=job_server','-DPLATFORM_MacOSX','-D__DARWIN_UNIX03',*['-I'+str(q) for q in [source,darling/'src/launchd/liblaunch',build,darling/'src/external/libxpc/include',sdk/'usr/include',resource/'include']]]
commands=[];log=build/'build.log'
with log.open('w') as out:
 def run(cmd):
  commands.append(cmd);subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
 cmake=(source/'CMakeLists.txt').read_text()
 for name in re.findall(r'^mig\((\w+)\.defs\)',cmake,re.M):
  run([str(mig),'-arch','x86_64',*common,'-user',str(build/(name+'User.c')),'-header',str(build/(name+'.h')),'-server',str(build/(name+'Server.c')),'-sheader',str(build/(name+'Server.h')),str(source/(name+'.defs'))])
 section=re.search(r'set\(launchd_sources\s+(.*?)\n\)',cmake,re.S)[1];sources=[]
 for line in section.splitlines():
  line=line.strip()
  if line.startswith('#') or not line.endswith('.c'):continue
  sources.append(build/line.rsplit('/',1)[-1] if '${CMAKE_CURRENT_BINARY_DIR}/' in line else source/line)
 assert len(sources)==16;objects=[]
 for q in sources:
  obj=build/(q.stem+'.o');objects.append(str(obj));print('Compile',q.name,flush=True)
  run(['clang-19',*common,'-F',str(sdk/'System/Library/Frameworks'),'-idirafter',str(apple/'usr/include'),'-include',str(sdk/'usr/include/sys/fileport.h'),'-fblocks','-O2','-Wno-deprecated-declarations','-Wno-incompatible-pointer-types','-Wno-implicit-function-declaration','-Wno-int-conversion','-Wno-nullability-completeness','-Wno-macro-redefined','-c',str(q),'-o',str(obj)])
 base=(root/parent['source_runtime']['LINUXCODE_LIBXPC']['path']).parent/'darling-root';assert base.is_dir()
 run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(base),'-L',str(base/'usr/lib'),'-lbsm.0','-lSystem',*objects,'-o',str(build/'launchd')])
 macros=subprocess.check_output(['clang-19',*common,'-E','-dM','-x','c',str(source/'config.h')],text=True);assert '#define HAVE_SANDBOX 1' in macros
variant=build/'darling-root';subprocess.run(['cp','-a','--reflink=auto',str(base),str(variant)],check=True);shutil.copy2(build/'launchd',variant/'sbin/launchd')
inputs=[Path(__file__),root/a.parent_stage,source/'config.h',source/'core.h',source/'runtime.h',source/'CMakeLists.txt',source/'service_stats.h',*sources]
d=dict(full_launchd_source_build=True,complete_source_files=len(sources),binary=str((build/'launchd').relative_to(root)),binary_sha256=sha(build/'launchd'),variant_root=str(variant.relative_to(root)),parent_stage=a.parent_stage,commands=commands,log=str(log.relative_to(root)),log_sha256=sha(log),source_files={str(q.relative_to(root)):sha(q) for q in inputs},sandbox_queries_enabled=True,runtime_execution_verified=False,full_goal_complete=False)
report.write_text(json.dumps(d,indent=2)+'\n');print(report.relative_to(root))
