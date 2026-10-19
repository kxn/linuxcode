#!/usr/bin/env python3
"""Validate pinned original SwiftUI KeyPath records and reject actual damaged data.

Structural checks only; this does not prove full SwiftUI runtime compatibility.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, runpy, struct, time
root=Path(__file__).resolve().parent.parent
for attempt in range(10):
    raw=(root/'config/ios-resource-image-pins.json').read_bytes()
    try: pins=json.loads(raw); break
    except json.JSONDecodeError:
        if attempt==9: raise
        time.sleep(0.05)
folder=root/'runtime/keypath-environment-tests';folder.mkdir(exist_ok=True)
sha=hashlib.sha256(raw).hexdigest();snapshot=folder/(sha+'.json');snapshot.write_bytes(raw)
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
 'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
 'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
module=runpy.run_path(str(root/'scripts/swift-keypath-environment-records.py'))
read=ns['read'];cases=[];rejections=[];checks=0
for target,expected_patterns,expected_environments in [('swiftui-resource-native',75,56),('swiftuicore-resource-native',27,20)]:
    pin=pins[target];source=root/'runtime/fullsystem-libraries'/pin['path'].lstrip('/')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==pin['sha256']
    obj=ns['image'](pin['path']);sections=[(segment,name,address,size) for name,segment,address,size,_ in obj.sections]
    patterns=[int(a,16) for a in pin['swift_keypath_patterns']]
    records=module['validate'](read,sections,patterns)
    bounds=module['validate_bounds'](read,records,pin.get('swift_keypath_environment_bounds',[]))
    assert len(records)==expected_patterns
    assert len({r['environment'] for r in records})==expected_environments
    checks+=2
    first=patterns[0];component=first+24
    def changed(start, payload):
        def reader(address,length):
            result=bytearray(read(address,length))
            for at in range(max(address,start),min(address+length,start+len(payload))):
                result[at-address]=payload[at-start]
            return bytes(result)
        return reader
    failures=[
      ('root_tag_removed',first+8,struct.pack('<i',struct.unpack('<i',read(first+8,4))[0]+1),'mangled type'),
      ('environment_pointer_outside_typeref',first+4,struct.pack('<i',4),'environment outside'),
      ('reserved_buffer_flag',first+20,struct.pack('<I',0x01000018),'reserved flags'),
      ('buffer_outside_bound',first+20,struct.pack('<I',0x00fffffc),'buffer extent'),
      ('unknown_component',component,struct.pack('<I',0x05000000),'component kind'),
    ]
    for name,address,payload,message in failures:
        try:module['validate'](changed(address,payload),sections,patterns)
        except ValueError as error:assert message in str(error),(name,str(error))
        else:raise AssertionError('Damaged real KeyPath accepted: '+name)
        rejections.append(target+':'+name);checks+=1
    try:module['validate'](read,sections,patterns+[first])
    except ValueError:checks+=1;rejections.append(target+':duplicate_pattern')
    else:raise AssertionError('Duplicate pattern accepted')
    identities=[r for r in records if r['buffer_size']==0]
    for identity in identities:assert identity['root_type']==identity['leaf_type'];checks+=1
    for entry in pin.get('swift_keypath_environment_bounds',[]):
        address=int(entry['start'],16)
        try:module['validate_bounds'](changed(address,b'\x00'),records,[entry])
        except ValueError as error:assert 'bytes changed' in str(error)
        else:raise AssertionError('Damaged original environment accepted')
        checks+=1;rejections.append(target+':changed_environment_bytes')
        invalid=dict(entry,end=hex(int(entry['end'],16)+1))
        try:module['validate_bounds'](read,records,[invalid])
        except ValueError as error:assert 'boundary' in str(error)
        else:raise AssertionError('Unrelated boundary accepted')
        checks+=1;rejections.append(target+':unrelated_boundary')
        cursor=address+4;flags=struct.unpack('<I',read(address,4))[0];levels=flags&0xfff
        params=struct.unpack('<'+'H'*levels,read(cursor,2*levels))[-1]
        requirement_start=(cursor+2*levels+params+3)&~3
        assert flags>>12==2 and (int(entry['end'],16)-requirement_start)//12==1
        checks+=1
    cases.append(dict(target=target,original_sha256=pin['sha256'],patterns=len(records),
        environments=len({r['environment'] for r in records}),identity_patterns=len(identities),
        pinned_shorter_environment_extents=len(bounds)))
assert checks>=20
report=dict(checked_at=datetime.now(timezone.utc).isoformat(),verified=True,checks=checks,cases=cases,
    rejected_damaged_actual_records=rejections,manifest_snapshot=str(snapshot.relative_to(root)),manifest_snapshot_sha256=sha,
    sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['scripts/swift-keypath-environment-records.py','scripts/test-swift-keypath-environments.py']},
    full_SwiftUI_runtime_verified=False,resource_compilation_verified=False)
(root/'artifacts').mkdir(exist_ok=True)
(root/'artifacts/swift-keypath-environment-layouts.json').write_text(json.dumps(report,indent=2)+'\n')
print('Pinned original KeyPath structural checks passed:',checks)
