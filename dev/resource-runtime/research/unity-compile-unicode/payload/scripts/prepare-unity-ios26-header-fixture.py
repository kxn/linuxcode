#!/usr/bin/env python3
"""Copy the owned Unity sample and remove two redundant private SDK imports.

This is sample-source compatibility work, not a Darling/compiler workaround.
The original sample, Xcode project files and CocoaPods configuration stay intact.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
root=Path(__file__).resolve().parent.parent;source=root/'runtime/unity-ios-cocoapods-v1/ios';folder=root/'runtime/unity-ios-cocoapods-ios26-v1';destination=folder/'ios';report=root/'artifacts/unity-ios26-header-fixture-v1.json'
assert source.is_dir() and not folder.exists() and not report.exists();folder.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
subprocess.run(['cp','-a','--reflink=auto',str(source),str(destination)],cwd=root,check=True)
names=['Dependencies/AFNetworking/AFNetworking/AFNetworkReachabilityManager.m','Dependencies/AFNetworking/AFNetworking/AFHTTPSessionManager.m']
subprocess.run(['python3','scripts/archive-source-inputs.py',*[str((destination/n).relative_to(root)) for n in names]],cwd=root,check=True)
patches=[]
for name in names:
 original=source/name;target=destination/name;before=original.read_bytes();assert target.read_bytes()==before and before.count(b'#import <netinet6/in6.h>\n')==1 and b'#import <netinet/in.h>\n' in before
 after=before.replace(b'#import <netinet6/in6.h>\n',b'');pending=target.with_suffix('.m.pending');assert not pending.exists();pending.write_bytes(after);pending.chmod(target.stat().st_mode);os.replace(pending,target);assert original.read_bytes()==before
 patches.append(dict(path=name,before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=sha(target),removed_line='#import <netinet6/in6.h>',lines_removed=1))
same=0;projects={};links={}
for original in source.rglob('*'):
 rel=str(original.relative_to(source));target=destination/rel
 if original.is_symlink():assert target.is_symlink() and os.readlink(target)==os.readlink(original);links[rel]=os.readlink(original)
 elif original.is_file() and rel not in names:
  digest=sha(original);assert sha(target)==digest; same+=1
  if any(part.endswith(('.xcodeproj','.xcworkspace')) for part in original.relative_to(source).parts) or original.name in ['Podfile','Podfile.lock','Manifest.lock']:projects[rel]=digest
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS26.5.sdk/usr/include';modulemap=sdk/'netinet.modulemap';public=sdk/'netinet/in.h'
assert 'private textual header "netinet6/in6.h"' in modulemap.read_text() and '#include <netinet6/in6.h>' in public.read_text()
record=dict(verified=True,fixture_only_SDK_compatibility_patch=True,Darling_runtime_fix=False,original_sample=str(source.relative_to(root)),sample=str(destination.relative_to(root)),workspace=str((destination/'Unity-iPhone.xcworkspace').relative_to(root)),patches=patches,other_regular_files_byte_equal=same,original_Xcode_and_CocoaPods_files=projects,symlinks_preserved=links,original_sample_modified=False,project_files_modified=False,compiler_diagnostics_suppressed=False,SDK_modulemap_sha256=sha(modulemap),SDK_public_header_sha256=sha(public),full_build_verified=False,full_goal_complete=False)
report.write_text(json.dumps(record,indent=2)+'\n');print(report.relative_to(root));print('Unchanged other files',same,'project/CocoaPods files',len(projects))
