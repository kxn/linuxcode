#!/usr/bin/env python3
"""Build complete headless trustd and its ARC-managed trust library from source.

Resume checks successful object inputs and reuses only identical compilations.
The opt-in backend exposes existing private definitions without changing code.
"""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,os,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resume');p.add_argument('--jobs',type=int,default=8);a=p.parse_args()
w=(r/a.resume).resolve() if a.resume else Path(tempfile.mkdtemp(prefix='trustd-source-',dir=r/'runtime'));assert w.is_relative_to(r/'runtime')
print('BUILD',w.relative_to(r),flush=True);s=r/'vendor/darling/src/external/security';d=r/'vendor/darling';sdk=d/'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';apple=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip());gen=w/'generated';gen.mkdir(exist_ok=True);(gen/'securityd_client').mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();attempt=len(list(w.glob('attempt-*')))+1;logdir=w/f'attempt-{attempt}';logdir.mkdir()
header_repositories={name:subprocess.check_output(['git','-C',str(d/name),'rev-parse','HEAD'],text=True).strip() for name in ['src/external/commoncrypto','src/external/SmartCardServices','src/external/sqlite','src/external/SecurityTokend']}
includes=[gen,s/'securityd/src',s/'securityd',s/'keychain/KeychainStasher',s/'darling/include',s/'darling/include/macOS',s,s/'gen/derived_src',s/'gen/cstemp',s/'OSX/libsecurity_asn1',s/'OSX/libsecurity_keychain/lib',s/'OSX/sec',s/'OSX/sec/Security',s/'OSX/utilities',s/'OSX',s/'darling/src/libDER',s/'darling/include/Security',s/'darling/include/macOS/Security',s/'OSX/include',s/'OSX/libsecurity_cssm/lib',s/'OSX/utilities/src',s/'OSX/libsecurity_apple_csp/open_ssl',s/'OSX/libsecurityd/lib',s/'OSX/libsecurityd/mig',d/'src/external/libcxx/include',sdk/'usr/include',resource/'include']
includes += [d/'framework-include',d/'framework-private-include']
includes += [d/'src/external/SecurityTokend/lib',d/'src/external/SecurityTokend/mig']
defs=['-DDARLING','-DPRIVATE','-DPLATFORM_MacOSX','-D__DARWIN_UNIX03','-D__KEYCHAINCORE__=1','-DCORECRYPTO_DONOT_USE_TRANSPARENT_UNION=1','-DSECUREOBJECTSYNC=1','-DSHAREDWEBCREDENTIALS=0','-DPLATFORM=macOS','-DSECURITY_BUILD_VERSION="0"','-DNDEBUG=1','-DDTRACE_PROBES_DISABLED=1']
common=['-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc',*['-I'+str(x) for x in includes],'-idirafter',str(apple/'usr/include'),'-F',str(sdk/'System/Library/Frameworks'),*defs,'-fblocks','-fPIC','-O2','-g','-w']

defs += ['-DLIBTRUSTD=1','-DSECITEM_SHIM_OSX=1','-DSEC_IOS_ON_OSX=1']
common += defs[-3:]
text=(s/'trust/trustd/CMakeLists.txt').read_text();block=text.split('add_lib_ios_shim(libtrustd',1)[1].split('\n)',1)[0]
sources=[(s/'trust/trustd'/n).resolve() for n in re.findall(r'^\s+([^\s]+\.(?:c|m))\s*$',block,re.M)]
sources += [s/'OSX/sec/ipc/server_entitlement_helpers.c',s/'trust/trustd/trustd.c',s/'OSX/sec/ipc/util.m']
sources += [s/'OSX/utilities'/n for n in ['SecDb.c','sec_action.c','SecAppleAnchor.c','SecPLWrappers.m','SecFileLocations.c','SecAutorelease.m']]
sources += [s/'OSX/libsecurity_asn1/lib/oidsocsp.c']
assert len(sources)==38,len(sources)
statefile=w/'compile-state.json';state=json.loads(statefile.read_text()) if statefile.exists() else {}
def compile_one(row):
    i,src=row;obj=w/(str(i)+'-'+src.stem+'.o');dep=w/(str(i)+'.d')
    extras=[]
    if src.name in ['OTATrustUtilities.m','SecRevocationNetworking.m','trustdFileLocations.m']:
        extras=['-include',str(r/'fixtures/hello/trustd-build-declarations.h')]
    if src.name=='md.m':extras+=['-I'+str(d/'src/external/libnetwork/include')]
    if src.name=='SecPolicyServer.c':extras+=['-I'+str(d/'src/external/configd')]
    command=['clang-19',*extras,*common,*(['-fobjc-arc'] if src.suffix=='.m' else []),'-MMD','-MF',str(dep),'-c',str(src),'-o',str(obj)];prior=state.get(str(src))
    if prior and prior['command']==command and obj.is_file() and all(Path(n).is_file() and sha(Path(n))==h for n,h in prior['dependencies'].items()):return dict(source=str(src),object=str(obj),reused=True,entry=prior)
    log=logdir/(str(i)+'-'+src.stem+'.log')
    with log.open('w') as out:res=subprocess.run(command,cwd=r,stdout=out,stderr=subprocess.STDOUT)
    if res.returncode:return dict(source=str(src),object=str(obj),status=res.returncode,log=str(log),reused=False)
    paths=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);dependencies={n:sha(Path(n)) for n in paths if Path(n).is_file()};dependencies[str(src)]=sha(src)
    return dict(source=str(src),object=str(obj),reused=False,entry=dict(command=command,dependencies=dependencies))
