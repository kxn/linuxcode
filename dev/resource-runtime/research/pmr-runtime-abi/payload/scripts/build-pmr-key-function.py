#!/usr/bin/env python3
"""Build the genuine PMR key function; preserve the existing libc++ components.

The compiler emits standard-namespace RTTI and a vtable from the actual SDK
declaration. This does not implement the remaining standard PMR pool runtime.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root/('runtime/pmr-key-function-'+args.tag)
report_path = root/('artifacts/pmr-key-function-'+args.tag+'-build.json')
assert not folder.exists() and not report_path.exists()
folder.mkdir()
(folder/'libraries').mkdir()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
previous_path = 'artifacts/expected-access-source-build.json'
previous = json.loads((root/previous_path).read_text())
assert sha(previous['library']) == previous['library_sha256']
for path, expected in {**previous['source_files'], **previous['existing_object_inputs']}.items():
    assert sha(path) == expected, path
typed = json.loads((root/'artifacts/typed-new-delete-source-build.json').read_text())
assert sha(typed['backend']) == typed['backend_sha256']
inputs = [*previous['existing_object_inputs'], 'runtime/expected-access-source/expected_exception.o']
input_sha = {path: sha(path) for path in inputs}
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = 'scripts/pmr-memory-resource.cpp'
official = 'vendor/llvm-charconv/libcxx/src/memory_resource.cpp'
method = 'memory_resource::~memory_resource() = default;'
assert method in (root/source).read_text() and method in (root/official).read_text()
header = str((sdk/'usr/include/c++/v1/__memory_resource/memory_resource.h').relative_to(root))
assert 'virtual ~memory_resource();' in (root/header).read_text()
obj = folder/'memory_resource.o'
compile_command = ['clang++-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
    '-nostdinc++', '-isystem', str(sdk/'usr/include/c++/v1'), '-std=c++17',
    '-D_LIBCPP_DISABLE_AVAILABILITY', '-O2', '-fPIC', '-c', str(root/source), '-o', str(obj)]
subprocess.run(compile_command, check=True, cwd=root)
guest = root/'runtime/rootfs/usr/libexec/darling'
link = ['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-install_name', '/usr/lib/libc++.1.dylib', '-compatibility_version', '1.0.0',
    '-current_version', '1.0.0', '-syslibroot', str(guest), '-L', str(guest/'usr/lib'),
    '-lSystem', '-reexport_library', str(root/typed['backend']), *[str(root/p) for p in inputs]]
normalize = runpy.run_path(str(root/'scripts/normalize-macho-weak-bind.py'))['normalize']
baseline = folder/'baseline-relink.dylib'
subprocess.run([*link, '-o', str(baseline)], check=True, cwd=root)
baseline.write_bytes(normalize(baseline.read_bytes())[0])
old, control = (root/previous['library']).read_bytes(), baseline.read_bytes()
assert len(old) == len(control)
at, uuid = 32, None
for _ in range(struct.unpack_from('<I', old, 16)[0]):
    command, size = struct.unpack_from('<II', old, at)
    if command == 0x1b:
        uuid = (at+8, at+24)
    at += size
assert uuid is not None and all(a == b or uuid[0] <= i < uuid[1]
    for i, (a, b) in enumerate(zip(old, control))), 'Baseline relink changed existing bytes'
output = folder/'libraries/libc++.1.dylib'
raw = folder/'unprocessed-libc++.1.dylib'
subprocess.run([*link, str(obj), '-o', str(raw)], check=True, cwd=root)
data, normalization = normalize(raw.read_bytes())
output.write_bytes(data)

def exports(path):
    text = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(root/path)], text=True)
    return set(re.findall(r'^0x[0-9A-Fa-f]+\s+(\S+)', text, re.M))

before, after = exports(previous['library']), exports(str(output.relative_to(root)))
required = {'__ZNSt3__13pmr15memory_resourceD'+n+'Ev' for n in ['0', '1', '2']}
required |= {'__ZT'+n+'NSt3__13pmr15memory_resourceE' for n in ['I', 'S', 'V']}
assert before <= after and after-before == required, sorted(after-before)
record = dict(library=str(output.relative_to(root)), library_sha256=sha(str(output.relative_to(root))),
    parent_build=previous_path, parent_build_sha256=sha(previous_path),
    baseline=str(baseline.relative_to(root)), baseline_sha256=sha(str(baseline.relative_to(root))),
    baseline_only_UUID_differs=True, baseline_UUID_range=uuid,
    original_direct_exports_preserved=len(before), added_exports=sorted(required),
    source=source, source_sha256=sha(source), upstream_source=official,
    upstream_source_sha256=sha(official), SDK_header=header, SDK_header_sha256=sha(header),
    key_function_body_unchanged=True, class_declaration_from_actual_SDK=True,
    compiler_generated_RTTI_and_vtable=True, experimental_namespace_aliased=False,
    existing_object_inputs=input_sha, backend=typed['backend'], backend_sha256=sha(typed['backend']),
    new_object=str(obj.relative_to(root)), new_object_sha256=sha(str(obj.relative_to(root))),
    compile_command=compile_command, link_command=link, weak_bind_normalization=normalization,
    full_PMR_runtime=False, runtime_execution_verified=False, installed=False)
report_path.write_text(json.dumps(record, indent=2)+'\n')
print('BUILD_REPORT', report_path.relative_to(root), 'preserved', len(before), 'added', len(required))
