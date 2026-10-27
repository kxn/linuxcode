#!/usr/bin/env python3
"""Run an explicit raw fsevents fixture against selected real Linux sources."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',required=True);p.add_argument('--device-source',default='vendor/darlingserver/src/fsevents-device.cpp');p.add_argument('--expect-internal-loss',action='store_true');a=p.parse_args();f=Path(tempfile.mkdtemp(prefix='fsevents-device-host-',dir=r/'runtime'))
journal='vendor/darlingserver/src/fsevents-journal.cpp';header='vendor/darlingserver/internal-include/darlingserver/fsevents-device.hpp';cmd=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-error=misleading-indentation','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(r/'vendor/darlingserver/internal-include'),a.fixture,a.device_source,journal,'-o',str(f/'probe')]
with (f/'compile.log').open('w') as out:subprocess.run(cmd,cwd=r,check=True,stdout=out,stderr=subprocess.STDOUT)
run=[str(f/'probe')]+(['--expect-internal-loss'] if a.expect_internal_loss else [])
with (f/'run.log').open('w') as out:res=subprocess.run(run,cwd=r,stdout=out,stderr=subprocess.STDOUT,timeout=40)
text=(f/'run.log').read_text();marker='OLD_INTERNAL_JOURNAL_WRITES_TRIGGER_RAW_EVENTS_DROPPED' if a.expect_internal_loss else ('FSEVENTS_DEVICE_REAL_LINUX_OK' if a.fixture.endswith('/fsevents-device-linux.cpp') else 'INTERNAL_JOURNAL_NO_RAW_SELF_NOTIFICATIONS_REAL_RENAME_DELETE_AND_USER_NAMES_OK');ok=res.returncode==0 and marker in text
sha=lambda n:hashlib.sha256(n.read_bytes()).hexdigest();record=dict(verified=ok,expected_internal_loss=a.expect_internal_loss,outer_status=res.returncode,asan_ubsan=True,command=cmd,log=str((f/'run.log').relative_to(r)),log_sha256=sha(f/'run.log'),files={str(n):sha(r/n) for n in [a.fixture,a.device_source,journal,header,str(Path(__file__).relative_to(r))]},native_Darling_integration_verified=False,full_goal_complete=False)
(f/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-2000:]);print('EVIDENCE',f/'result.json');raise SystemExit(0 if ok else 1)
