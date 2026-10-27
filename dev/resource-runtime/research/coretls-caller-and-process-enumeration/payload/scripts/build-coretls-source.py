#!/usr/bin/env python3
"""Compile every configured CoreTLS unit into a coherent private runtime."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,hashlib,json,re,runpy,struct,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;repo=r/'vendor/darling/src/external/coretls'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-compilation',type=Path);a=p.parse_args()
folder=(r/a.reuse_compilation).resolve() if a.reuse_compilation else Path(tempfile.mkdtemp(prefix='coretls-source-',dir=r/'runtime'));assert folder.is_relative_to(r/'runtime') and not (folder/'build.json').exists();print('BUILDING',folder.relative_to(r),flush=True)
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';compat=folder/'include';(compat/'CommonCrypto').mkdir(parents=True,exist_ok=True)
common=r/'vendor/darling/src/external/commoncrypto/include'
for directory in ['Public','Private']:
    for source in (common/directory).glob('*.h'):
        target=compat/'CommonCrypto'/source.name
        if not target.exists():target.symlink_to(source)
for leaf,target in [('sys/codesign.h','bsd/sys/codesign.h'),('kern/cs_blobs.h','osfmk/kern/cs_blobs.h')]:
    path=compat/'System'/leaf;path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():path.symlink_to(r/'vendor/darling/src/external/xnu'/target)
cmake=(repo/'CMakeLists.txt').read_text();names=re.search(r'add_circular\(system_coretls\s+FAT\s+SOURCES(.*?)\s+SIBLINGS',cmake,re.S)[1].split();assert names and all((repo/n).is_file() and n.endswith('.c') for n in names)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
def compile_one(name):
    source=repo/name;obj=folder/(source.stem+'.o');log=folder/(source.stem+'.log')
    command=['clang-19','-target','x86_64-apple-macos11','-std=gnu99','-fblocks','-O2','-Wno-deprecated-declarations','-Wno-error=int-conversion','-DDARLING=1','-D__ASSERT_MACROS_DEFINE_VERSIONS_WITHOUT_UNDERSCORES=1','-DCCCBC_RETURN_INT','-DCORECRYPTO_DONOT_USE_TRANSPARENT_UNION','-isysroot',str(sdk),'-I',str(compat),'-I',str(repo/'lib'),'-I',str(r/'vendor/darling/src/external/corecrypto/include'),'-I',str(r/'vendor/darling/src/external/libxpc/include'),'-c',str(source),'-o',str(obj)]
    with log.open('w') as out:result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    return dict(source=str(source.relative_to(r)),source_sha256=sha(source),object=str(obj.relative_to(r)),object_sha256=sha(obj) if obj.exists() else None,command=command,status=result.returncode,log=str(log.relative_to(r)))
if a.reuse_compilation:
    units=json.loads((folder/'compile.json').read_text());assert [u['source'] for u in units]==[str((repo/n).relative_to(r)) for n in names]
    assert all(u['status']==0 and sha(r/u['source'])==u['source_sha256'] and sha(r/u['object'])==u['object_sha256'] for u in units)
    headers=[*(repo/'lib').glob('*.h'),*(repo/'lib').glob('*.inc'),*(r/'vendor/darling/src/external/corecrypto/include').rglob('*.h'),*(common/'Private').glob('*.h'),r/'vendor/darling/src/external/xnu/bsd/sys/codesign.h',r/'vendor/darling/src/external/xnu/osfmk/kern/cs_blobs.h']
    assert max(h.stat().st_mtime_ns for h in headers)<=min((r/u['object']).stat().st_mtime_ns for u in units),'Headers changed after compilation; use a fresh build'
else:
    with ThreadPoolExecutor(max_workers=8) as pool:units=list(pool.map(compile_one,names))
    (folder/'compile.json').write_text(json.dumps(units,indent=2)+'\n')
failed=[x for x in units if x['status']]
if failed:
    print('COMPILE_FAILED',len(failed),'of',len(units))
    for row in failed:
        errors=re.findall(r'^.*error: .*$',(r/row['log']).read_text(),re.M)
        print(row['source'],'\n'+'\n'.join(errors[:2]))
    raise SystemExit(1)
baseline=r/'runtime/rootfs/usr/libexec/darling/usr/lib/system/libsystem_coretls.dylib';crypto=r/'runtime/corecrypto-hkdf-source/libraries/libcorecrypto.dylib';libraries=folder/'libraries';libraries.mkdir(exist_ok=True);binary=libraries/'libsystem_coretls.dylib'
def exports(path):return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(path)],text=True),re.M))
old=exports(baseline);export_file=folder/'exports.txt';export_file.write_text('\n'.join(sorted(old|{'_tls_handshake_create_for_caller'}))+'\n')
command=['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-no_fixup_chains','-no_adhoc_codesign','-syslibroot',str(sdk),'-install_name','/usr/lib/system/libsystem_coretls.dylib','-compatibility_version','1','-current_version','167','-exported_symbols_list',str(export_file),*[str(r/u['object']) for u in units],str(crypto),'-lSystem','-o',str(binary)]
reused_link=binary.exists()
if not reused_link:
    with (folder/'link.log').open('w') as out:result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    if result.returncode:print((folder/'link.log').read_text()[-4500:]);raise SystemExit(1)
actual=exports(binary);assert actual==old|{'_tls_handshake_create_for_caller'}
umbrella=r/'runtime/rootfs/usr/libexec/darling/usr/lib/libcoretls.dylib';original=umbrella.read_bytes()
if original[:4]==b'\xca\xfe\xba\xbe':
    arches=[struct.unpack_from('>5I',original,8+20*i) for i in range(struct.unpack_from('>I',original,4)[0])];matches=[x for x in arches if x[0]==0x1000007];assert len(matches)==1;offset,size=matches[0][2:4];assert offset+size<=len(original);original=original[offset:offset+size]
payload,changes=runpy.run_path(str(r/'scripts/macho-named-reexport.py'))['add'](original,'/usr/lib/system/libsystem_coretls.dylib',sorted(actual));assert changes['original_instructions_and_other_bytes_preserved'];front=libraries/'libcoretls.dylib';assert not front.exists();front.write_bytes(payload)
record=dict(full_coretls_source_build=True,complete_source_files=len(units),sources=units,source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),headers={str(p.relative_to(r)):sha(p) for p in [repo/'CMakeLists.txt',*(repo/'lib').glob('*.h'),*(repo/'lib').glob('*.inc')]},baseline=str(baseline.relative_to(r)),baseline_sha256=sha(baseline),backend=str(binary.relative_to(r)),backend_sha256=sha(binary),umbrella=str(front.relative_to(r)),umbrella_sha256=sha(front),original_exports_preserved=len(old),new_exports=['_tls_handshake_create_for_caller'],original_umbrella_reexport=changes,corecrypto=str(crypto.relative_to(r)),corecrypto_sha256=sha(crypto),link_command=command,tool_sha256=sha(Path(__file__)),runtime_execution_verified=False,actual_TLS_handshake_verified=False,UE_build_verified=False)
record.update(compilation_reused=bool(a.reuse_compilation),existing_link_reused=reused_link,transitive_header_hashes_recorded_before_compilation=False,original_umbrella=str(umbrella.relative_to(r)),original_umbrella_sha256=sha(umbrella),x86_64_umbrella_slice_sha256=hashlib.sha256(original).hexdigest())
(folder/'build.json').write_text(json.dumps(record,indent=2)+'\n');print('CORETLS_SOURCE_BUILD',folder/'build.json')
