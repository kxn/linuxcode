from pathlib import Path
import json,hashlib,struct,plistlib,subprocess
r=Path('/home/dl/linuxcode');base=r/'runtime/unity-ios-cocoapods-v76-build/DerivedData/Build/Products/Debug-iphoneos';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
images={}
for p in [base/'uEmuera.app/uEmuera',base/'UnityFramework.framework/UnityFramework']:
 b=p.read_bytes();h=struct.unpack_from('<8I',b);assert h[0]==0xfeedfacf and h[1]==0x100000c;off=32;platform=None;loads=[];signature=False
 for i in range(h[4]):
  cmd,n=struct.unpack_from('<II',b,off);assert n>=8 and off+n<=len(b)
  if cmd==0x32:platform=struct.unpack_from('<III',b,off+8)
  if cmd in [0xc,0x80000018,0x8000001f]:
   start=off+struct.unpack_from('<I',b,off+8)[0];loads.append(b[start:b.index(b'\0',start)].decode())
  if cmd==0x1d:signature=True
  off+=n
 assert platform and platform[0]==2 and h[3]==(2 if p.name=='uEmuera' else 6)
 images[str(p.relative_to(r))]=dict(size=len(b),sha256=sha(p),architecture='arm64',MachO_file_type=h[3],build_version=platform,loaded_libraries=loads,LC_CODE_SIGNATURE_present=signature)
main=base/'uEmuera.app/uEmuera';assert b'Frameworks/UnityFramework.framework' in main.read_bytes()
nibs={};infos={}
for p in (base/'uEmuera.app').rglob('*'):
 if not p.is_file():continue
 if p.suffix=='.nib':
  b=p.read_bytes();assert b[:10]==b'NIBArchive';v=struct.unpack_from('<10I',b,10);assert all(50<=v[i]<=len(b) for i in [3,5,7,9]);nibs[str(p.relative_to(r))]=dict(size=len(b),sha256=sha(p),header=v)
 if p.name=='Info.plist' and '.storyboardc' in str(p):infos[str(p.relative_to(r))]=plistlib.loads(p.read_bytes())
assert len(nibs)==4 and len(infos)==2
archives={str(p.relative_to(r)):dict(size=p.stat().st_size,sha256=sha(p),archive_members=len(subprocess.check_output(['llvm-ar-19','t',str(p)],text=True).splitlines())) for p in [base/'AFNetworking/libAFNetworking.a',base/'libPods-UnityFramework.a',base/'libGameAssembly.a']}
record=dict(verified_linked_unity_arm64_executable_and_framework=True,full_build_report='artifacts/xcode-service-runtime-tool-dispatch-diagnostic-build-f4e33657f175.json',original_xcode_status=65,full_App_build_verified=False,application_signing_step_completed=False,original_Storyboard_compile_and_link_completed=True,independent_NIB_headers_verified=True,full_visual_layout_semantics_verified=False,MachO_images=images,main_loads_UnityFramework_via_NSBundle=True,main_source=dict(path='runtime/unity-ios-cocoapods-ios26-v1/ios/MainApp/main.mm',sha256=sha(r/'runtime/unity-ios-cocoapods-ios26-v1/ios/MainApp/main.mm')),CocoaPods_and_engine_archives=archives,compiled_NIBs=nibs,storyboard_entry_plists=infos,next_blocker='Original actool CompileAssetCatalogVariant thinned nonzero; no completed Assets.car. Focused original task reproduction active.',no_private_binaries_published=True)
(r/'artifacts/unity-original-storyboards-linked-app-v1.json').write_text(json.dumps(record,indent=2)+'\n');print('LINKED_UNITY_ARM64_AND_FOUR_STORYBOARD_NIBS_VERIFIED')
