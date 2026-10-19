#!/usr/bin/env python3
"""Record independently checked private xcrun, libdyld and actual App build evidence."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,runpy,shutil
r=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
for name in ['dispatch-stage','scope-probe','libdyld-probe','build-report','product-report']:parser.add_argument('--'+name,required=True)
a=parser.parse_args();sha=lambda name:hashlib.sha256((r/name).read_bytes()).hexdigest();read=lambda name:json.loads((r/name).read_text())
module=runpy.run_path(str(r/'scripts/resource-tool-dispatch-profile.py'));p=module['profile'](diagnostic=True,dispatch_stage=a.dispatch_stage)
scope=read(a.scope_probe);life=read(a.libdyld_probe);build=read(a.build_report);product=read(a.product_report)
assert scope['dispatch_stage']==life['dispatch_stage']==a.dispatch_stage
assert scope['dispatch_stage_sha256']==life['dispatch_stage_sha256']==sha(a.dispatch_stage)
assert scope['source_runtime']==life['source_runtime']==build['source_runtime']==p['source_runtime']
assert scope['scope_smoke_verified'] and life['all_verified']
assert not scope['resource_tools_verified'] and not scope['full_resource_compilation_verified']
assert len(scope['cases'])==5 and [c['case'] for c in scope['cases']]==['scope','parent-version','xcrun-clang','actool','ibtool']
blockers=set()
for i,c in enumerate(scope['cases']):
 assert sha(c['log'])==c['log_sha256'] and sha(c['script'])==c['script_sha256']
 text=(r/c['log']).read_text()
 if i<3:
  assert c['verified'] and c['exit_status']==0
  markers=['RESOURCE_SCOPE_RUBY_OPENSSL_OK','RESOURCE_SCOPE_QUERY_STATUS 0'] if i==0 else ['RESOURCE_SCOPE_TOOL_STATUS 0']
  assert all(re.search('^'+re.escape(marker)+'$',text,re.M) for marker in markers)
 else:
  assert not c['verified'] and c['exit_status']!=0
  match=re.search(r'Library not loaded: (.+)',text);assert match;blockers.add(match[1])
assert len(life['cases'])==4
for c in life['cases']:
 assert c['verified'] and c['exit_status']==0 and sha(c['log'])==c['log_sha256']
 for name,digest in c['executed_files'].items():assert sha(name)==digest
 suffix=r' [1-9][0-9]*' if c['name']=='snapshot' else ''
 assert all(re.search('^'+re.escape(marker)+suffix+'$',(r/c['log']).read_text(),re.M) for marker in c['expected_markers'])
assert build['exit_status']==0 and build['native_xcode_status']==['0'] and build['prebuild_command_verified'] and build['UTI_preflight_verified']
assert build['gui_environment_removed']==scope.get('gui_environment_removed',life['gui_environment_removed'])==['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']
assert sha(build['log'])==build['log_sha256'] and sha(build['script'])==build['script_sha256']
text=(r/build['log']).read_text()
for marker in ['** BUILD SUCCEEDED **','SERVICE_RUNTIME_XCODE_STATUS 0','SCOPED_RUBY_OPENSSL_OK','SERVICE_RUNTIME_PREBUILD_COMMAND_OK','SERVICE_RUNTIME_UTI_PREFLIGHT_OK']:assert re.search('^'+re.escape(marker)+'$',text,re.M),marker
for marker in ['CompileC ','/LocalMath.c','Libtool ','Ld ','/main.m']:assert marker in text,marker
assert product['verified'] and product['architecture']=='arm64' and product['platform']=='iPhoneOS'
assert product['real_Pod_symbol_linked']=='_local_add' and not product['signing_verified'] and not product['engine_generated_project']
for name,digest in product['files'].items():assert sha(name)==digest
xcode='runtime/state/prefix/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild';assert sha(xcode)==build['original_xcodebuild_sha256']=='d6ceec0a4fa47e3f7a20c712d960ffb954b2246a2c94a0bf0818b2e8344065c5'
server='runtime/darlingserver-source-build/darlingserver/darlingserver';assert sha(server)=='ae78babd377dd542788f321752b11e9dea6413ee49d1009f00df825fdd9efd6b'
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),verified=True,goal_complete=False,private_source_runtime=p['source_runtime'],stage=a.dispatch_stage,resource_images=len(p['source_ios_resource_frameworks']['components']),scope_and_original_xcrun_compiler_verified=True,libdyld_version_and_real_lifecycle_snapshot_TLV_verified=True,fresh_CocoaPods_iOS_App_build_verified=True,product=product,gui_environment_removed=build['gui_environment_removed'],guest_minimum_os=life['expected_minimum_os'],libdyld_SDK_version=life['SDK_version'],original_xcrun_modified=False,original_xcodebuild_sha256=sha(xcode),default_server_sha256=sha(server),default_runtime_changed=False,resource_invocation_observed_blockers=sorted(blockers),full_resource_compilation_verified=False,signing_verified=False,Unity_UE_project_verified=False,full_macOS_API_compatibility_verified=False,evidence={name:sha(name) for name in [a.dispatch_stage,a.scope_probe,a.libdyld_probe,a.build_report,a.product_report]},recorder_sha256=sha(str(Path(__file__).relative_to(r))))
output=r/'artifacts/resource-tool-dispatch-progress.json'
if output.exists():
 old=output.read_bytes();digest=hashlib.sha256(old).hexdigest();dest=r/'artifacts/resource-tool-dispatch-progress-history'/digest;dest.mkdir(parents=True,exist_ok=True);(dest/output.name).write_bytes(old)
output.write_text(json.dumps(record,indent=2)+'\n');print('PRIVATE_RESOURCE_DISPATCH_FRESH_IOS_BUILD_EVIDENCE_VERIFIED')