with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:results=list(pool.map(compile_one,enumerate(sources)))
for row in results:
    if 'entry' in row:state[row['source']]=row['entry']
statefile.write_text(json.dumps(state,indent=2)+'\n');failures=[v for v in results if 'status' in v]
(logdir/'compile.json').write_text(json.dumps(results,indent=2)+'\n');print('COMPILED',len(results)-len(failures),'REUSED',sum(v['reused'] for v in results),'FAILED',len(failures),flush=True)
if failures:
    for row in failures[:5]:print(row['source'],Path(row['log']).read_text()[-2000:],flush=True)
    raise SystemExit(1)
objects=[v['object'] for v in results];undefined=set();defined=set()
for option,target in [('--undefined-only',undefined),('--defined-only',defined)]:
    listing=subprocess.check_output(['llvm-nm-19',option,'--format=posix',*objects],text=True,stderr=subprocess.DEVNULL);target.update(parts[0] for line in listing.splitlines() if len(parts:=line.split())>1)
undefined-=defined
base=r/'runtime/local-identity-store-chain-parent-candidates-v15/libraries/libDarlingLocalIdentitySecurityBackend.dylib';library=w/'libraries'/base.name;library.parent.mkdir(exist_ok=True)
payload,exports=runpy.run_path(str(r/'scripts/macho-nlist-exports.py'))['add'](base.read_bytes(),sorted(undefined));library.write_bytes(payload)
guest=r/'runtime/rootfs/usr/libexec/darling';binary=w/'trustd'
command=['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(guest),'-L',str(guest/'usr/lib'),'-L',str(guest/'usr/lib/system'),'-F',str(guest/'System/Library/PrivateFrameworks'),*sum((['-framework',n] for n in ['Foundation','CoreFoundation','CFNetwork','Network','MobileAsset']),[]),'-lobjc','-lsqlite3','-lz','-lbsm.0','-lSystem',str(library),*objects,'-dead_strip','--error-limit=0','-o',str(binary)]
with (logdir/'link.log').open('w') as out:res=subprocess.run(command,cwd=r,stdout=out,stderr=subprocess.STDOUT)
(logdir/'link-inputs.json').write_text(json.dumps(dict(command=command,exports=exports,status=res.returncode),indent=2)+'\n')
if res.returncode:print((logdir/'link.log').read_text()[:6000]);raise SystemExit(res.returncode)
record=dict(full_trustd_source_build=True,ARC_for_all_ObjC_units=True,complete_source_files=len(sources),recompiled=sum(not v['reused'] for v in results),reused=sum(v['reused'] for v in results),binary=str(binary.relative_to(r)),binary_sha256=sha(binary),backend=str(library.relative_to(r)),backend_sha256=sha(library),sources={str(p.relative_to(r)):sha(p) for p in [Path(__file__),s/'trust/trustd/CMakeLists.txt',*sources]},build_directory=str(w.relative_to(r)),command=command,source_exports=exports,installed=False)
(w/'build.json').write_text(json.dumps(record,indent=2)+'\n');print('BUILT',w/'build.json')
