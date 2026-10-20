#!/usr/bin/env python3
"""Build the complete existing libcxxabi source list in an isolated directory."""
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
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root / ('runtime/cxxabi-primary-exception-' + args.tag)
report_path = root / ('artifacts/cxxabi-primary-exception-' + args.tag + '-build.json')
assert not folder.exists() and not report_path.exists()
(folder / 'objects').mkdir(parents=True)
(folder / 'libraries').mkdir()
source_root = root / 'vendor/darling/src/external/libcxxabi'
cmake = source_root / 'CMakeLists.txt'
body = re.search(r'set\(cxxabi_sources\s+(.*?)\n\)', cmake.read_text(), re.S)[1]
sources = re.sub(r'#[^\n]*', '', body).split()
assert len(sources) == len(set(sources)) == 18 and 'src/cxa_exception.cpp' in sources
sdk = root / 'vendor/darling/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root / 'runtime/rootfs/usr/libexec/darling'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
rel = lambda p: str(Path(p).relative_to(root))
baseline = guest / 'usr/lib/libc++abi.dylib'
record = dict(installed=False, linked=False, runtime_execution_verified=False,
              complete_source_units=len(sources), compilation=[], sources={}, compiler_headers={},
              cmake=rel(cmake), cmake_sha256=sha(cmake), baseline_library=rel(baseline),
              baseline_library_sha256=sha(baseline), builder=rel(Path(__file__)),
              builder_sha256=sha(Path(__file__)))


def save():
    report_path.write_text(json.dumps(record, indent=2) + '\n')


objects = []
for name in sources:
    source = source_root / name
    obj = folder / 'objects' / (source.stem + '.o')
    dep, log = obj.with_suffix('.d'), obj.with_suffix('.log')
    command = ['clang++-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
               '-I', str(root / 'vendor/darling/basic-headers'), '-nostdinc++',
               '-I', str(source_root.parent / 'libcxx/include'),
               '-I', str(source_root.parent / 'libcxx'),
               '-I', str(source_root / 'include'),
               '-I', str(source_root.parent / 'libunwind/include'),
               '-idirafter', str(source_root.parent / 'xnu/EXTERNAL_HEADERS'),
               '-D_LIBCXXABI_BUILDING_LIBRARY=1', '-D_LIBCPP_BUILDING_LIBRARY=1',
               '-D__DARWIN_NON_CANCELABLE=1', '-D_LIBCPP_HAS_NO_LIBRARY_ALIGNED_ALLOCATION=1',
               '-DPLATFORM_MacOSX=1', '-DDARLING=1', '-std=c++11', '-O0', '-fPIC',
               '-MD', '-MF', str(dep), '-c', str(source), '-o', str(obj)]
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    row = dict(source=rel(source), source_sha256=sha(source), command=command,
               returncode=result.returncode, log=rel(log), log_sha256=sha(log))
    record['compilation'].append(row)
    if result.returncode:
        save()
        print(log.read_text()[-3000:], flush=True)
        raise SystemExit(result.returncode)
    row.update(object=rel(obj), object_sha256=sha(obj))
    for name in shlex.split(dep.read_text().replace('\\\n', ' ').partition(':')[2]):
        p = Path(name).resolve()
        record['sources' if p.is_relative_to(root) else 'compiler_headers'][rel(p) if p.is_relative_to(root) else str(p)] = sha(p)
    objects.append(obj)
    save()
    print('COMPILED', source.name, flush=True)

raw = folder / 'raw-libc++abi.dylib'
library = folder / 'libraries/libc++abi.dylib'
command = ['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
           '-install_name', '/usr/lib/libc++abi.dylib', '-compatibility_version', '1.0.0',
           '-current_version', '1.0.0', '-no_fixup_chains', '-no_adhoc_codesign',
           '-syslibroot', str(guest), '-L', str(guest / 'usr/lib'), '-lSystem',
           *map(str, objects), '-o', str(raw)]
log = folder / 'link.log'
with log.open('w') as out:
    result = subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
record.update(link_command=command, link_returncode=result.returncode,
              link_log=rel(log), link_log_sha256=sha(log))
if result.returncode:
    save()
    print(log.read_text()[-3000:], flush=True)
    raise SystemExit(result.returncode)
data, normalization = runpy.run_path(str(root / 'scripts/normalize-macho-weak-bind.py'))['normalize'](raw.read_bytes())
library.write_bytes(data)


def exports(path):
    text = subprocess.check_output(['llvm-nm-19', '--arch=x86_64', '--defined-only', '--extern-only', str(path)], text=True)
    return {line.split()[-1] for line in text.splitlines() if line.strip()}


before, after = exports(baseline), exports(library)
record.update(linked=True, library=rel(library), library_sha256=sha(library),
              baseline_exports=len(before), direct_exports=len(after),
              missing_baseline_exports=sorted(before - after), added_exports=sorted(after - before),
              primary_initializer_exported='___cxa_init_primary_exception' in after,
              weak_bind_normalization=normalization)
save()
print('BUILD_REPORT', rel(report_path), 'missing', len(before-after), 'added', len(after-before))
assert not before-after and record['primary_initializer_exported'], 'Existing ABI exports must be retained'
