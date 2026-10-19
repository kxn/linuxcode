#!/usr/bin/env python3
"""Record exact original dependency exports for unresolved cache pointers.

Read-only with respect to images and pins. Ambiguous function addresses are
never selected. The known Swift Class alias is only proposed here; candidate
preparation independently verifies its section, isa and original class name.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
pins = json.loads((root/'config/coregraphics-image-pins.json').read_text())
pin = pins[args.target]
assert pin['reference_set'] == 'fullsystem'
output = root/args.output
assert not output.exists()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
original = root/'runtime/fullsystem-libraries'/pin['path'].lstrip('/')
assert sha(original) == pin['sha256']
missing_path = root/('runtime/rebuilt-'+args.target+'/missing-cache-imports.json')
missing = json.loads(missing_path.read_text())
assert missing['diagnostic_only'] and not missing['image_emitted']
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
dependencies = ns['image'](pin['path']).dependencies
wanted = {int(row['target'], 16) for row in missing['imports']}
exact = {address: [] for address in wanted}
dependency_sha = {}
for provider in dependencies:
    dependency_sha[provider] = sha(root/'runtime/fullsystem-libraries'/provider.lstrip('/'))
    for symbol, value in ns['image'](provider).exports.items():
        if value[0] == 'address' and value[1] in exact:
            exact[value[1]].append([symbol, provider])
class_alias = {'_$ss20__StaticArrayStorageCN', '_OBJC_CLASS_$__TtCs20__StaticArrayStorage'}
swift_provider = '/usr/lib/swift/libswiftCore.dylib'
rows = []
for item in missing['imports']:
    choices = exact[int(item['target'], 16)]
    alias = (len(choices) == 2 and {name for name, _ in choices} == class_alias
             and {provider for _, provider in choices} == {swift_provider})
    selected = choices[0] if len(choices) == 1 else (
        ['_$ss20__StaticArrayStorageCN', swift_provider] if alias else None)
    rows.append(dict(target=item['target'], slots=item['slots'], exports=choices,
                     selected=selected, same_class_alias=alias))
report = dict(target=args.target, original_image_sha256=pin['sha256'],
    missing_imports_sha256=sha(missing_path), original_dependency_sha256=dependency_sha,
    unresolved=sum(row['selected'] is None for row in rows), rows=rows,
    sources={str(Path(__file__).relative_to(root)): sha(Path(__file__)),
             'scripts/dsc-image.py': sha(root/'scripts/dsc-image.py')},
    image_emitted=False, runtime_execution_verified=False)
output.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(dict(output=str(output.relative_to(root)), imports=len(rows),
                     unresolved=report['unresolved'])))
raise SystemExit(1 if report['unresolved'] else 0)
