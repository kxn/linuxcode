#!/usr/bin/env python3
"""Check the original Intel job/domain wrapper register ABI without executing it."""
from pathlib import Path
import argparse,hashlib,json,runpy,struct
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);a=p.parse_args();output=root/a.report;assert not output.exists()
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals=dict(REFERENCE_CACHE_PATH=root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',REFERENCE_LIBRARY_ROOT=root/'runtime/fullsystem-libraries'));image=ns['image']('/usr/lib/system/libxpc.dylib');entries={}
for name,expected in [('__launch_job_routine',10),('__xpc_domain_routine',3)]:
 address=image.exports[name][1];data=ns['read'](address,24)
 assert data[:8]==bytes.fromhex('4889d14889f289fe') and data[8]==0xbf
 assert data[13:20]==bytes.fromhex('4531c04531c9e9')
 subsystem=struct.unpack_from('<I',data,9)[0];assert subsystem==expected
 target=address+24+struct.unpack_from('<i',data,20)[0]
 entries[name]=dict(address=hex(address),subsystem=subsystem,common_target=hex(target),third_argument='reply output pointer',wrapper_bytes_sha256=hashlib.sha256(data).hexdigest())
assert entries['__launch_job_routine']['common_target']==entries['__xpc_domain_routine']['common_target']
name='__launch_job_routine_async';address=image.exports[name][1];data=ns['read'](address,17)
assert data[:8]==bytes.fromhex('89d14889f289febf') and data[12]==0xe9 and struct.unpack_from('<I',data,8)[0]==10
entries[name]=dict(address=hex(address),subsystem=10,third_argument='32-bit Mach reply port',wrapper_bytes_sha256=hashlib.sha256(data).hexdigest(),common_target=hex(address+17+struct.unpack_from('<i',data,13)[0]))
source=root/'runtime/fullsystem-libraries/usr/lib/system/libxpc.dylib';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();report=dict(verified=True,ABI_only=True,job_operations_validated=False,original_image=str(source.relative_to(root)),original_image_sha256=sha(source),wrappers=entries,sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/'scripts/dsc-image.py']},full_goal_complete=False);output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
