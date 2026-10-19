#!/usr/bin/env python3
"""Observe real Ruby/SDK-query, parent Xcode, xcrun compiler and resource invocations."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,runpy,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
names=['scope','parent-version','xcrun-clang','actool','ibtool']
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dispatch-stage',default='artifacts/resource-tool-dispatch-sharing-v2-stage.json')
parser.add_argument('--case',action='append',choices=names)
parser.add_argument('--baseline',action='store_true');parser.add_argument('--diagnostic',action='store_true');args=parser.parse_args()
module=runpy.run_path(str(root/('scripts/xcode-tool-dispatch-runtime-profile.py' if args.baseline else 'scripts/resource-tool-dispatch-profile.py')))
p=module['profile'](diagnostic=args.diagnostic,**({} if args.baseline else {'dispatch_stage':args.dispatch_stage}))
folder=Path(tempfile.mkdtemp(prefix='resource-tool-dispatch-probe-',dir=root/'runtime'));guest='/Volumes/SystemRoot/workspace/'+str(folder.relative_to(root))+'/'
scripts={'scope':'''#!/bin/bash
ulimit -c 0
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY
set -e
cd /Volumes/SystemRoot/workspace/fixtures/iOSCocoaPodsSmoke
/usr/bin/ruby -e '$stdout.sync=true; puts "RESOURCE_SCOPE_RUBY_CORE_OK"; require "openssl"; puts "RESOURCE_SCOPE_RUBY_OPENSSL_LOADED"; OpenSSL::SSL::SSLContext.new; puts "RESOURCE_SCOPE_RUBY_OPENSSL_OK"'
compiler=$(/usr/bin/xcrun --sdk iphoneos --find clang)
test "$compiler" = /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang
printf 'RESOURCE_SCOPE_ORIGINAL_CLANG_FOUND %s\n' "$compiler"
printf 'RESOURCE_SCOPE_QUERY_STATUS 0\n'
'''}
programs={'parent-version':'/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild -version','xcrun-clang':'/usr/bin/xcrun --sdk iphoneos clang --version','actool':'/usr/bin/xcrun --sdk iphoneos actool --version','ibtool':'/usr/bin/xcrun --sdk iphoneos ibtool --version'}
for name,command in programs.items():scripts[name]='#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+command+'\nstatus=$?\nprintf "RESOURCE_SCOPE_TOOL_STATUS %s\\n" "$status"\nexit "$status"\n'
cases=[];env=module['environment'](p)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
resource_folder=None
if not args.baseline:resource_folder=p['source_ios_resource_frameworks']['folder']
for name in args.case or names:
 script=folder/(name+'.sh');script.write_text(scripts[name]);tail=['/bin/bash',guest+script.name]
 if name!='parent-version':tail=['/usr/bin/env','-u','DYLD_LIBRARY_PATH','-u','DYLD_FRAMEWORK_PATH',*tail]
 command=p['command'][:-2]+tail;command[3]='120';log=folder/(name+'.log')
 with log.open('w') as stream:r=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
 text=log.read_text();case=dict(case=name,command=command,exit_status=r.returncode,log=str(log.relative_to(root)),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),script=str(script.relative_to(root)),script_sha256=hashlib.sha256(script.read_bytes()).hexdigest())
 if name=='scope':
  markers=['RESOURCE_SCOPE_RUBY_CORE_OK','RESOURCE_SCOPE_RUBY_OPENSSL_LOADED','RESOURCE_SCOPE_RUBY_OPENSSL_OK','RESOURCE_SCOPE_QUERY_STATUS 0']
  case['verified']=r.returncode==0 and all(re.search('^'+re.escape(marker)+'$',text,re.M) for marker in markers) and bool(re.search('^RESOURCE_SCOPE_ORIGINAL_CLANG_FOUND /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang$',text,re.M))
 else:
  statuses=re.findall('^RESOURCE_SCOPE_TOOL_STATUS ([0-9]+)$',text,re.M);case['native_status']=statuses;case['verified']=r.returncode==0 and statuses==['0']
 if name in ['actool','ibtool']:case['resource_path_restoration_observed']=bool(resource_folder and '/Volumes/SystemRoot/workspace/'+resource_folder+'/frameworks/' in text)
 cases.append(case);print(name,r.returncode,text[-1400:],flush=True)
by_name={case['case']:case for case in cases}
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),baseline_selected=args.baseline,test_only_permissive_coreservices_policy=args.diagnostic,dispatch_stage=args.dispatch_stage,dispatch_stage_sha256=hashlib.sha256((root/args.dispatch_stage).read_bytes()).hexdigest(),cases=cases,scope_smoke_verified=all(name in by_name and by_name[name]['verified'] for name in ['scope','parent-version']),resource_tools_verified=all(name in by_name and by_name[name]['verified'] for name in ['actool','ibtool']),all_selected_cases_verified=all(case['verified'] for case in cases),full_resource_compilation_verified=False,caller_resource_environment=p.get('resource_environment_applied_to_caller',False),source_runtime=p['source_runtime'],source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',folder/'result.json',flush=True)
raise SystemExit(0 if record['all_selected_cases_verified'] else 1)
