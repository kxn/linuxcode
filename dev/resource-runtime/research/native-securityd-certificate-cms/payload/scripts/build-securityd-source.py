#!/usr/bin/env python3
"""Build complete headless securityd and MIG dispatch from source in parallel.

Resume checks successful object inputs and reuses only identical compilations.
The opt-in backend exposes existing private definitions without changing code.
"""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,os,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resume');p.add_argument('--jobs',type=int,default=8);a=p.parse_args()
w=(r/a.resume).resolve() if a.resume else Path(tempfile.mkdtemp(prefix='securityd-source-',dir=r/'runtime'));assert w.is_relative_to(r/'runtime')
print('BUILD',w.relative_to(r),flush=True);s=r/'vendor/darling/src/external/security';d=r/'vendor/darling';sdk=d/'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';apple=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource=Path(subprocess.check_output(['clang-19','-print-resource-dir'],text=True).strip());gen=w/'generated';gen.mkdir(exist_ok=True);(gen/'securityd_client').mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();attempt=len(list(w.glob('attempt-*')))+1;logdir=w/f'attempt-{attempt}';logdir.mkdir()
header_repositories={name:subprocess.check_output(['git','-C',str(d/name),'rev-parse','HEAD'],text=True).strip() for name in ['src/external/commoncrypto','src/external/SmartCardServices','src/external/sqlite','src/external/SecurityTokend']}
includes=[gen,s/'securityd/src',s/'securityd',s/'keychain/KeychainStasher',s/'darling/include',s/'darling/include/macOS',s,s/'gen/derived_src',s/'gen/cstemp',s/'OSX/libsecurity_asn1',s/'OSX/libsecurity_keychain/lib',s/'OSX/sec',s/'OSX/sec/Security',s/'OSX/utilities',s/'OSX',s/'darling/src/libDER',s/'darling/include/Security',s/'darling/include/macOS/Security',s/'OSX/include',s/'OSX/libsecurity_cssm/lib',s/'OSX/utilities/src',s/'OSX/libsecurity_apple_csp/open_ssl',s/'OSX/libsecurityd/lib',s/'OSX/libsecurityd/mig',d/'src/external/libcxx/include',sdk/'usr/include',resource/'include']
includes += [d/'framework-include',d/'framework-private-include']
includes += [d/'src/external/SecurityTokend/lib',d/'src/external/SecurityTokend/mig']
defs=['-DDARLING','-DPRIVATE','-DPLATFORM_MacOSX','-D__DARWIN_UNIX03','-D__KEYCHAINCORE__=1','-DCORECRYPTO_DONOT_USE_TRANSPARENT_UNION=1','-DSECUREOBJECTSYNC=1','-DSHAREDWEBCREDENTIALS=0','-DPLATFORM=macOS','-DSECURITY_BUILD_VERSION="0"','-DNDEBUG=1','-DDTRACE_PROBES_DISABLED=1']
common=['-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc',*['-I'+str(x) for x in includes],'-idirafter',str(apple/'usr/include'),'-F',str(sdk/'System/Library/Frameworks'),*defs,'-fblocks','-fPIC','-O2','-g','-w']
mig=r/'runtime/darlingserver-source-build/build-mig';migcommands=[]
migstatefile=w/'mig-state.json';migstate=json.loads(migstatefile.read_text()) if migstatefile.exists() else {}
for name,src in [('self',s/'securityd/mig/self.defs'),('ucsp',s/'OSX/libsecurityd/mig/ucsp.defs'),('ucspNotify',s/'OSX/libsecurityd/mig/ucspNotify.defs'),('tokend',d/'src/external/SecurityTokend/mig/tokend.defs'),('mach_notify',s/'OSX/libsecurity_utilities/lib/mach_notify.defs')]:
    command=[str(mig),'-arch','x86_64','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc',*['-I'+str(x) for x in includes],*defs,'-user',str(gen/(name+'User.cpp')),'-header',str(gen/(name+'.h')),'-server',str(gen/(name+'Server.cpp')),'-sheader',str(gen/(name+'Server.h')),str(src)]
    migcommands.append(command)
    cpp=['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-nostdinc',*['-I'+str(x) for x in includes],*defs,'-E','-P','-x','c',str(src)]
    preprocessed=subprocess.check_output(cpp,cwd=r,stderr=subprocess.DEVNULL)
    key=hashlib.sha256(preprocessed+json.dumps(command).encode()+mig.read_bytes()).hexdigest()
    prior=migstate.get(name);outputs=[gen/(name+suffix) for suffix in ['User.cpp','.h','Server.cpp','Server.h']]
    if not(prior and prior['key']==key and all(n.is_file() and sha(n)==prior['outputs'].get(str(n)) for n in outputs)):
        with (logdir/(name+'-mig.log')).open('w') as out:subprocess.run(command,cwd=r,check=True,stdout=out,stderr=subprocess.STDOUT)
        migstate[name]=dict(key=key,outputs={str(n):sha(n) for n in outputs})
        migstatefile.write_text(json.dumps(migstate,indent=2)+'\n')
    if name!='self':
        link=gen/'securityd_client'/(name+'.h')
        if not link.exists():link.symlink_to('../'+name+'.h')
