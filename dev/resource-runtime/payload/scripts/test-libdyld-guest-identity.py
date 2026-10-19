#!/usr/bin/env python3
"""Check the selected libdyld identity and real loader lifetimes in a private runtime.

Requires the existing verified libdyld lifecycle fixtures. Does not promote a
runtime or infer macOS API compatibility from its declared deployment version.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, runpy, subprocess, tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dispatch-stage',required=True)
parser.add_argument('--diagnostic',action='store_true')
args=parser.parse_args()
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
m=runpy.run_path(str(root/'scripts/resource-tool-dispatch-profile.py'))
p=m['profile'](diagnostic=args.diagnostic,dispatch_stage=args.dispatch_stage)
chosen=p['resource_tool_dispatch_selected_runtime'];build=chosen['libdyld_source_build']
version=[int(x) for x in build['minimum_os'].split('.')];version+=(3-len(version))*[0]
expected=(version[0]<<16)|(version[1]<<8)|version[2]
folder=Path(tempfile.mkdtemp(prefix='libdyld-guest-identity-test-',dir=root/'runtime'))
gu= lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(root))
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=root/'fixtures/hello/xcrun-host-version.c';obj=folder/'provider.o';binary=folder/'provider'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-fblocks','-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(root/'runtime/rootfs/usr/libexec/darling'),'-L',str((root/p['source_runtime']['LINUXCODE_LIBDYLD']['path']).parent),'-ldyld','-lSystem',str(obj),'-o',str(binary)],check=True)
old_name='artifacts/dyld-dlopen-header-source.json';old=json.loads((root/old_name).read_text())
assert old['runtime_execution_verified'] and old['all_real_lifecycle_markers_verified']
lifecycle=root/'artifacts/dyld-dlopen-header';assert sha(lifecycle)==old['test_binary_sha256']
for name,value in old['tested_fixture_files'].items():assert sha(root/name)==value,name
lifecycle_markers=['DYLD_DLOPEN_HEADER_API_OWNED_BY_ACTUAL_LIBDYLD_OK',
 'DYLD_DLOPEN_HEADER_REAL_NO_EXPORTS_FIRST_MULTIPLE_REFERENCES_UNLOAD_INVALID_HANDLES_AND_DLERROR_OK',
 'DYLD_DLOPEN_HEADER_REAL_REEXPORT_OWNER_AND_DYLIB_RTLD_SELF_CALLER_OK',
 'DYLD_DLOPEN_HEADER_REAL_DUPLICATE_MODULE_NAMES_AND_UNLINK_INVALIDATION_OK',
 'DYLD_DLOPEN_HEADER_REAL_EIGHT_THREADS_512_DLOPEN_QUERY_DLCLOSE_CYCLES_OK']
fixtures=root/'runtime/libdyld-source/fixtures'
entries=[('provider',[gu(binary)],[f'XCRUN_HOST_PROVIDER /usr/lib/system/libdyld.dylib',f'XCRUN_HOST_VERSION 1 720896 {expected}','XCRUN_HOST_CALLBACKS 1']),
 ('lifecycle',[gu(lifecycle),*[gu(fixtures/name) for name in ['empty.dylib','reexport.dylib','empty.bundle']]],lifecycle_markers),
 ('snapshot',[gu(root/'artifacts/dyld-process-snapshot'),gu(root/'runtime/dyld-cache-introspection/fixture.dylib')],['REAL_DYLD_PROCESS_SNAPSHOT_MACH_IMAGES_UUID_SEGMENTS_CONTENT_LOAD_UNLOAD_FROZEN_STATE_RIGHTS_OK']),
 ('tlv',[gu(root/'artifacts/metadata-thread-local')],['ORIGINAL_METADATA_EXPORTED_TLV_THREE_THREADS_ZERO_INITIALIZATION_DISTINCT_STORAGE_ISOLATION_OK'])]
env=m['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
cases=[]
for name,tail,markers in entries:
 command=p['command'][:-2]+['/usr/bin/env','-u','DISPLAY','-u','WAYLAND_DISPLAY','-u','XAUTHORITY',*tail];command[3]='90'
 log=folder/(name+'.log')
 with log.open('w') as out:r=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
 text=log.read_text();suffix=r' [1-9][0-9]*' if name=='snapshot' else '';valid=r.returncode==0 and all(re.search('^'+re.escape(value)+suffix+'$',text,re.M) for value in markers)
 cases.append(dict(name=name,command=command,exit_status=r.returncode,verified=valid,log=str(log.relative_to(root)),log_sha256=sha(log),expected_markers=markers,executed_files={str(Path(path.removeprefix('/Volumes/SystemRoot/workspace/'))):sha(root/path.removeprefix('/Volumes/SystemRoot/workspace/')) for path in tail}))
 print(name,r.returncode,valid,text[-1600:],flush=True)
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),dispatch_stage=args.dispatch_stage,dispatch_stage_sha256=sha(root/args.dispatch_stage),source_runtime=p['source_runtime'],expected_minimum_os=build['minimum_os'],SDK_version='11',cases=cases,all_verified=all(c['verified'] for c in cases),test_driver_sha256=sha(__file__),provider_source_sha256=sha(source),lifecycle_fixture_report=old_name,lifecycle_fixture_report_sha256=sha(root/old_name),gui_environment_removed=['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY'],full_macOS_API_compatibility_verified=False,default_runtime_changed=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',folder/'result.json',flush=True)
raise SystemExit(0 if record['all_verified'] else 1)
