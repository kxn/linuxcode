#!/usr/bin/env python3
"""Link the complete source library and migrate explicit compatibility exports."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--objects', required=True)
parser.add_argument('--stage', default='artifacts/shared-remap-runtime-v2-stage.json')
parser.add_argument('--tag', default='')
parser.add_argument('--template', default='runtime/simd-matrix-source/libraries/libSystem.B.dylib')
parser.add_argument('--runtime-profile', default='scripts/shared-remap-runtime-profile.py')
parser.add_argument('--profile-arguments-file', help='JSON keyword arguments for the real provider runtime profile')
args = parser.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
report_path = root / args.objects
record = json.loads(report_path.read_text())
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
for name, digest in {**record['sources'], **record.get('dependency_sha256', {}), **record.get('object_sha256', {})}.items():
    resolve(name, digest)
folder = report_path.parent
folder = folder / args.tag if args.tag else folder
folder.mkdir(exist_ok=True)
raw = folder / 'libSystem.raw.dylib'
output = folder / 'libSystem.B.dylib'
assert not raw.exists() and not output.exists()
template = root / args.template
helper = runpy.run_path(str(root / 'scripts/macho-named-reexport.py'))

def inspect(data, provider=False):
    if data[:4] == bytes.fromhex("cafebabe"):
        slices = [struct.unpack_from(">5I", data, 8+20*i) for i in range(struct.unpack_from(">I", data, 4)[0])]
        selected = next(row for row in slices if row[0] == 0x1000007)
        data = data[selected[2]:selected[2]+selected[3]]
    assert data[:8] == bytes.fromhex('cffaedfe07000001')
    deps, exports, linkedit, code = [], None, None, []
    at = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, at)
        if cmd in (0xc, 0x80000018, 0x8000001f, 0x80000023, 0x20):
            start = at + struct.unpack_from('<I', data, at + 8)[0]
            deps.append((data[start:data.index(0, start)].decode(), cmd))
        elif cmd in (0x22, 0x80000022):
            exports = at + 40
        elif cmd == 0x80000033:
            exports = at + 8
        elif cmd == 0x19:
            if data[at+8:at+24].split(b'\0')[0] == b'__LINKEDIT':
                linkedit = at
            for j in range(struct.unpack_from('<I', data, at + 64)[0]):
                sec = at + 72 + 80*j
                if struct.unpack_from('<I', data, sec+64)[0] & 0x80000400:
                    off = struct.unpack_from('<I', data, sec+48)[0]
                    length = struct.unpack_from('<Q', data, sec+40)[0]
                    code.append((off, length))
        elif cmd == 0x1d and not provider:
            raise ValueError('Source output must not carry a stale signature')
        at += size
    assert exports is not None and linkedit is not None
    off, length = struct.unpack_from('<II', data, exports)
    return deps, exports, linkedit, helper['entries'](data[off:off+length]), code

def take(data, at=0):
    value = shift = 0
    while True:
        byte = data[at]
        at += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, at
        shift += 7
        assert shift < 64

old_data = template.read_bytes()
old_deps, _, _, old_exports, _ = inspect(old_data)
profile_arguments = json.loads((root / args.profile_arguments_file).read_text()) if args.profile_arguments_file else dict(stage=args.stage)
assert isinstance(profile_arguments, dict)
module = runpy.run_path(str(root / args.runtime_profile))
p = module['profile'](**profile_arguments)
library_path = next(arg.split('=', 1)[1] for arg in p['command'] if arg.startswith('DYLD_LIBRARY_PATH='))
dirs = [root / item.removeprefix('/Volumes/SystemRoot/workspace/')
        for item in library_path.split(':') if item.startswith('/Volumes/SystemRoot/workspace/')]
selected = {Path(row['path']).name: root / row['path'] for row in p['source_runtime'].values()}
guestroot = root / 'runtime/rootfs/usr/libexec/darling'
command = ['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-install_name', '/usr/lib/libSystem.B.dylib', '-current_version', '1281.0.0',
    '-compatibility_version', '1.0.0', '-headerpad', '0x10000', '-no_adhoc_codesign',
    '-no_fixup_chains', '-syslibroot', str(guestroot),
    *[str(root / name) for name in record['objects']]]
inputs = {}
for index, (name, kind) in enumerate(old_deps):
    candidate = selected.get(Path(name).name)
    if candidate is None:
        candidate = next((base / Path(name).name for base in dirs if (base / Path(name).name).is_file()), None)
    if candidate is None:
        candidate = guestroot / name.lstrip('/')
    assert candidate.is_file(), name
    inputs[str(candidate.relative_to(root))] = sha(candidate)
    # Only expose symbols this provider actually exports. Following arbitrary
    # dependency cycles at link time can falsely attribute dlsym to libTrace.
    # These are link descriptions, never runtime substitute implementations.
    _, _, _, provider_exports, _ = inspect(candidate.read_bytes(), provider=True)
    regular, weak, tls = [], [], []
    for symbol, terminal in provider_exports.items():
        flags, _ = take(terminal)
        target = tls if flags & 3 == 1 else weak if flags & 4 else regular
        target.append(symbol.decode())
    stub = folder / ('provider-' + str(index) + '.tbd')
    stub.write_text('--- !tapi-tbd-v3\narchs: [ x86_64 ]\nplatform: macosx\n'
        + 'install-name: ' + json.dumps(name) + '\ncurrent-version: 1.0.0\ncompatibility-version: 1.0.0\n'
        + 'exports:\n  - archs: [ x86_64 ]\n'
        + ''.join('    ' + key + ': ' + json.dumps(sorted(values)) + '\n' for key, values in
            [('symbols', regular), ('weak-def-symbols', weak), ('thread-local-symbols', tls)] if values)
        + '...\n')
    command += ['-needed_library', str(stub)]
command += ['-o', str(raw)]
print('LINK', raw, flush=True)
subprocess.run(command, cwd=root, check=True)
data = bytearray(raw.read_bytes())
# LLD 19 emits both LC_LOAD_DYLIB and LC_REEXPORT_DYLIB for this
# -reexport_library form while binding ordinals count only one. Preserve one
# command per dependency and mark its existing command as a namespace reexport.
at = 32
reexport_names = {name for name, kind in old_deps if kind == 0x8000001f}
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    cmd, size = struct.unpack_from('<II', data, at)
    if cmd == 0xc:
        start = at + struct.unpack_from('<I', data, at+8)[0]
        name = data[start:data.index(0, start)].decode()
        if name in reexport_names:
            struct.pack_into('<I', data, at, 0x8000001f)
    if cmd in (0x22, 0x80000022):
        weak_offset, weak_size = struct.unpack_from('<II', data, at+24)
        weak = bytes(data[weak_offset:weak_offset+weak_size])
        # dyld2 merges weak symbols as a sorted stream. LLD emits these
        # strong-definition markers in source order, splitting kqueue owners.
        markers = []
        pos = 0
        while pos < len(weak) and weak[pos]:
            assert weak[pos] == 0x48, 'Only reorder pure strong-definition markers'
            end = weak.index(0, pos+1)
            markers.append(weak[pos+1:end])
            pos = end+1
        assert not any(weak[pos:])
        ordered = b''.join(b'\x48'+name+b'\0' for name in sorted(markers))
        assert len(ordered) <= weak_size
        data[weak_offset:weak_offset+weak_size] = ordered.ljust(weak_size, b'\0')
    at += size
deps, exp_at, linkedit, exports, code = inspect(data)
new_exports = dict(exports)
local_count = named_count = 0
for name, terminal in old_exports.items():
    flags, pos = take(terminal)
    if flags & 8:
        ordinal, pos = take(terminal, pos)
        provider = old_deps[ordinal-1][0]
        new_ordinal = next(i+1 for i, row in enumerate(deps) if row[0] == provider)
        new_exports[name] = helper['uleb'](flags) + helper['uleb'](new_ordinal) + terminal[pos:]
        named_count += 1
    else:
        assert name in exports, ('Missing source export', name)
        new_flags, _ = take(exports[name])
        assert not new_flags & 8, ('Source export unexpectedly reexported', name)
        assert (flags & 3) == (new_flags & 3), ('Source export kind mismatch', name)
        local_count += 1
fresh = helper['trie'](new_exports)
assert helper['entries'](fresh) == new_exports
data.extend(bytes(-len(data) % 8))
offset = len(data)
data.extend(fresh)
struct.pack_into('<II', data, exp_at, offset, len(fresh))
fileoff = struct.unpack_from('<Q', data, linkedit+40)[0]
filesize = len(data)-fileoff
struct.pack_into('<Q', data, linkedit+48, filesize)
struct.pack_into('<Q', data, linkedit+32, (filesize+4095)&~4095)
original = raw.read_bytes()
for start, length in code:
    assert data[start:start+length] == original[start:start+length]
output.write_bytes(data)
result = dict(full_initializer_and_queue_source_build=True, complete_source_files=len(record['objects']),
    object_report=args.objects, stage=args.stage, template=args.template, command=command,
    provider_runtime_profile=args.runtime_profile, provider_profile_arguments=profile_arguments,
    source_local_exports_preserved=local_count, named_reexports_preserved=named_count,
    original_source_instructions_preserved=True, runtime_execution_verified=False,
    output=str(output.relative_to(root)), output_sha256=sha(output),
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), report_path,
        root / 'scripts/macho-named-reexport.py', template, raw, output]},
    link_inputs=inputs, full_Unity_build_verified=False)
for path in [root / args.runtime_profile, *([root / args.profile_arguments_file] if args.profile_arguments_file else [])]:
    result['files'][str(path.relative_to(root))] = sha(path)
(folder / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
print('BUILD_REPORT', folder / 'build.json')
