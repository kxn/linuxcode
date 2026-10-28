#!/usr/bin/env python3
"""Build the complete upstream Intel math component, including extra objects.

Read the source sets and alias lists from its existing CMake configuration.
Output remains private; neither the baseline library nor runtime is changed.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse,hashlib,json,re,shlex,subprocess

root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output-dir',required=True)
p.add_argument('--report',required=True)
a=p.parse_args()
folder=(root/a.output_dir).resolve();assert folder.is_relative_to(root/'runtime') and not folder.exists()
assert not (root/a.report).exists();folder.mkdir()
darling=root/'vendor/darling';component=darling/'src/libm'
sdk=darling/'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip())
cmake=component/'CMakeLists.txt';text=re.sub(r'#[^\n]*','',cmake.read_text())
sets=re.findall(r'set\(libm_sources\s+(.*?)\)',text,re.S)
assert len(sets)==2
sources=[component/name for group in sets for name in group.split() if name!='${libm_sources}']
extra=re.search(r'add_darling_object_library\(system_m_extra\s+(Source/Intel/.*?)\)',text,re.S)[1].split()
extra=[component/name for name in extra]
assert len(sources)>100 and len(extra)==6 and all(path.is_file() for path in sources+extra)
assert 'Source/Intel/log.S' in sets[1] and not any(path.name=='xmm_log.c' for path in sources)
headers=folder/'include';headers.mkdir();(headers/'System').symlink_to(darling/'src/external/xnu/osfmk',target_is_directory=True)
includes=[headers,darling/'src/external/xnu/EXTERNAL_HEADERS',component/'Source',darling/'src/libc/darwin',component/'Source/Intel',sdk/'usr/include',resource/'include']
flags=['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc',
       *['-I'+str(path) for path in includes],'-D__DARWIN_UNIX03','-fPIC','-w','-g','-O0',
       '-DBUILDING_FOR_CARBONCORE_LEGACY','-funroll-loops','-msse','-msse2','-msse3','-Dmovsxw=movsw','-DPRIVATE',
       '-Wno-error=int-conversion','-Wno-error=incompatible-pointer-types']
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
rows=[]
for index,(source,kind) in enumerate([(p,'source') for p in sources]+[(p,'extra') for p in extra]):
    obj=folder/(str(index)+'-'+source.stem+'.o');dep=folder/(str(index)+'.d')
    command=flags+(['-UBUILDING_FOR_CARBONCORE_LEGACY'] if kind=='extra' else [])+['-c',str(source),'-o',str(obj),'-MMD','-MF',str(dep)]
    rows.append(dict(source=str(source.relative_to(root)),sha256=sha(source),kind=kind,object=str(obj.relative_to(root)),command=command))
def compile_one(item):
    index,row=item
    with (folder/(str(index)+'.compile.log')).open('w') as out:
        result=subprocess.run(row['command'],stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Compilation failed: '+row['source']+'\n'+(folder/(str(index)+'.compile.log')).read_text()[-4000:])
with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(compile_one,enumerate(rows)))
dependencies={}
for dep in folder.glob('*.d'):
    for name in shlex.split(dep.read_text().split(':',1)[1].replace('\\\n',' ')):
        path=Path(name).resolve();dependencies[str(path.relative_to(root)) if path.is_relative_to(root) else str(path)]=sha(path)
print('COMPILED',len(rows),'complete libm units',flush=True)
baseline=root/'runtime/rootfs/usr/libexec/darling/usr/lib/system/libsystem_m.dylib'
sysroot=root/'runtime/rootfs/usr/libexec/darling';output=folder/'libsystem_m.dylib'
aliases=[component/'Exports/libm_Intel.a.alias',component/'Exports/libmathCommonIntel.alias']
alias_pairs=[]
for path in aliases:
    for line in path.read_text().splitlines():
        names=shlex.split(line,comments=True)
        if names:
            assert len(names)==2,(path,line)
            alias_pairs+=['-alias',*names]
command=['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11',
         '-install_name','/usr/lib/system/libsystem_m.dylib','-compatibility_version','1.0.0',
         '-syslibroot',str(sysroot),'-L',str(sysroot/'usr/lib/system'),'-lsystem_c','-ldyld',
         *[str(root/row['object']) for row in rows],*alias_pairs,
         '-no_adhoc_codesign','-no_fixup_chains','-o',str(output)]
with (folder/'link.log').open('w') as out:subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,check=True)
exports=lambda path:set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(path)],text=True),re.M))
old,new=exports(baseline),exports(output);missing=old-new;assert not missing,sorted(missing)
assert {'_log2','_log2$fenv_access_off','_log2f','_log2l'}<=new
report=dict(full_libm_source_build=True,complete_source_files=len(rows),source_units=len(sources),extra_units=len(extra),
            sources=rows,source_headers=dependencies,link_command=command,baseline=str(baseline.relative_to(root)),
            baseline_sha256=sha(baseline),baseline_exports_preserved=len(old),source_exports=len(new),missing_original_exports=sorted(missing),
            library=str(output.relative_to(root)),library_sha256=sha(output),runtime_execution_verified=False,
            files={str(path.relative_to(root)):sha(path) for path in [Path(__file__),cmake,*aliases]},full_goal_complete=False)
(root/a.report).write_text(json.dumps(report,indent=2)+'\n');print('BUILT',a.report,flush=True)