text=(s/'securityd/CMakeLists.txt').read_text();block=text.split('add_darling_executable(securityd_exe',1)[1].split('\n)',1)[0]
sources=[s/'securityd'/n for n in re.findall(r'^\s+(src/[^\s]+\.(?:cpp|m))\s*$',block,re.M)]
assert len(sources)==38,len(sources)
sources += [gen/(n+'.cpp') for n in ['selfServer','selfUser','ucspServer','ucspNotifyServer']]
sources += [s/'securityd/securityd_service/securityd_service/securityd_service_client.c']
sources += [gen/'tokendUser.cpp',d/'src/external/SecurityTokend/lib/tdclient.cpp',d/'src/external/SecurityTokend/lib/tdtransit.cpp']
for module in ['libsecurity_utilities','libsecurity_cdsa_utilities']:
    module_root=s/'OSX'/module;cmake=(module_root/'CMakeLists.txt').read_text()
    sources += [module_root/n for n in re.findall(r'^\s+((?:lib/|\.\./\.\./gen/)[^\s]+\.(?:cpp|c))\s*$',cmake,re.M)]
sources += [gen/'mach_notifyServer.cpp']
module_root=s/'OSX/libsecurity_cdsa_client';cmake=(module_root/'CMakeLists.txt').read_text()
sources += [module_root/n for n in re.findall(r'^\s+(lib/[^\s]+\.(?:cpp|c))\s*$',cmake,re.M)]
sources += [s/'OSX/libsecurityd/lib'/n for n in ['ssblob.cpp','sec_xdr_array.c','sec_xdr_reference.c','sec_xdr_sizeof.c','sec_xdr.c','sec_xdrmem.c','xdr_auth.c','xdr_cssm.c','xdr_dldb.cpp']]
statefile=w/'compile-state.json';state=json.loads(statefile.read_text()) if statefile.exists() else {};results=[]
def compile_one(row):
    i,src=row;obj=w/(str(i)+'-'+src.stem+'.o');dep=w/(str(i)+'.d');mig_c=src.name=='mach_notifyServer.cpp';isxx=src.suffix=='.cpp' and not mig_c
    command=['clang++-19' if isxx else 'clang-19',*common,*(['-nostdinc++','-std=c++14'] if isxx else []),*(['-x','c'] if mig_c else []),*(['-fobjc-arc'] if src.suffix=='.m' else []),'-MMD','-MF',str(dep),'-c',str(src),'-o',str(obj)]
    prior=state.get(str(src));key=sha(Path(__file__))
    if prior and prior.get('header_repositories')==header_repositories and prior['command']==command and obj.is_file() and all(Path(n).is_file() and sha(Path(n))==h for n,h in prior['dependencies'].items()):return dict(source=str(src),object=str(obj),reused=True,entry=prior)
    log=logdir/(str(i)+'-'+src.stem+'.log')
    with log.open('w') as out:res=subprocess.run(command,cwd=r,stdout=out,stderr=subprocess.STDOUT)
    if res.returncode:return dict(source=str(src),object=str(obj),reused=False,status=res.returncode,log=str(log))
    paths=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);dependencies={n:sha(Path(n)) for n in paths if Path(n).is_file()};dependencies[str(src)]=sha(src)
    return dict(source=str(src),object=str(obj),reused=False,entry=dict(command=command,dependencies=dependencies,header_repositories=header_repositories))
