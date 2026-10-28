from pathlib import Path
import argparse,hashlib,json,os,re,runpy,subprocess,time
root=Path(__file__).resolve().parents[2];folder=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();p=argparse.ArgumentParser();p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--prepare-only',action='store_true');a=p.parse_args();prepared=folder/'prepared.json';inputs=json.loads(prepared.read_text())
for name,digest in inputs['files'].items():assert sha(root/name)==digest,name
assert not (folder/'result.json').exists() and not (folder/'native.log').exists()
config=root/a.configuration;stage=root/a.stage;assert json.loads(config.read_text())['runtime_mode']=='unified'
module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration=a.configuration);command=profile['command'][:-2]+['/bin/bash','/Volumes/SystemRoot/workspace/'+inputs['guest_script']];assert command[0]=='timeout';command[2:4]=[str(inputs['kill_grace_seconds']),str(inputs['run_timeout_seconds'])]
environment=module['environment'](profile);controls={}
for suffix in ['UNWINDING','APIS','DWARF']:
 key='LINUXCODE_RUN_LIBUNWIND_PRINT_'+suffix;environment.setdefault(key,'0');controls[key]=environment[key]
plan=dict(configuration=a.configuration,configuration_sha256=sha(config),stage=a.stage,stage_sha256=sha(stage),command=command,prepared=str(prepared.relative_to(root)),prepared_sha256=sha(prepared),whole_run_unwind_log_inputs=controls,run_timeout_seconds=inputs['run_timeout_seconds'],kill_grace_seconds=inputs['kill_grace_seconds'],native_execution=False)
(folder/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
if a.prepare_only:print(folder/'plan.json');raise SystemExit(0)
start=time.monotonic();log=folder/'native.log'
with log.open('w') as stream:r=subprocess.run(command,cwd=root,env=environment,stdout=stream,stderr=subprocess.STDOUT)
text=log.read_text(errors='replace');statuses=re.findall(r'^SVC_UNWIND_GATE_PHASE_STATUS (\S+) (\d+)$',text,re.M);expected=[(phase['name'],'0') for phase in inputs['phases']];markers={phase['name']:all(marker in text for marker in phase['expected']) for phase in inputs['phases']};verified=r.returncode==0 and statuses==expected and all(markers.values()) and 'SVC_UNWIND_GATE_COMPLETE phases=5' in text
result={**plan,'native_execution':True,'verified':verified,'outer_status':r.returncode,'elapsed_seconds':time.monotonic()-start,'phase_statuses':statuses,'phase_markers':markers,'private_log':str(log.relative_to(root)),'private_log_sha256':sha(log),'raw_log_publishable':False,'other_process_memory_accessed':False,'service_builder_repeated':False,'source_or_library_configuration_modified':False};(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['verified','outer_status','elapsed_seconds','phase_statuses','phase_markers']},indent=2));raise SystemExit(0 if verified else 1)
