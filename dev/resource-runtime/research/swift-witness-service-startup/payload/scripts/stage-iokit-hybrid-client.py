#!/usr/bin/env python3
"""Stage source registry clients in a new resource overlay without changing defaults."""
from pathlib import Path
import argparse,hashlib,json,runpy,shutil,subprocess
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for n in ['configuration','build','tag','version']:p.add_argument('--'+n,required=True)
a=p.parse_args();assert a.tag.isalnum() and a.version.isdigit();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();cfg=json.loads((r/a.configuration).read_text());parent=r/cfg['resource_overlay_stage'];d=json.loads(parent.read_text());b=json.loads((r/a.build).read_text());assert b['verified_code_preservation'];resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
for n,h in d['files'].items():resolve(n,h)
for n in ['framework','extra_library','legacy_client']:assert sha(r/b[n])==b[n+'_sha256']
base=(r/d['frameworks']).parent;out=r/('runtime/resource-framework-overlay-'+a.tag);report=r/('artifacts/resource-framework-overlay-'+a.tag+'-stage.json');configuration=r/('config/direct-resource-tool-environment-v'+a.version+'.json');assert all(not q.exists() for q in [out,report,configuration]);subprocess.run(['cp','-a','--reflink=auto',str(base),str(out)],check=True)
relative=Path('frameworks/IOKit.framework/Versions/A/IOKit');old=sha(out/relative);shutil.copy2(r/b['framework'],out/relative);shutil.copy2(r/b['extra_library'],out/'libraries'/Path(b['extra_library']).name)
for key in ['frameworks','libraries']:d[key]=str((out/key).relative_to(r))
for key in ['extra_framework_paths','extra_library_paths']:d[key]=[str((out/(r/v).relative_to(base)).relative_to(r)) for v in d.get(key,[])]
for q in out.rglob('*'):
 n=str(q.relative_to(r))
 if q.is_symlink():d['links'][n]=str(q.readlink())
 elif q.is_file():d['files'][n]=sha(q)
for q in [Path(__file__),parent,r/a.build,r/a.configuration]:d['files'][str(q.relative_to(r))]=sha(q)
d.update(parent_overlay=str(parent.relative_to(r)),parent_overlay_sha256=sha(parent),iokit_hybrid_client=dict(build=a.build,previous_sha256=old,current_sha256=sha(out/relative)),runtime_execution_verified=False,full_goal_complete=False);report.write_text(json.dumps(d,indent=2)+'\n');cfg.update(resource_overlay_stage=str(report.relative_to(r)),resource_overlay_stage_sha256=sha(report));configuration.write_text(json.dumps(cfg,indent=2)+'\n');print(configuration.relative_to(r))