with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:results=list(pool.map(compile_one,enumerate(sources)))
for row in results:
    if 'entry' in row:state[row['source']]=row['entry']
statefile.write_text(json.dumps(state,indent=2)+'\n');failures=[v for v in results if 'status' in v]
(logdir/'compile.json').write_text(json.dumps(dict(results=results,migcommands=migcommands),indent=2)+'\n')
print('COMPILED',len(results)-len(failures),'REUSED',sum(v['reused'] for v in results),'FAILED',len(failures),flush=True)
if failures:
    for row in failures[:4]:print(row['source'],Path(row['log']).read_text()[-2000:],flush=True)
    raise SystemExit(1)
objects=[v['object'] for v in results];undefined=set();defined=set()
for option,target in [('--undefined-only',undefined),('--defined-only',defined)]:
    listing=subprocess.check_output(['llvm-nm-19',option,'--format=posix',*objects],text=True,stderr=subprocess.DEVNULL)
    target.update(parts[0] for line in listing.splitlines() if len(parts:=line.split())>1)
undefined-=defined
base=r/'runtime/local-identity-store-parent-candidates-v9/libraries/libDarlingLocalIdentitySecurityBackend.dylib';library=w/'libraries'/base.name;library.parent.mkdir(exist_ok=True)
payload,exports=runpy.run_path(str(r/'scripts/macho-nlist-exports.py'))['add'](base.read_bytes(),sorted(undefined));library.write_bytes(payload)
guest=r/'runtime/rootfs/usr/libexec/darling';binary=w/'securityd'
command=['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(guest),'-L',str(guest/'usr/lib'),'-L',str(guest/'usr/lib/system'),'-F',str(guest/'System/Library/PrivateFrameworks'),'-framework','AppleFSCompression','-framework','Foundation','-framework','PCSC','-framework','IOKit','-framework','CoreFoundation','-lobjc','-lDiagnosticMessagesClient','-lsqlite3','-lz','-lbsm.0','-lxar','-lSystem','-lc++',str(library),*objects,'-dead_strip','--error-limit=0','-o',str(binary)]
with (logdir/'link.log').open('w') as out:res=subprocess.run(command,cwd=r,stdout=out,stderr=subprocess.STDOUT)
(logdir/'link-inputs.json').write_text(json.dumps(dict(command=command,exports=exports,status=res.returncode),indent=2)+'\n')
if res.returncode:print((logdir/'link.log').read_text()[:7000]);raise SystemExit(res.returncode)
files={str(Path(__file__).relative_to(r)):sha(Path(__file__)),'scripts/macho-nlist-exports.py':sha(r/'scripts/macho-nlist-exports.py')}
for entry in state.values():
    for n,h in entry['dependencies'].items():
        path=Path(n)
        if path.is_relative_to(r):files[str(path.relative_to(r))]=h
record=dict(full_securityd_source_build=True,complete_source_files=len(sources),darling_macOS_named_sandbox_initialization=False,linux_namespace_and_host_permissions_unchanged=True,debug_graphics_or_TTY_session=False,binary=str(binary.relative_to(r)),binary_sha256=sha(binary),backend=str(library.relative_to(r)),backend_sha256=sha(library),backend_base=str(base.relative_to(r)),backend_base_sha256=sha(base),private_backend_exports=exports,files=files,build_log=str((logdir/'link.log').relative_to(r)),compile_report=str((logdir/'compile.json').relative_to(r)),source_runtime_installed=False,certificate_signing_verified=False)
(w/'build.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',w/'build.json')
