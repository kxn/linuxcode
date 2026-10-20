#!/usr/bin/env python3
"""Install the matched original SystemAppearance data bundle into the guest prefix."""
from pathlib import Path
import hashlib,json,os,plistlib,shutil,tempfile
root=Path(__file__).resolve().parent.parent
base=root/'runtime/recovery/macOS Base System'
source=base/'System/Library/CoreServices/SystemAppearance.bundle'
dest=root/'runtime/state/prefix/System/Library/CoreServices/SystemAppearance.bundle'
report=root/'artifacts/system-appearance-resources-v1-stage.json'
assert not dest.is_symlink()
version=plistlib.loads((base/'System/Library/CoreServices/SystemVersion.plist').read_bytes());assert version['ProductBuildVersion']=='25G83'
info=plistlib.loads((source/'Contents/Info.plist').read_bytes());assert info['CFBundleIdentifier']=='com.apple.systemappearance'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={}
for p in source.rglob('*'):
 assert not p.is_symlink(),p
 if p.is_file():files[str(p.relative_to(source))]=sha(p)
assert 'Contents/Resources/SystemAppearance.car' in files and len(files)==9
if dest.exists() or report.exists():
    assert dest.is_dir() and report.is_file()
    previous=json.loads(report.read_text())
    assert previous['files']==files and previous['source_OS_build']==version['ProductBuildVersion']
    actual={str(q.relative_to(dest)):sha(q) for q in dest.rglob('*') if q.is_file()}
    assert not any(q.is_symlink() for q in dest.rglob('*')) and actual==files
    print('Verified existing',report.relative_to(root));raise SystemExit(0)

pending=Path(tempfile.mkdtemp(prefix='.SystemAppearance-',dir=dest.parent))
try:
 shutil.copytree(source,pending,dirs_exist_ok=True)
 for name,digest in files.items():assert sha(pending/name)==digest
 os.rename(pending,dest)
except BaseException:
 shutil.rmtree(pending,ignore_errors=True);raise
record=dict(installed_in_owned_guest_prefix=True,host_system_modified=False,original_Apple_data=True,source=str(source.relative_to(root)),destination=str(dest.relative_to(root)),source_OS_build=version['ProductBuildVersion'],source_OS_version=version['ProductVersion'],bundle_identifier=info['CFBundleIdentifier'],files=files,total_bytes=sum((source/name).stat().st_size for name in files),runtime_execution_verified=False,full_goal_complete=False)
report.write_text(json.dumps(record,indent=2)+'\n');print(report.relative_to(root))
