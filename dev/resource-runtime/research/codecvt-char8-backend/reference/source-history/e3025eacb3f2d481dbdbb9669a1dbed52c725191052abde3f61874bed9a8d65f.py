#!/usr/bin/env python3
"""Build every libc++ backend source unit in a fresh, uninstalled directory.

This keeps locale construction and its char8_t facets in one implementation.
The result is experimental until native locale and existing consumer tests pass.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--standard', choices=['c++11', 'c++20'], default='c++20')
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root/('runtime/libcxx-char8-backend-'+args.tag)
report_path = root/('artifacts/libcxx-char8-backend-'+args.tag+'-build.json')
assert not folder.exists() and not report_path.exists()
folder.mkdir()
(folder/'objects').mkdir()
(folder/'libraries').mkdir()
source_root = root/'vendor/darling/src/external/libcxx'
cmake = source_root/'CMakeLists.txt'
sources = re.search(r'set\(cxx_sources\s+(.*?)\n\)', cmake.read_text(), re.S)[1].split()
assert sources and len(sources) == len(set(sources)) and 'src/locale.cpp' in sources
sdk = root/'vendor/darling/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
relative = lambda p: str(Path(p).relative_to(root))
record = dict(installed=False, runtime_execution_verified=False, full_xcode_build_ready=False,
    standard=args.standard, backend_source_units=len(sources), compilation=[], linked=False,
    cmake=relative(cmake), cmake_sha256=sha(cmake),
    old_backend=relative(guest/'usr/lib/libc++0.dylib'),
    old_backend_sha256=sha(guest/'usr/lib/libc++0.dylib'),
    sources={}, compiler_headers={})


def save():
    report_path.write_text(json.dumps(record, indent=2)+'\n')


objects = []
for path in sources:
    source = source_root/path
    output = folder/'objects'/(source.stem+'.o')
    dep = output.with_suffix('.d')
    log = output.with_suffix('.log')
    command = ['clang++-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
        '-I', str(root/'vendor/darling/basic-headers'), '-nostdinc++',
        '-I', str(source_root/'include'), '-I', str(source_root.parent/'libcxxabi/include'),
        '-D_LIBCPP_BUILDING_LIBRARY=1', '-DLIBCXX_BUILDING_LIBCXXABI=1', '-DPLATFORM_MacOSX=1',
        '-std='+args.standard, '-O2', '-fPIC', '-fvisibility=hidden', '-fvisibility-inlines-hidden',
        '-MD', '-MF', str(dep), '-c', str(source), '-o', str(output)]
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    item = dict(source=relative(source), source_sha256=sha(source), command=command,
        returncode=result.returncode, log=relative(log), log_sha256=sha(log))
    record['compilation'].append(item)
    if result.returncode:
        save()
        print(log.read_text()[-4000:], flush=True)
        raise SystemExit(result.returncode)
    item.update(object=relative(output), object_sha256=sha(output))
    dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').partition(':')[2])
    for name in dependencies:
        file = Path(name).resolve()
        if file.is_relative_to(root):
            record['sources'][relative(file)] = sha(file)
        else:
            record['compiler_headers'][str(file)] = sha(file)
    objects.append(output)
    print('COMPILED', path, flush=True)
    save()

library = folder/'libraries/libc++0.dylib'
raw = folder/'unprocessed-libc++0.dylib'
abi = guest/'usr/lib/libc++abi.dylib'
policy = source_root/'lib/libc++unexp.exp'
command = ['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-install_name', '/usr/lib/libc++0.dylib', '-compatibility_version', '1.0.0',
    '-current_version', '1.0.0', '-syslibroot', str(guest), '-L', str(guest/'usr/lib'),
    '-lSystem', '-reexport_library', str(abi), '-unexported_symbols_list', str(policy),
    *[str(p) for p in objects], '-o', str(raw)]
log = folder/'link.log'
with log.open('w') as out:
    result = subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
record.update(link_command=command, link_returncode=result.returncode, link_log=relative(log),
    link_log_sha256=sha(log), ABI_library=relative(abi), ABI_library_sha256=sha(abi),
    export_policy=relative(policy), export_policy_sha256=sha(policy),
    Apple_force_weak_and_notweak_policies_applied=False)
if result.returncode:
    save()
    print(log.read_text()[-4000:], flush=True)
    raise SystemExit(result.returncode)
normalize = runpy.run_path(str(root/'scripts/normalize-macho-weak-bind.py'))['normalize']
data, normalization = normalize(raw.read_bytes())
library.write_bytes(data)


def exports(path):
    text = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
    return set(re.findall(r'^0x[0-9A-Fa-f]+\s+(\S+)', text, re.M))


before, after = exports(root/record['old_backend']), exports(library)
record.update(linked=True, library=relative(library), library_sha256=sha(library),
    previous_backend_direct_exports=len(before), direct_exports=len(after),
    previous_backend_missing_exports=sorted(before-after), added_exports=sorted(after-before),
    weak_bind_normalization=normalization,
    builder=relative(Path(__file__)), builder_sha256=sha(Path(__file__)))
save()
print('BUILD_REPORT', relative(report_path), 'missing', len(before-after), 'added', len(after-before))
