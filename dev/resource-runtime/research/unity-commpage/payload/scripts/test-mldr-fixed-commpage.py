#!/usr/bin/env python3
"""Force fixed-address collisions while testing production loader code."""
from pathlib import Path
import argparse,hashlib,json,resource,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);a=p.parse_args()
build=json.loads((root/a.build).read_text());folder=Path(tempfile.mkdtemp(prefix='mldr-fixed-commpage-test-',dir=root/'runtime'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs=[root/'vendor/darling/src/startup/mldr'/n for n in ['mldr.c','commpage.c','commpage.h']]
for src in inputs:assert sha(src)==build['files'][str(src.relative_to(root))]
common=build['commands'][0];common=common[:common.index('-c')]
fixture=root/'fixtures/hello/mldr-fixed-commpage.c';exe=folder/'test'
cmd=[*common,'-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-DMLDR_SOURCE_FILE="'+str(inputs[0])+'"','-DCOMMPAGE_SOURCE_FILE="'+str(inputs[1])+'"',str(fixture),'-lm','-o',str(exe)]
with (folder/'build.log').open('w') as out:subprocess.run(cmd,check=True,stdout=out,stderr=subprocess.STDOUT)
def nocore():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
baseline=root/'runtime/source-input-history/c8c2eab6bf0cfa54a63e6eedde750010466e707a6b236296f87913542e17df2a'
assert sha(baseline)==baseline.name
baseline_fixture=root/'fixtures/hello/mldr-commpage-baseline.c';baseline_exe=folder/'baseline'
baseline_cmd=[*common,'-DCOMMPAGE_BASELINE_FILE="'+str(baseline)+'"',str(baseline_fixture),'-lm','-o',str(baseline_exe)]
with (folder/'baseline-build.log').open('w') as out:subprocess.run(baseline_cmd,check=True,stdout=out,stderr=subprocess.STDOUT)
old=subprocess.run([str(baseline_exe)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,preexec_fn=nocore);(folder/'baseline.log').write_bytes(old.stdout)
print('BASELINE_OCCUPIED_ADDRESS_STATUS',old.returncode)
r=subprocess.run([str(exe)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,preexec_fn=nocore);(folder/'run.log').write_bytes(r.stdout)
verified=old.returncode==12 and r.returncode==0 and b'MLDR_COMMPAGE_OK' in r.stdout
report=dict(verified=verified,status=r.returncode,baseline_status=old.returncode,baseline_command=baseline_cmd,build=a.build,command=cmd,real_mmap_mremap_and_production_stack_switch=True,proc_maps_collision_metadata_supplied_by_fixture=True,native_Darling_execution_verified=False,files={str(x.relative_to(root)):sha(x) for x in [Path(__file__),fixture,baseline_fixture,baseline,*inputs,folder/'build.log',folder/'run.log',folder/'baseline-build.log',folder/'baseline.log']})
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout.decode());print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
