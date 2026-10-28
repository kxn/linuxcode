#!/usr/bin/env python3
"""Host-build the complete Darling-pinned libunwind source list, without installing it."""
from pathlib import Path
import argparse,hashlib,json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parent.parent
PIN='a91da1a0e262e04eb601152a84228ff733e48422'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);a=p.parse_args();source=a.source.resolve(strict=True);folder=a.output.resolve();baseline=a.baseline.resolve(strict=True);assert folder.is_relative_to(ROOT/'runtime') and not folder.exists();actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip();assert actual==PIN;assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True);assert subprocess.check_output(['git','-C',str(ROOT/'vendor/darling'),'ls-tree','HEAD','src/external/libunwind'],text=True).split()[2]==PIN
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest();rel=lambda path:str(path.relative_to(ROOT));(folder/'objects').mkdir(parents=True);(folder/'libraries').mkdir();cmake=source/'CMakeLists.txt';text=cmake.read_text();units=[]
for kind in ['CXX','C','ASM']:
 body=re.search(r'set\(LIBUNWIND_'+kind+r'_SOURCES\s+(.*?)\)',text,re.S)[1];units.extend((name,kind) for name in re.sub(r'#[^\n]*','',body).split())
assert len(units)==len(set(name for name,kind in units))==9
sdk=ROOT/'vendor/darling/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';guest=baseline.parents[3];assert (guest/'usr/lib/system/libsystem_c.dylib').is_file();record=dict(source_url='https://github.com/darlinghq/darling-libunwind.git',source_pin=PIN,source_actual_HEAD=actual,source_dirty=False,source=rel(source),source_CMake=rel(cmake),source_CMake_sha256=sha(cmake),upstream_Apple_tag='libunwind-201',complete_source_units=9,source_units=units,baseline_library=rel(baseline),baseline_sha256=sha(baseline),host_only=True,installed=False,runtime_execution_verified=False,Client_fault_fix_claimed=False,commands=[],source_dependencies={},compiler_headers={})
def save():
 record['builder']=rel(Path(__file__));record['builder_sha256']=sha(Path(__file__));(folder/'build.json').write_text(json.dumps(record,indent=2)+'\n')
objects=[]
for i,(name,kind) in enumerate(units):
 unit=source/name;obj=folder/'objects'/(str(i)+'-'+unit.stem+'.o');dep=obj.with_suffix('.d');log=obj.with_suffix('.log');cmd=['clang++-19' if kind=='CXX' else 'clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-I',str(source/'libunwind/include'),'-I',str(source/'libunwind/src'),'-I',str(ROOT/'vendor/darling/basic-headers'),'-idirafter',str(ROOT/'vendor/darling/src/external/xnu/EXTERNAL_HEADERS'),'-D_LIBUNWIND_IS_NATIVE_ONLY','-D__DARWIN_UNIX03','-DPLATFORM_MacOSX=1','-DDARLING=1','-fPIC','-funwind-tables','-O0','-g','-msse','-msse2','-msse3']
 if kind=='CXX':cmd+=['-nostdinc++','-I',str(ROOT/'vendor/darling/src/external/libcxx/include'),'-fno-rtti','-fno-exceptions','-std=c++11']
 cmd+=['-MD','-MF',str(dep),'-c',str(unit),'-o',str(obj)];record['commands'].append(cmd)
 with log.open('w') as out:result=subprocess.run(cmd,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
 if result.returncode:record['failure']=dict(unit=name,status=result.returncode,log=rel(log));save();print(log.read_text()[-4500:]);raise SystemExit(result.returncode)
 for spelling in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
  path=Path(spelling).resolve();mapping=record['source_dependencies'] if path.is_relative_to(ROOT) else record['compiler_headers'];mapping[rel(path) if path.is_relative_to(ROOT) else str(path)]=sha(path)
 objects.append(obj);save()
library=folder/'libraries/libunwind.dylib';cmd=['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-flat_namespace','-undefined','dynamic_lookup','-install_name','/usr/lib/system/libunwind.dylib','-compatibility_version','1.0.0','-current_version','0.0.0','-no_fixup_chains','-no_adhoc_codesign','-syslibroot',str(guest),'-L',str(guest/'usr/lib/system'),'-lsystem_c','-lkeymgr',*[str(o) for o in objects],'-o',str(library)];record['commands'].append(cmd)
with (folder/'link.log').open('w') as out:result=subprocess.run(cmd,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
record['link_status']=result.returncode
if result.returncode:save();print((folder/'link.log').read_text()[-4000:]);raise SystemExit(result.returncode)
def exports(path):return {line.split()[-1] for line in subprocess.check_output(['llvm-nm-19','--arch=x86_64','--defined-only','--extern-only',str(path)],text=True).splitlines() if line.strip()}
before=exports(baseline);after=exports(library);record.update(library=rel(library),library_sha256=sha(library),baseline_export_count=len(before),source_export_count=len(after),missing_baseline_exports=sorted(before-after),added_exports=sorted(after-before),objects={rel(o):sha(o) for o in objects},dynamic_FDE_exports_verified={'___unw_add_dynamic_fde','___unw_remove_dynamic_fde','___register_frame','___deregister_frame'}<=after);save();assert not before-after and record['dynamic_FDE_exports_verified'];print(folder/'build.json')
