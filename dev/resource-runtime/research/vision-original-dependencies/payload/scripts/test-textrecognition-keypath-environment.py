#!/usr/bin/env python3
"""Check the actual stripped TextRecognition environment and damaged controls."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = root/args.output
assert not output.exists()
sha = lambda p: hashlib.sha256((root/p).read_bytes()).hexdigest()
preparation = 'artifacts/vision-closure-textrecognition-resource-v2-input.json'
record = json.loads((root/preparation).read_text())
pin = record['pin']
assert sha('runtime/fullsystem-libraries'+pin['path']) == pin['sha256']
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
image = ns['image'](pin['path'])
sections = [(seg, name, at, size) for name, seg, at, size, flags in image.sections]
module = runpy.run_path(str(root/'scripts/swift-keypath-environment-records.py'))
read = ns['read']
patterns = [int(p,16) for p in pin['swift_keypath_patterns']]
paths = module['validate'](read, sections, patterns)
bounds = pin['swift_keypath_environment_bounds']
actual = module['validate_bounds'](read, paths, bounds)
assert len(paths) == len(actual) == 1
start, end = next(iter(actual.items()))
assert paths[0]['environment'] == hex(start) and paths[0]['root_type'] == hex(end)
assert end-start == 12
flags, first, last, p0, p1, padding = struct.unpack('<IHHBBH', read(start,12))
assert (flags,first,last,p0,p1,padding) == (8194,1,2,128,128,0)
rejected = []
def rejects(name, call, message):
    try:
        call()
    except ValueError as error:
        assert message in str(error), (name,str(error))
        rejected.append(name)
    else:
        raise AssertionError('Damaged metadata accepted: '+name)

def changed(at, payload):
    def reader(address, length):
        data = bytearray(read(address,length))
        for pos in range(max(address,at),min(address+length,at+len(payload))):
            data[pos-address] = payload[pos-at]
        return bytes(data)
    return reader

rejects('changed_original_environment',
    lambda: module['validate_bounds'](changed(start,b'\x03'),paths,bounds), 'bytes changed')
rejects('unrelated_end_address',
    lambda: module['validate_bounds'](read,paths,[dict(bounds[0],end=hex(end+1))]), 'boundary')
rejects('duplicate_environment',
    lambda: module['validate_bounds'](read,paths,bounds+bounds), 'boundary')
rejects('unreferenced_environment',
    lambda: module['validate_bounds'](read,[],bounds), 'boundary')
rejects('duplicate_keypath',
    lambda: module['validate'](read,sections,patterns+patterns), 'pattern list')
pattern = patterns[0]
delta = struct.unpack('<i',read(pattern+8,4))[0]
rejects('root_type_tag_removed',
    lambda: module['validate'](changed(pattern+8,struct.pack('<i',delta+1)),sections,patterns), 'mangled type')
rebuilt = 'runtime/rebuilt-vision-closure-textrecognition-resource-v2/reconstruction.json'
recovery = json.loads((root/rebuilt).read_text())
assert recovery['rip_instructions_patched'] == 0
assert recovery['byte_preserving_patch_got']['executable_sections_byte_equal']
assert recovery['swift_metadata']['overstated_keypath_requirements'] == [dict(
    environment=hex(start),declared=2,emitted=0,original_header_preserved=True)]
assert recovery['swift_metadata']['generic_environments'] == [dict(start=hex(start),end=hex(end))]
output.write_text(json.dumps(dict(verified=True,original_path=pin['path'],
    original_sha256=pin['sha256'],validated_patterns=paths,environment_bounds=bounds,
    original_header_preserved=True,declared_requirements=2,emitted_requirements=0,
    rejected_damaged_records=rejected,executable_sections_byte_equal=True,
    image_execution_verified=False,resource_compilation_verified=False,
    sources={p:sha(p) for p in [str(Path(__file__).relative_to(root)),
        'scripts/prepare-resource-image-candidate.py','scripts/swift-keypath-environment-records.py',
        'scripts/restore-swift-metadata.py',preparation,rebuilt]}),indent=2)+'\n')
print('Actual TextRecognition KeyPath environment verified; six damaged controls rejected')
