#!/usr/bin/env python3
"""Prepare an isolated real Mach-O API probe and merged private provider scope."""
from pathlib import Path
import argparse,hashlib,json,os,re,runpy,shlex,subprocess,tempfile,time
ROOT=Path(__file__).resolve().parent.parent

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def guest(path):return '/Volumes/SystemRoot/workspace/'+str(path.resolve().relative_to(ROOT))

def prepare(args):
    build_path=ROOT/args.build;build=json.loads(build_path.read_text());library=ROOT/build['library'];assert sha(library)==build['library_sha256'];assert build['new_export_names']==['_macho_source_version'] and not build['module_initializers']
    folder=Path(tempfile.mkdtemp(prefix='macho-source-version-probe-',dir=ROOT/'runtime'));config=json.loads((ROOT/args.configuration).read_text());parent_path=ROOT/config['resource_overlay_stage'];parent=json.loads(parent_path.read_text());assert sha(parent_path)==config['resource_overlay_stage_sha256']
    overlay={**parent,'libraries':str(library.parent.relative_to(ROOT)),'extra_library_paths':[parent['libraries'],*parent.get('extra_library_paths',[])],'parent_overlay':str(parent_path.relative_to(ROOT)),'parent_overlay_sha256':sha(parent_path),'files':dict(parent['files']),'runtime_execution_verified':False,'source_version_component_build':args.build}
    for path in [build_path,library,*[ROOT/name for name in build['files']]]:overlay['files'][str(path.relative_to(ROOT))]=sha(path)
    overlay_path=folder/'provider-stage.json';overlay_path.write_text(json.dumps(overlay,indent=2)+'\n');config['resource_overlay_stage']=str(overlay_path.relative_to(ROOT));config['resource_overlay_stage_sha256']=sha(overlay_path)
    program=folder/'probe';config['executables']=list(dict.fromkeys([*config['executables'],guest(program)]));configuration=folder/'resource-configuration.json';configuration.write_text(json.dumps(config,indent=2)+'\n')
    sdk=ROOT/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source=ROOT/'fixtures/hello/macho-source-version.c';obj=folder/'probe.o'
    commands=[['clang-19','-target','x86_64-apple-macos15.4','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','15.4','15.4','-syslibroot',str(sdk),'-L',str(library.parent),'-lDarlingCacheIntrospection','-lSystem','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]
    for command in commands:subprocess.run(command,check=True)
    module=runpy.run_path(str(ROOT/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=args.stage,configuration=str(configuration.relative_to(ROOT)))
    original_unity=ROOT/'runtime/unity-macos-editor-6000.3.27f1-v1/Unity/Unity.app/Contents/MacOS/Unity'
    script=folder/'probe-guest.sh';script.write_text('#!/bin/bash\nulimit -c 0\n'+shlex.join([guest(program),guest(library),guest(original_unity)])+'\nstatus=$?\nprintf "MACHO_SOURCE_VERSION_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command=profile['command'][:-2]+['/usr/bin/env','-u','DISPLAY','-u','WAYLAND_DISPLAY','-u','XAUTHORITY','/bin/bash',guest(script)];command[3]='120'
    record=dict(stage=args.stage,configuration=str(configuration.relative_to(ROOT)),build=args.build,library=str(library.relative_to(ROOT)),command=command,source_runtime=profile['source_runtime'],checks_expected=20,source_fixture=str(source.relative_to(ROOT)),native_execution=False,files={str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__),source,program,script,configuration,overlay_path,build_path,library,original_unity]})
    (folder/'prepared.json').write_text(json.dumps(record,indent=2)+'\n');runner=folder/'run-native.sh';runner.write_text('#!/bin/bash\nset -euo pipefail\nexec '+shlex.join(['python3',str(Path(__file__).resolve()),'--run-prepared',str(folder/'prepared.json')])+'\n');runner.chmod(0o755);print(folder/'prepared.json');print(configuration)

def run(args):
    path=args.run_prepared.resolve(strict=True);record=json.loads(path.read_text());folder=path.parent;target=folder/'result.json';assert not target.exists()
    for name,digest in record['files'].items():assert sha(ROOT/name)==digest,name
    module=runpy.run_path(str(ROOT/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=record['stage'],configuration=record['configuration']);assert profile['source_runtime']==record['source_runtime'];env=module['environment'](profile)
    for name in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY'):env.pop(name,None)
    log=folder/'private-native.log';start=time.monotonic()
    with log.open('w') as stream:process=subprocess.run(record['command'],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
    text=log.read_text(errors='replace');status=re.findall(r'^MACHO_SOURCE_VERSION_NATIVE_STATUS (\d+)$',text,re.M);checks=re.findall(r'^APPLE_DYLD_SOURCE_VERSION_ACTUAL_(\d+)_CHECKS_OK$',text,re.M);verified=process.returncode==0 and status==['0'] and checks==[str(record['checks_expected'])]
    result=dict(verified=verified,outer_status=process.returncode,native_status=status,checks=checks,elapsed_seconds=time.monotonic()-start,prepared=str(path.relative_to(ROOT)),private_log=str(log.relative_to(ROOT)),private_log_sha256=sha(log),raw_log_publishable=False,source_version_real_load_command_cases_verified=verified,macos_Unity_Editor_verified=False)
    target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('verified','outer_status','native_status','checks')},indent=2));print(target);raise SystemExit(0 if verified else 1)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build');p.add_argument('--configuration');p.add_argument('--stage',default='artifacts/private-procfs-auditsession108-stage.json');p.add_argument('--run-prepared',type=Path);a=p.parse_args()
    if a.run_prepared:run(a)
    else:assert a.build and a.configuration;prepare(a)

if __name__=='__main__':main()
