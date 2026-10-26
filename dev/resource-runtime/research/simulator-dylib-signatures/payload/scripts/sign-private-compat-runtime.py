#!/usr/bin/env python3
"""Ad-hoc sign a private compatibility library with original Apple codesign.

Never overwrite the selected runtime input; check that all Mach-O section bytes
remain identical, then independently verify the newly generated signature.
"""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,runpy,shlex,shutil,struct,subprocess,tempfile,types
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
for n in ['stage','configuration','source']:p.add_argument('--'+n,required=True)
p.add_argument('--adopt-result',help='Finish independent checks of an already signed private output without repeating signing');a=p.parse_args();source=root/a.source;assert source.is_file() and source.resolve().is_relative_to(root/'runtime')
folder=(root/a.adopt_result).resolve() if a.adopt_result else Path(tempfile.mkdtemp(prefix='signed-compat-runtime-',dir=root/'runtime'));assert folder.is_relative_to(root/'runtime');target=folder/source.name
if not a.adopt_result:shutil.copy2(source,target)
else:assert target.is_file() and not (folder/'result.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before=sha(source)
def sections(path):
 b=path.read_bytes();slices=[(0x1000007,3,0,len(b))]
 if b[:4]==bytes.fromhex('cafebabe'):slices=[struct.unpack_from('>IIIII',b,8+20*i)[:4] for i in range(struct.unpack_from('>I',b,4)[0])]
 result={}
 for cpu,sub,base,length in slices:
  assert b[base:base+4]==bytes.fromhex('cffaedfe');at=base+32
  for i in range(struct.unpack_from('<I',b,base+16)[0]):
   command,size=struct.unpack_from('<II',b,at)
   if command==25:
    seg=struct.unpack_from('<II16sQQQQiiII',b,at)
    for j in range(seg[-2]):
     sec=struct.unpack_from('<16s16sQQIIIIIIII',b,at+72+80*j)
     if (sec[8]&255) not in [1,12,18]:
      name=(cpu,sub,sec[1].rstrip(b'\0').decode(),sec[0].rstrip(b'\0').decode());assert name not in result
      result[name]=dict(size=sec[3],sha256=hashlib.sha256(b[base+sec[4]:base+sec[4]+sec[3]]).hexdigest())
   at+=size
 return result
if not a.adopt_result:
    oldsections=sections(source);guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));script=folder/'run.sh'
    # Discard the stale signature load command in this derived build input. Reading
    # its CMS to preserve old metadata would ask the unavailable trust service to
    # evaluate the original timestamp. Preserve identifier/entitlements explicitly;
    # the new identity is local ad-hoc, with a newly generated requirement.
    b=bytearray(target.read_bytes());slices=[(0,len(b))]
    if b[:4]==bytes.fromhex('cafebabe'):slices=[struct.unpack_from('>IIIII',b,8+20*i)[2:4] for i in range(struct.unpack_from('>I',b,4)[0])]
    labels=[];entitlements=[];runtimeFlags=[]
    for base,length in slices:
     count,cmdsize=struct.unpack_from('<II',b,base+16);at=base+32;commands=[];found=False
     for i in range(count):
      kind,n=struct.unpack_from('<II',b,at);command=bytes(b[at:at+n])
      if kind==29:
       assert not found;found=True;start,n2=struct.unpack_from('<II',b,at+8);sig=base+start
       for j in range(struct.unpack_from('>I',b,sig+8)[0]):
        slot,off=struct.unpack_from('>II',b,sig+12+8*j);size=struct.unpack_from('>I',b,sig+off+4)[0]
        if slot==0:
         ident=struct.unpack_from('>I',b,sig+off+20)[0];end=b.index(0,sig+off+ident);labels.append(bytes(b[sig+off+ident:end]).decode());runtimeFlags.append(bool(struct.unpack_from('>I',b,sig+off+12)[0]&0x10000))
        if slot==5:entitlements.append(plistlib.loads(bytes(b[sig+off+8:sig+off+size])))
      else:commands.append(command)
      at+=n
     assert found;new=b''.join(commands);b[base+32:base+32+cmdsize]=new+bytes(cmdsize-len(new));struct.pack_into('<II',b,base+16,count-1,len(new))
    assert len(set(labels))==1 and len(set(runtimeFlags))==1
    assert not entitlements or all(e==entitlements[0] for e in entitlements)
    target.write_bytes(b);assert sections(target)==oldsections
    argv=['/usr/bin/codesign','--force','--sign','-','--timestamp=none','--digest-algorithm=sha256','--identifier',labels[0]]
    if runtimeFlags[0]:argv+=['--options','runtime']
    if entitlements:
     entitlement=folder/'entitlements.plist';entitlement.write_bytes(plistlib.dumps(entitlements[0]));argv+=['--entitlements',guest(entitlement)]
    argv.append(guest(target))
    script.write_text('#!/bin/bash\nset -e\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(argv)+'\n'+shlex.join(['/usr/bin/codesign','--verify','--strict','--verbose=2',guest(target)])+'\nprintf "PRIVATE_COMPAT_RUNTIME_SIGNED_AND_STRICT_VERIFIED_OK\\n"\n')
    m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile);cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
    for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
     i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
    cmd+=['/bin/bash',guest(script)];cmd[3]='150';log=folder/'run.log'
    with log.open('w') as out:r=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
else:
    oldsections=sections(source);script=folder/'run.sh';log=folder/'run.log';assert 'PRIVATE_COMPAT_RUNTIME_SIGNED_AND_STRICT_VERIFIED_OK' in log.read_text()
    argv=shlex.split(script.read_text().splitlines()[4]);cmd=[];r=types.SimpleNamespace(returncode=0)
independent=runpy.run_path(str(root/'scripts/verify-adhoc-macho-file.py'))['verify'](target) if r.returncode==0 else None
same=sections(target)==oldsections;verified=r.returncode==0 and same and independent and independent['verified'] and 'PRIVATE_COMPAT_RUNTIME_SIGNED_AND_STRICT_VERIFIED_OK' in log.read_text();assert sha(source)==before
report=dict(verified=bool(verified),source=a.source,source_sha256=before,output=str(target.relative_to(root)),output_sha256=sha(target),all_MachO_section_bytes_preserved=same,section_count=len(oldsections),section_hashes=[dict(cpu=k[0],subtype=k[1],segment=k[2],section=k[3],**v) for k,v in oldsections.items()],independent_signature_check=independent,outer_status=r.returncode,command=cmd,sign_arguments=argv,log=str(log.relative_to(root)),log_sha256=sha(log),files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),script,root/a.stage,root/a.configuration]},ad_hoc_only=True,Apple_platform_identity_claimed=False,original_input_modified=False,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(log.read_text()[-5000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
