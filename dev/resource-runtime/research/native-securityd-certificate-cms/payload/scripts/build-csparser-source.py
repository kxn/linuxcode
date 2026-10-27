#!/usr/bin/env python3
"""Build the upstream ANTLR code-requirement compiler as its actual bundle."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,plistlib,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--securityd-build',required=True);p.add_argument('--resume');a=p.parse_args()
security=json.loads((r/a.securityd_build).read_text());prior=(r/a.securityd_build).parent;state=json.loads((prior/'compile-state.json').read_text());s=r/'vendor/darling/src/external/security';module=s/'OSX/libsecurity_codesigning'
w=r/a.resume if a.resume else Path(tempfile.mkdtemp(prefix='csparser-source-',dir=r/'runtime'));assert w.is_relative_to(r/'runtime');print('BUILD',w.relative_to(r),flush=True)
prototype=state[str(s/'securityd/src/main.cpp')]['command'];common=prototype[:prototype.index('-MMD')]+['-I'+str(module/'antlr2')]
cmake=(module/'CMakeLists.txt').read_text();sources=[module/n for n in re.findall(r'^\s+(antlr2/src/[^\s]+\.cpp)\s*$',cmake,re.M)]+[module/'lib'/n for n in ['antlrplugin.cpp','RequirementLexer.cpp','RequirementParser.cpp']]
sources += [module/'lib/reqmaker.cpp',s/'OSX/libsecurity_cdsa_utilities/lib/cssmdata.cpp']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();attempt=len(list(w.glob('attempt-*')))+1;logs=w/f'attempt-{attempt}';logs.mkdir();cachefile=w/'compile-state.json';cache=json.loads(cachefile.read_text()) if cachefile.exists() else {}
def compile_one(row):
 i,source=row;obj=w/(str(i)+'.o');dep=w/(str(i)+'.d');command=[*common,'-MMD','-MF',str(dep),'-c',str(source),'-o',str(obj)]
 old=cache.get(str(source))
 if old and old['command']==command and obj.exists() and all(Path(n).exists() and sha(Path(n))==h for n,h in old['dependencies'].items()):return dict(source=str(source),object=str(obj),entry=old,reused=True)
 log=logs/(source.stem+'.log')
 with log.open('w') as out:res=subprocess.run(command,cwd=r,stdout=out,stderr=subprocess.STDOUT)
 if res.returncode:return dict(source=str(source),log=str(log),status=res.returncode)
 deps={n:sha(Path(n)) for n in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]) if Path(n).is_file()}
 return dict(source=str(source),object=str(obj),entry=dict(command=command,dependencies=deps),reused=False)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(compile_one,enumerate(sources)))
for row in rows:
 if 'entry' in row:cache[row['source']]=row['entry']
cachefile.write_text(json.dumps(cache,indent=2)+'\n');(logs/'compile.json').write_text(json.dumps(rows,indent=2)+'\n');failed=[v for v in rows if 'status' in v];print('COMPILED',len(rows)-len(failed),'REUSED',sum(v.get('reused',False) for v in rows),'FAILED',len(failed),flush=True)
if failed:
 for row in failed[:3]:print(Path(row['log']).read_text()[-2000:])
 raise SystemExit(1)
objects=[v['object'] for v in rows];undefined=set();defined=set()
for option,target in [('--undefined-only',undefined),('--defined-only',defined)]:
 listing=subprocess.check_output(['llvm-nm-19',option,'--format=posix',*objects],text=True,stderr=subprocess.DEVNULL);target.update(parts[0] for line in listing.splitlines() if len(parts:=line.split())>1)
base=r/security['backend'];assert sha(base)==security['backend_sha256'];backend=w/'libraries'/base.name;backend.parent.mkdir(exist_ok=True);payload,exports=runpy.run_path(str(r/'scripts/macho-nlist-exports.py'))['add'](base.read_bytes(),sorted(undefined-defined));backend.write_bytes(payload)
bundle=w/'csparser.bundle';binary=bundle/'Contents/MacOS/csparser';binary.parent.mkdir(parents=True,exist_ok=True);(bundle/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='org.linuxcode.csparser',CFBundleExecutable='csparser',CFBundlePackageType='BNDL',CFBundleVersion='1')))
guest=r/'runtime/rootfs/usr/libexec/darling';command=['ld64.lld-19','-bundle','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(guest),'-lSystem','-lc++','-framework','CoreFoundation',str(backend),*objects,'-exported_symbol','_findAntlrPlugin','--error-limit=0','-o',str(binary)]
with (logs/'link.log').open('w') as out:res=subprocess.run(command,cwd=r,stdout=out,stderr=subprocess.STDOUT)
(logs/'link.json').write_text(json.dumps(dict(command=command,exports=exports,status=res.returncode),indent=2)+'\n')
if res.returncode:print((logs/'link.log').read_text()[:6000]);raise SystemExit(res.returncode)
files={str(Path(__file__).relative_to(r)):sha(Path(__file__)),'scripts/macho-nlist-exports.py':sha(r/'scripts/macho-nlist-exports.py')}
for entry in cache.values():
 for n,h in entry['dependencies'].items():
  path=Path(n)
  if path.is_relative_to(r):files[str(path.relative_to(r))]=h
record=dict(bundle=str(bundle.relative_to(r)),binary=str(binary.relative_to(r)),binary_sha256=sha(binary),backend=str(backend.relative_to(r)),backend_sha256=sha(backend),backend_base=security['backend'],backend_base_sha256=sha(base),private_exports=exports,complete_source_files=len(sources),original_upstream_grammar=True,files=files,log=str((logs/'link.log').relative_to(r)),native_execution_verified=False)
(w/'build.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',w/'build.json')
