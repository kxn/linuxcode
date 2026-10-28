#!/usr/bin/env python3
"""Test production local-membership and identifier modules against real Linux NSS.

Only an isolated usernamespace/chroot gets generated passwd/group fixtures.
No Darling runtime, host account mutation, mocked NSS or authorization bypass.
"""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
w=Path(tempfile.mkdtemp(prefix='local-membership-host-',dir=r/'runtime'))
s=r/'runtime/opendirectory-membership-complete-source-v1/opendirectoryd/src'
inc=w/'include/os';inc.mkdir(parents=True);(inc/'availability.h').write_text('/* Host-only annotation; production uses Darwin SDK. */\n#define API_DEPRECATED(...)\n')
source=r/'fixtures/hello/local-membership-check-smoke.c'
command=['gcc','-std=gnu11','-D_GNU_SOURCE','-O1','-g','-I'+str(s),'-I'+str(w/'include'),'-I'+str(r/'vendor/darling/src/external/Libinfo/membership.subproj'),str(source),str(s/'local-membership-check.c'),str(s/'identifier-translation.c'),'-o',str(w/'probe')]
with (w/'compile.log').open('w') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
p=subprocess.run([str(w/'probe')],capture_output=True,text=True,timeout=15);(w/'live.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stdout+p.stderr
root=w/'root';(root/'etc').mkdir(parents=True);(root/'.local-membership-fixture-root').write_text('owned-host-NSS-fixture-only\n')
(root/'etc/passwd').write_text('root:x:0:0:root:/:/bin/false\nalice:x:1001:1000:Alice:/:/bin/false\nbob:x:1002:1002:Bob:/:/bin/false\n')
(root/'etc/group').write_text('root:x:0:\nprimary:x:1000:\nbob:x:1002:\nsupplementary:x:2000:alice\nnonmember:x:2001:\n'+''.join(f'many{i}:x:{3000+i}:alice\n' for i in range(40)))
(root/'etc/nsswitch.conf').write_text('passwd: files\ngroup: files\n');shutil.copy2(w/'probe',root/'probe')
ldd=subprocess.check_output(['ldd',str(w/'probe')],text=True)
for name in re.findall(r'(/[^\s()]+)',ldd):
 p=Path(name)
 if p.is_file():target=root/name.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
run=['unshare','--user','--map-root-user','/usr/sbin/chroot',str(root),'/probe','--private-records']
p=subprocess.run(run,capture_output=True,text=True,timeout=15);(w/'private.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stdout+p.stderr
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(verified=True,host_only=True,native_Darling_executed=False,mocked_NSS=False,host_accounts_unchanged=True,actual_host_primary_and_supplementary_verified=True,real_private_files_NSS=True,private_fixture_requires_chroot_marker=True,more_than_16_supplementary_groups=True,unknown_numeric_UUID_not_a_membership_grant=True,nonexistent_group_success_false=True,unknown_user_ENOENT=True,opaque_UUIDs_fail_closed=True,unsupported_SID_NFS_ENOTSUP=True,malformed_inputs_EINVAL=True,known_user_equal_UUID_and_everyone_verified=True,service_absence_ENOENT=True,SACL_all_services_priority_verified=True,fresh_records_checked_without_cache=True,commands=[command,run],outputs=dict(live=(w/'live.log').read_text(),private=(w/'private.log').read_text()),source_files={str(p.relative_to(r)):sha(p) for p in [Path(__file__),source,s/'local-membership-check.c',s/'local-membership-check.h',s/'identifier-translation.c',s/'identifier-translation.h',r/'vendor/darling/src/external/Libinfo/membership.subproj/membership.h',r/'vendor/darling/src/external/Libinfo/membership.subproj/mbr_check_membership.3']})
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(w/'result.json');print(record['outputs']['live']+record['outputs']['private'])
