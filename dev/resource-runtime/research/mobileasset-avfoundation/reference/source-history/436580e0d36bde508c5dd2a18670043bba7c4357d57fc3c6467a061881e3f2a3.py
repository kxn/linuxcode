#!/usr/bin/env python3
"""Pin one original Intel image and optionally run its guarded reconstruction.

Always creates a new target and preserves the previous manifest bytes. The
builder still refuses unknown relocations; this helper does not choose symbols
for missing pointers or claim that a reconstructed image works at runtime.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import runpy
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
selection = parser.add_mutually_exclusive_group(required=True)
selection.add_argument('--image')
selection.add_argument('--from-target')
parser.add_argument('--exact-import-audit')
parser.add_argument('--verified-subset-import-audit', action='store_true',
                    help='For patch-GOT recovery, accept only independently rechecked selected rows; unresolved rows remain unbound and may still block emission')
parser.add_argument('--omit-lazy-helper-section', action='store_true',
    help='Omit the new lazy-helper section description when the pinned header is too small; mapped helper bytes remain present')
parser.add_argument('--omit-leading-padding-sections', action='store_true',
    help='Omit descriptions of newly allocated zero page-alignment padding; the builder rejects any fixup in an omitted range')
parser.add_argument('--preserve-original-uuid', action='store_true',
    help='Retain the pinned original LC_UUID identity; reconstructed bytes are still identified by their separate SHA256')
parser.add_argument('--read-only-data-const', action='store_true',
    help='Mark writable non-executable __DATA_CONST as SG_READ_ONLY for protection after dyld fixups')
parser.add_argument('--align-linkedit-streams', action='store_true',
    help='Align nonempty classic dyld opcode/export streams to eight bytes in the standalone LINKEDIT segment')
parser.add_argument('--preserve-code-with-patch-got', action='store_true',
                    help='Pin original v4 patch metadata and pooled GOT cells instead of rewriting instructions')
parser.add_argument('--patch-got-renamed-reexports', action='store_true',
                    help='Match original import names through explicit original export-trie reexport chains')
parser.add_argument('--allow-absent-weak-dependencies', action='store_true',
                    help='Pin absent original weak dylibs only when every reference is an undefined weak symbol')
parser.add_argument('--swift-keypath-pattern', action='append', default=[],
                    help='Pin a typed original KeyPath pattern and validate its environment and root/leaf references')
parser.add_argument('--target', required=True)
parser.add_argument('--build', action='store_true')
args = parser.parse_args()
assert not args.patch_got_renamed_reexports or args.preserve_code_with_patch_got
assert not args.verified_subset_import_audit or (args.from_target and args.exact_import_audit)
assert args.target and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.target)
manifest = root/'config/coregraphics-image-pins.json'
original_manifest = manifest.read_bytes()
pins = json.loads(original_manifest)
assert args.target not in pins
typed_class_aliases = []
typed_constant_aliases = []
if args.from_target:
    assert args.exact_import_audit and args.from_target in pins
    args.image = pins[args.from_target]['path']
else:
    assert not args.exact_import_audit
assert args.image.startswith('/') and '..' not in Path(args.image).parts
folder = root/('runtime/rebuilt-'+args.target)
report_path = root/('artifacts/'+args.target+'-input.json')
assert not folder.exists() and not report_path.exists()
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
image = ns['image'](args.image)
source = root/'runtime/fullsystem-libraries'/args.image.lstrip('/')
data = source.read_bytes()
assert data[:4] == bytes.fromhex('cffaedfe') and struct.unpack_from('<I', data, 4)[0] == 0x01000007
digest = lambda data: hashlib.sha256(data).hexdigest()
classes = sum(size//8 for name, segment, address, size, flags in image.sections if name == '__objc_classlist')
assert all(size % 8 == 0 for name, _, _, size, _ in image.sections if name == '__objc_classlist')
swift = any(name.startswith('__swift') for name, _, _, _, _ in image.sections)
pin = dict(path=args.image, sha256=digest(data), reference_set='fullsystem',
    objc_classes=classes, import_providers={})
absent_weak_proof = None
absent_weak_providers = set()
if args.allow_absent_weak_dependencies or (args.from_target and pins[args.from_target].get('absent_weak_dependencies')):
    weak_audit = runpy.run_path(str(root/'scripts/absent-weak-imports.py'))['audit']
    absent_weak_proof = weak_audit(data,root/'runtime/fullsystem-libraries',ns['image'])
    absent_weak_providers = {row['provider'] for row in absent_weak_proof['dependencies']}
    assert absent_weak_providers
    pin['absent_weak_dependencies'] = sorted(absent_weak_providers)
for section, key in [('__objc_catlist', 'restore_objc_categories'),
                     ('__objc_protolist', 'restore_objc_protocols')]:
    if not classes and any(name == section and size for name, _, _, size, _ in image.sections):
        pin[key] = True
if args.from_target:
    pin = copy.deepcopy(pins[args.from_target])
    assert pin['sha256'] == digest(data)
    if args.allow_absent_weak_dependencies:
        pin['absent_weak_dependencies'] = sorted(absent_weak_providers)
    assert set(pin.get('absent_weak_dependencies',[])) == absent_weak_providers
    audit_path = root/args.exact_import_audit
    audit = json.loads(audit_path.read_text())
    missing_path = root/('runtime/rebuilt-'+args.from_target+'/missing-cache-imports.json')
    missing = json.loads(missing_path.read_text())
    assert missing['diagnostic_only'] and not missing['image_emitted']
    assert audit['target'] == args.from_target
    assert audit['unresolved'] == sum(row['selected'] is None for row in audit['rows'])
    assert audit['unresolved'] == 0 or args.verified_subset_import_audit
    assert not args.verified_subset_import_audit or (args.preserve_code_with_patch_got or pin.get('preserve_code_with_patch_got'))
    assert audit['original_image_sha256'] == pin['sha256']
    assert audit['missing_imports_sha256'] == digest(missing_path.read_bytes())
    assert [(row['target'], row['slots']) for row in audit['rows']] == [
        (row['target'], row['slots']) for row in missing['imports']]
    wanted = {int(row['target'], 16) for row in audit['rows']}
    exact = {address: [] for address in wanted}
    for provider in image.dependencies:
        if provider in absent_weak_providers:
            assert audit['absent_weak_dependencies'] == absent_weak_proof
            continue
        original = root/'runtime/fullsystem-libraries'/provider.lstrip('/')
        assert digest(original.read_bytes()) == audit['original_dependency_sha256'][provider]
        for symbol, value in ns['image'](provider).exports.items():
            if value[0] == 'address' and value[1] in wanted:
                exact[value[1]].append([symbol, provider])
    additions = pin.setdefault('cache_imports', {})
    for row in audit['rows']:
        choices = exact[int(row['target'], 16)]
        assert choices == row['exports']
        if row['selected'] is None and args.verified_subset_import_audit:
            # Do not invent a symbol for this address. The builder must either
            # independently resolve it from typed metadata or refuse emission.
            continue
        if len(choices) == 1:
            assert choices[0] == row['selected']
            symbol, provider = choices[0]
        elif row.get('same_trivial_property_alias',False):
            proof = row['constant_alias_proof']
            verifier = runpy.run_path(str(root/'scripts/verify-original-constant-alias.py'))['verify']
            actual = verifier(ns,int(row['target'],16),choices,proof['selected_provider'],root)
            assert actual == proof and row['selected'] == choices[0]
            symbol,provider = row['selected']
            typed_constant_aliases.append(actual)
        else:
            # The Swift metadata name and ObjC Class name denote the same
            # object, not folded function bodies. Verify its actual section,
            # metaclass and original class_ro name before accepting this one
            # known alias pair. All other ambiguous identities still fail.
            provider = '/usr/lib/swift/libswiftCore.dylib'
            symbol = '_$ss20__StaticArrayStorageCN'
            names = {'_$ss20__StaticArrayStorageCN', '_OBJC_CLASS_$__TtCs20__StaticArrayStorage'}
            assert len(choices) == 2 and {name for name, _ in choices} == names
            assert {path for _, path in choices} == {provider} and row['selected'] == [symbol, provider]
            address = int(row['target'], 16)
            assert all(ns['resolve'](provider, name) == address for name in names)
            owner = ns['image'](provider)
            assert any(name == '__objc_data' and not flags & 0x80000400 and start <= address < start+size
                       for name, _, start, size, flags in owner.sections)
            metaclass = ns['resolve'](provider, '_OBJC_METACLASS_$__TtCs20__StaticArrayStorage')
            assert metaclass and ns['pointer'](address) == metaclass
            ro = ns['pointer'](address+32) & ~7
            raw_name = ns['read'](ns['pointer'](ro+24), 96).split(b'\0')[0]
            assert raw_name == b'_TtCs20__StaticArrayStorage'
            typed_class_aliases.append(dict(address=hex(address), metaclass=hex(metaclass),
                original_name=raw_name.decode(), selected_symbol=symbol))
        assert ns['resolve'](provider, symbol) == int(row['target'], 16)
        assert additions.get(symbol, provider) == provider
        additions[symbol] = provider
if args.omit_lazy_helper_section:
    pin['describe_lazy_helpers'] = False
if args.omit_leading_padding_sections:
    pin['describe_leading_padding'] = False
if args.preserve_original_uuid:
    pin['preserve_original_uuid'] = True
if args.read_only_data_const:
    pin['read_only_data_const'] = True
if args.align_linkedit_streams:
    pin['align_linkedit_streams'] = True
keypath_validation = None
if args.swift_keypath_pattern:
    assert swift
    patterns = [int(value,0) for value in args.swift_keypath_pattern]
    assert len(patterns) == len(set(patterns))
    patterns = sorted(set(patterns) | {int(value,16) for value in pin.get('swift_keypath_patterns',[])})
    validator = runpy.run_path(str(root/'scripts/swift-keypath-environment-records.py'))['validate']
    sections = [(segment,name,start,size) for name,segment,start,size,flags in image.sections]
    keypath_validation = validator(ns['read'],sections,patterns)
    pin['swift_keypath_patterns'] = [hex(value) for value in patterns]
patch_contract = None
if args.preserve_code_with_patch_got:
    assert not pin.get('import_providers') and not pin.get('backend_call_overrides')
    original_imports = {}
    at = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, length = struct.unpack_from('<II', data, at)
        if command == 2:
            symoff, count, stroff, strsize = struct.unpack_from('<4I', data, at+8)
            assert symoff + count*16 <= len(data) and stroff + strsize <= len(data)
            for index in range(count):
                start, kind, _, desc, value = struct.unpack_from('<IBBHQ', data, symoff+index*16)
                if kind & 0xe or not kind & 1:
                    continue
                assert start < strsize
                end = data.index(0, stroff+start, stroff+strsize)
                name = data[stroff+start:end].decode()
                ordinal = desc >> 8
                assert 0 <= ordinal <= len(image.dependencies)
                provider = image.dependencies[ordinal-1] if ordinal else args.image
                if provider in absent_weak_providers:
                    assert desc & 0x40 and value == 0
                    continue
                address = ns['resolve'](provider, name)
                assert address is not None
                original_imports.setdefault(address, []).append((name, ordinal, bool(desc & 0x40)))
        at += length
    for name, provider in pin.get('cache_imports', {}).items():
        assert provider in image.dependencies
        address = ns['resolve'](provider, name)
        assert address is not None
        original_imports.setdefault(address, []).append((name, image.dependencies.index(provider)+1, False))
    reader = runpy.run_path(str(root/'scripts/cache-patch-metadata.py'))
    if args.patch_got_renamed_reexports:
        pin['patch_got_renamed_reexports'] = True
    metadata = reader['read_image_bindings'](ns, args.image, original_imports,
        follow_renamed_reexports=pin.get('patch_got_renamed_reexports',False))
    canonical_imports = []
    if pin.get('patch_got_renamed_reexports',False):
        ambiguous = {}
        for record in metadata['got_records']:
            if len(record.get('matching_import_names',[])) > 1:
                key = (record['symbol'], record['implementation'])
                assert not record['weak_import'], 'Canonical weak import needs separate image-specific proof'
                ambiguous.setdefault(key, []).append(record['slot'])
        for (name, address), slots in ambiguous.items():
            # Two public names can explicitly reexport the same canonical
            # function. Bind that exact canonical export through an existing
            # original dependency, instead of choosing either public API.
            providers = [provider for provider in image.dependencies
                         if provider not in absent_weak_providers and ns['resolve'](provider,name) == address]
            assert len(providers) == 1, 'Canonical patch symbol has no unique original dependency'
            provider = providers[0]
            additions = pin.setdefault('cache_imports',{})
            assert additions.get(name,provider) == provider
            additions[name] = provider
            original_imports.setdefault(address,[]).append((name,image.dependencies.index(provider)+1,False))
            canonical_imports.append(dict(symbol=name,provider=provider,
                implementation=hex(address),slots=[hex(slot) for slot in sorted(slots)]))
        if canonical_imports:
            metadata = reader['read_image_bindings'](ns,args.image,original_imports,
                follow_renamed_reexports=True)
    addends = reader['addend_imports'](metadata, original_imports)
    got = reader['exact_imports'](metadata['got_records'], original_imports, pooled=True)
    assert got, 'No verified original pooled GOT cells'
    pin.update(cache_patch_addends=True, cache_patch_addends_expected=len(addends),
        preserve_code_with_patch_got=True, patch_got_expected=len(got),
        patch_got_range=[hex(min(got) & ~4095), hex((max(got)+8+4095) & ~4095)])
    if swift:
        pin['preserve_swift_code_with_patch_got'] = True
    patch_contract = dict(original_records=len(metadata['records']), nonzero_addends=len(addends),
        got_cells=len(got), patch_info_sha256=metadata['patch_info_sha256'],
        canonical_imports=canonical_imports,
        source_sha256=digest((root/'scripts/cache-patch-metadata.py').read_bytes()))
old_sha = digest(original_manifest)
snapshot = root/'runtime/source-input-history'/old_sha
if snapshot.exists(): assert snapshot.read_bytes() == original_manifest
else: snapshot.write_bytes(original_manifest)
history_path = root/'runtime/source-input-history/manifest.json'
history = json.loads(history_path.read_text())
name = str(manifest.relative_to(root))
previous = history.get(name, {})
revisions = dict(previous.get('revisions', {}))
if 'sha256' in previous: revisions[previous['sha256']] = previous['snapshot']
history[name] = dict(sha256=old_sha, snapshot=str(snapshot.relative_to(root)), revisions=revisions)
history_path.write_text(json.dumps(history, indent=2)+'\n')
pins[args.target] = pin
manifest.write_text(json.dumps(pins, indent=2)+'\n')
command = ['python3', 'scripts/rebuild-c-cache-image.py', '--target-manifest', str(manifest.relative_to(root)),
    '--target', args.target, '--lazy-functions', '--collect-missing-imports']
command += ['--experimental-swift', '--repair-swift-relative'] if swift else ['--analyze-code']
record = dict(target=args.target, pin=pin, original_bytes=len(data), swift_metadata=swift,
    original_dependencies=image.dependencies, previous_manifest_sha256=old_sha,
    manifest_sha256=digest(manifest.read_bytes()), command=command,
    preparation_source_sha256=digest(Path(__file__).read_bytes()),
    reconstruction_attempted=False, image_runtime_verified=False)
if args.from_target:
    record.update(parent_target=args.from_target, exact_import_audit=args.exact_import_audit,
        exact_import_audit_sha256=digest(audit_path.read_bytes()), typed_class_aliases=typed_class_aliases)
    if typed_constant_aliases:
        record['typed_constant_aliases'] = typed_constant_aliases
    if args.verified_subset_import_audit:
        record['audit_unresolved_rows_not_selected'] = audit['unresolved']
if patch_contract is not None:
    record['original_patch_contract'] = patch_contract
if absent_weak_proof is not None:
    record['original_absent_weak_dependencies'] = absent_weak_proof
    record['absent_weak_audit_source_sha256'] = digest((root/'scripts/absent-weak-imports.py').read_bytes())
if keypath_validation is not None:
    record['typed_keypath_patterns'] = keypath_validation
    record['keypath_validator_sha256'] = digest((root/'scripts/swift-keypath-environment-records.py').read_bytes())
report_path.write_text(json.dumps(record, indent=2)+'\n')
status = 0
if args.build:
    log = root/('logs/'+args.target+'-build.log')
    assert not log.exists()
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    status = result.returncode
    record.update(reconstruction_attempted=True, build_returncode=status,
        log=str(log.relative_to(root)), log_sha256=digest(log.read_bytes()))
    report_path.write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', report_path.relative_to(root))
raise SystemExit(status)
