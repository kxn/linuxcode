#!/usr/bin/env python3
"""Freeze resource-aware xcrun scope in a new private pair of Darling roots."""
from pathlib import Path
import argparse, fcntl, hashlib, json, plistlib, re, runpy, shlex, shutil, subprocess
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag',required=True)
parser.add_argument('--resource-stage',required=True)
parser.add_argument('--libdyld-source-build',help='Optional verified private source build; preserve the existing pinned loader ABI')
args=parser.parse_args();assert re.fullmatch('[a-z0-9-]+',args.tag)
module=runpy.run_path(str(root/'scripts/ios-resource-closure-profile.py'))
legacy=runpy.run_path(str(root/'scripts/xcode-tool-dispatch-runtime-profile.py'))
report=root/('artifacts/resource-tool-dispatch-'+args.tag+'-stage.json')
folders={label:root/('runtime/resource-tool-dispatch-'+args.tag+'-'+label) for label in ['normal','diagnostic']}
assert not report.exists() and all(not p.exists() for p in folders.values()),'Keep previous runtime candidates immutable'
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
dyld_build=None
if args.libdyld_source_build:
 dyld_build=json.loads((root/args.libdyld_source_build).read_text())
 assert dyld_build['full_libdyld_source_build'] and dyld_build['complete_source_files']==29
 assert dyld_build['source_configuration']==json.loads((root/'config/libdyld-source-build.json').read_text())
 dyld_source=root/dyld_build['variant_root']/'usr/lib/system/libdyld.dylib'
 assert sha(dyld_source)==dyld_build['library_sha256']
 assert sha(root/dyld_build['variant_root']/'usr/lib/dyld')==dyld_build['source_configuration']['packaged_loader_sha256']
profiles={label:module['profile'](diagnostic=label=='diagnostic',stage=args.resource_stage) for label in folders}
records={}
with (root/'runtime/session.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 for label,folder in folders.items():
  p=profiles[label];old=p['tool_dispatch_selected_runtime'];base=root/old['variant_root'];folder.mkdir()
  variant=folder/'darling-root';subprocess.run(['cp','-a','--reflink=auto',str(base),str(variant)],check=True)
  original_source=next(name for name in old['files'] if name.endswith('/original-tools/xcrun'))
  original=folder/'original-tools/xcrun';original.parent.mkdir();shutil.copy2(root/original_source,original)
  assert sha(original)==old['files'][original_source]
  values=[arg for arg in p['command'] if arg.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH='))]
  fallback=[arg for arg in legacy['profile'](diagnostic=label=='diagnostic')['command'] if arg.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH='))]
  classification='''resource_target=
resource_query=0
resource_skip=0
for resource_argument in "$@"; do
    if [ "$resource_skip" = 1 ]; then resource_skip=0; continue; fi
    case "$resource_argument" in
        --sdk|-sdk|--toolchain|-toolchain) resource_skip=1 ;;
        --find|-find|-f|--show-sdk-*|-show-sdk-*|--help|-help|-h|--version|-version) resource_query=1 ;;
        --) resource_skip=0 ;;
        -*) ;;
        *) resource_target=$resource_argument; break ;;
    esac
done
if [ "$resource_query" = 0 ]; then
    case "$resource_target" in
        actool|ibtool)
'''
  content=('#!/bin/sh\n'+''.join('export '+shlex.quote(value)+'\n' for value in fallback)+classification
    +''.join('            export '+shlex.quote(value)+'\n' for value in values)
    +'            ;;\n    esac\nfi\nexec '+shlex.quote('/Volumes/SystemRoot/workspace/'+str(original.relative_to(root)))+' "$@"\n')
  wrapper=variant/'usr/bin/xcrun';wrapper.unlink();wrapper.write_text(content);wrapper.chmod(0o755)
  selected={key:dict(value) for key,value in p['source_runtime'].items()}
  for value in selected.values():
   destination=folder/Path(value['path']).name;shutil.copy2(root/value['path'],destination);assert sha(destination)==value['sha256'];value['path']=str(destination.relative_to(root))
  if dyld_build:
   destination=folder/'libdyld.dylib';shutil.copy2(dyld_source,destination)
   subprocess.run(['cp','-p','--reflink=auto',str(destination),str(variant/'usr/lib/system/libdyld.dylib')],check=True)
   selected['LINUXCODE_LIBDYLD']=dict(path=str(destination.relative_to(root)),sha256=sha(destination))
  version=variant/'System/Library/CoreServices/SystemVersion.plist'
  if dyld_build:
   assert plistlib.loads(version.read_bytes())['ProductVersion']==dyld_build['minimum_os']
  records[label]=dict(variant_root=str(variant.relative_to(root)),previous_source_runtime=p['source_runtime'],source_runtime=selected,system_version_binding=str(version.relative_to(root)),system_version_binding_sha256=sha(version),environment=values,fallback_environment=fallback,resource_tools=['actool','ibtool'],SDK_queries_keep_baseline_environment=True,
   files={str(path.relative_to(root)):sha(path) for path in [wrapper,original]},original_xcrun_source=original_source,original_xcrun_preserved=True,test_only_permissive_coreservices_policy=label=='diagnostic')
  if dyld_build:records[label]['libdyld_source_build']=dict(report=args.libdyld_source_build,sha256=sha(root/args.libdyld_source_build),minimum_os=dyld_build['minimum_os'],library_sha256=dyld_build['library_sha256'])
report.parent.mkdir(exist_ok=True)
report.write_text(json.dumps(dict(resource_stage=args.resource_stage,resource_stage_sha256=sha(root/args.resource_stage),runtimes=records,default_entry_promoted=False,persistent_prefix_modified=False,full_resource_compilation_verified=False),indent=2)+'\n')
print(report.relative_to(root))
