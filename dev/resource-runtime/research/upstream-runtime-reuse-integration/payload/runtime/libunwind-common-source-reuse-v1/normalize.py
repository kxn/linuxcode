from pathlib import Path
import hashlib,json,subprocess
root=Path.cwd();original=Path('runtime/libunwind-source-pin-a91da1-v2/build.json');d=json.loads(original.read_text());out=Path('runtime/libunwind-common-source-reuse-v1');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(Path(d['library']))==d['library_sha256']
assert sha(Path(d['baseline_library']))==d['baseline_sha256']
assert subprocess.check_output(['git','-C',d['source'],'rev-parse','HEAD'],text=True).strip()==d['source_pin']
assert not subprocess.check_output(['git','-C',d['source'],'status','--porcelain'],text=True)
def symbols(binary,*arguments):
 return {line.split()[-1] for line in subprocess.check_output(['llvm-nm-19','--arch=x86_64',*arguments,binary],text=True).splitlines() if line.strip()}
old_exports=symbols(d['baseline_library'],'--defined-only','--extern-only');new_exports=symbols(d['library'],'--defined-only','--extern-only');old_imports=symbols(d['baseline_library'],'--undefined-only');new_imports=symbols(d['library'],'--undefined-only');assert old_exports==new_exports and old_imports==new_imports
sources=[]
for index,(name,language) in enumerate(d['source_units']):
 path=Path(d['source'])/name;assert sha(path)==d['source_dependencies'][str(path)]
 sources.append(dict(source=str(path),sha256=sha(path),language=language,command=d['commands'][index]))
source_names={row['source'] for row in sources}
headers={name:digest for name,digest in d['source_dependencies'].items() if name not in source_names}
files={str(original):sha(original),d['source_CMake']:d['source_CMake_sha256'],d['builder']:d['builder_sha256'],d['library']:d['library_sha256'],**d['objects']}
report=dict(full_libunwind_source_build=True,complete_source_files=len(sources),sources=sources,source_headers=headers,compiler_headers=d['compiler_headers'],files=files,library=d['library'],library_sha256=d['library_sha256'],baseline_library=d['baseline_library'],baseline_library_sha256=d['baseline_sha256'],baseline_exports_preserved=len(old_exports),missing_original_exports=[],added_exports=[],source_export_count=len(new_exports),baseline_import_count=len(old_imports),source_import_count=len(new_imports),imports_identical=True,imports=sorted(new_imports),exports=sorted(new_exports),source_pin=d['source_pin'],upstream_Apple_tag=d['upstream_Apple_tag'],upstream_source=d['source_url'],source_CMake=d['source_CMake'],source_CMake_sha256=d['source_CMake_sha256'],original_build=str(original),original_build_sha256=sha(original),recompiled=False,relinked=False,reused_source_units=9,installed=False,native_verified=False,runtime_execution_verified=False,Client_fault_fix_claimed=False,full_goal_complete=False,scope='Complete existing Darling CMake x86_64 native libunwind module, nine translation units; not a new algorithm or all-architecture implementation',canonical_install_name='/usr/lib/system/libunwind.dylib',common_install_contract='Use existing stage-run-environment-launcher.py --source-library-build with this report. Install the same image in system root and shared prefix before bootstrap; index only at run-wide scope. No program-specific provider.',normalizer=str(out/'normalize.py'),normalizer_sha256=sha(out/'normalize.py'))
(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'build.json');print('exports',len(new_exports),'imports',len(new_imports),'source_units',len(sources))
