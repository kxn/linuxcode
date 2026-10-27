#!/usr/bin/env python3
"""Run the actual native Linux Unity Editor export; never infer success from preparation."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared-run',required=True);p.add_argument('--editor');a=p.parse_args()
folder=(r/a.prepared_run).resolve();assert folder.is_relative_to(r/'runtime');prepared=json.loads((folder/'prepared.json').read_text());command=list(prepared['command'])
if a.editor:command[0]=str(Path(a.editor).expanduser().resolve())
editor=Path(command[0]);assert editor.is_file() and editor.open('rb').read(4)==b'\x7fELF','A native Linux Unity Editor is required'
for name,digest in prepared['source_files'].items():assert hashlib.sha256((r/name).read_bytes()).hexdigest()==digest
attempt=Path(tempfile.mkdtemp(prefix='attempt-',dir=folder));log=attempt/'Unity-export.log';command[command.index('-logFile')+1]=str(log)
env=os.environ.copy();env.update(prepared['environment'])
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
print('RUNNING',attempt.relative_to(r),flush=True)
with (attempt/'stdout.log').open('w') as out:
 try:result=subprocess.run(command,cwd=folder/'project',env=env,stdout=out,stderr=subprocess.STDOUT,timeout=1800);status=result.returncode
 except subprocess.TimeoutExpired:status=124
text=log.read_text(errors='replace') if log.exists() else '';output=r/prepared['export'];pbx=output/'Unity-iPhone.xcodeproj/project.pbxproj';podfile=output/'Podfile';success=status==0 and 'LINUXCODE_UNITY_IOS_EXPORT_SUCCEEDED' in text and pbx.is_file() and podfile.is_file()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();record=dict(verified=success,native_Linux_Editor=True,mac_used=False,headless=True,editor_version=prepared['editor_version'],command=command,outer_status=status,prepared_run=a.prepared_run,prepared_sha256=sha(folder/'prepared.json'),editor_sha256=sha(editor),export=prepared['export'],log=str(log.relative_to(r)),log_sha256=sha(log) if log.exists() else None,stdout_log=str((attempt/'stdout.log').relative_to(r)),generated_project_sha256=sha(pbx) if pbx.exists() else None,generated_cpp_files=sum(1 for _ in output.rglob('*.cpp')) if output.exists() else 0,CocoaPods_verified=False,original_xcodebuild_verified=False)
(attempt/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-2200:]);print('EVIDENCE',attempt/'result.json');raise SystemExit(0 if success else 1)
