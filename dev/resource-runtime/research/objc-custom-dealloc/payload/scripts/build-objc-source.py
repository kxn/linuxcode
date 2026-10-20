#!/usr/bin/env python3
"""Build all Darling objc4 runtime sources into an isolated Intel library."""
from pathlib import Path
import argparse, fcntl, hashlib, json, re, subprocess, shlex, struct

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',default='runtime/objc-source')
parser.add_argument('--report',default='artifacts/objc-source-build.json')
args=parser.parse_args()
root = Path(__file__).resolve().parent.parent
darling = root / 'vendor/darling'
repo = darling / 'src/external/objc4'
runtime = repo / 'runtime'
commit = '1a12df76d12bfc9fdfffadb290f7742763568765'
assert subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() == commit
build = root / args.output_dir
build.mkdir(parents=True,exist_ok=True)
sdk = darling / 'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
apple = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource = Path(subprocess.check_output(['clang-19', '-print-resource-dir'], text=True).strip())
source_text = (runtime / 'CMakeLists.txt').read_text().split('set(objc_SRCS', 1)[1].split(')', 1)[0]
sources = re.findall(r'\S+\.(?:mm|S)', source_text)
assert len(sources) == 43, len(sources)
include = build / 'include'
include.mkdir(exist_ok=True)
if not (include / 'objc').exists(): (include / 'objc').symlink_to(runtime, target_is_directory=True)
system = include / 'System'
system.mkdir(exist_ok=True)
for base in [darling / 'src/external/xnu/osfmk', darling / 'src/external/xnu/bsd']:
    for path in base.iterdir():
        link = system / path.name
        if path.is_dir() and not link.exists(): link.symlink_to(path, target_is_directory=True)
# The old umbrella header was renamed; use libpthread's actual SPI declarations.
(system / 'pthread_machdep.h').write_text('#include <pthread/tsd_private.h>\n')
includes = [include, runtime, darling / 'src/duct/include', darling / 'src/external/libcxx/include',
    darling / 'src/external/libcxxabi/include', sdk / 'usr/include', resource / 'include']
flags = ['-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-nostdinc',
    *['-I' + str(p) for p in includes], '-idirafter', str(apple / 'usr/include'),
    '-DDARLING', '-DPLATFORM_MacOSX', '-D__DARWIN_UNIX03', '-D__STDC_NO_ATOMICS__',
    '-DOBJC_NO_GC', '-DOBJC_IS_DEBUG_BUILD=1', '-DTARGET_OS_IPHONE=0', '-DOS_OBJECT_USE_OBJC=0',
    '-D_LIBCPP_VISIBLE=', '-D_LIBC_NO_FEATURE_VERIFICATION', '-fPIC', '-fblocks', '-O2',
    '-fno-delete-null-pointer-checks', '-fstrict-aliasing', '-Wno-nullability-completeness',
    '-Wno-deprecated-declarations', '-Wno-deprecated-objc-isa-usage', '-Wno-invalid-noreturn',
    '-Wno-unused-command-line-argument', '-Wno-macro-redefined', '-Wno-availability']
objects = []
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for index, relative in enumerate(sources):
    source = runtime / relative
    obj = build / (str(index) + '-' + source.stem + '.o')
    objects.append(obj)
    cxx = source.suffix == '.mm'
    command = ['clang++-19' if cxx else 'clang-19', *flags,
        *(['-nostdinc++', '-std=gnu++14', '-fno-rtti', '-fno-exceptions', '-fobjc-legacy-dispatch',
            '-fvisibility-inlines-hidden', '-Wno-c++11-narrowing', '-Wno-invalid-offsetof', '-Wno-cast-of-sel-type'] if cxx else []),
        '-MD', '-MF', str(obj.with_suffix('.d')), '-c', str(source), '-o', str(obj)]
    state = obj.with_suffix('.inputs.json')
    if state.exists():
        old_inputs = json.loads(state.read_text())
        if old_inputs['command'] == command and obj.exists() and digest(obj) == old_inputs['object_sha256'] and all(Path(p).exists() and digest(Path(p)) == sha for p, sha in old_inputs['inputs'].items()):
            print('Reuse verified object', relative, flush=True)
            continue
    print('Compile', relative, flush=True)
    subprocess.run(command, check=True)
    dependencies = shlex.split(obj.with_suffix('.d').read_text().split(':', 1)[1].replace('\\\n', ' '))
    state.write_text(json.dumps(dict(command=command, object_sha256=digest(obj), inputs={p: digest(Path(p)) for p in dependencies}), indent=2) + '\n')
guest = '/Volumes/SystemRoot/workspace/'
guestpath = lambda p: guest + str(p.relative_to(root))
baseguest = '/Volumes/SystemRoot/usr/libexec/darling'
output = build / 'libobjc.A.dylib'
pending = output.with_suffix('.pending')
siblings = ['system_c', 'system_malloc', 'dyld', 'system_blocks', 'unwind', 'system_m',
    'macho', 'system_platform', 'system_kernel', 'system_pthread', 'compiler_rt', 'dispatch']
command = ['timeout', '-k', '5', '60', 'bin/darling', 'shell',
    '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld-classic',
    '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11.0', '11.0',
    '-install_name', '/usr/lib/libobjc.A.dylib', '-compatibility_version', '1.0', '-current_version', '228.0',
    '-syslibroot', baseguest, '-L', baseguest + '/usr/lib', '-lc++', '-lc++abi',
    *[v for name in siblings for v in ['-upward_library', baseguest + '/usr/lib/system/lib' + name + '.dylib']],
    '-sectalign', '__DATA', '__objc_data', '0x1000', '-interposable_list', guestpath(repo / 'interposable.txt'),
    '-rename_section', '__DATA', '__mod_init_func', '__DATA', '__objc_init_func',
    '-unexported_symbols_list', guestpath(repo / 'unexported_symbols'),
    *[guestpath(p) for p in objects], '-o', guestpath(pending)]
subprocess.run(command, cwd=root, check=True)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
exports = lambda p: set(re.findall(r'^(?:0x[\da-fA-F]+|\[re-export\])\s+(\S+)',
    subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(p)], text=True), re.M))
old = exports(root / 'runtime/rootfs/usr/libexec/darling/usr/lib/libobjc.A.dylib')
new = exports(pending)
assert not old - new, sorted(old - new)
data = pending.read_bytes()
at = 32
initializer_sections = []
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    cmd, size = struct.unpack_from('<II', data, at)
    if cmd == 0x19:
        for i in range(struct.unpack_from('<I', data, at + 64)[0]):
            section = at + 72 + 80 * i
            name = data[section:section + 16].split(b'\0')[0].decode()
            length = struct.unpack_from('<Q', data, section + 40)[0]
            flags = struct.unpack_from('<I', data, section + 64)[0]
            if 'init_func' in name:
                initializer_sections.append(dict(name=name, size=length, flags=flags))
    at += size
assert any(s['name'] == '__objc_init_func' and s['size'] > 0 and s['size'] % 8 == 0 for s in initializer_sections)
assert not any(s['name'] == '__mod_init_func' and s['size'] for s in initializer_sections)
with (root/'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    pending.replace(output)
report = dict(installed=False, full_objc_source_build=True, source_commit=commit, complete_source_files=len(sources),
    source_files={s: digest(runtime / s) for s in sources}, library=str(output.relative_to(root)), library_sha256=digest(output),
    original_export_count=len(old), source_export_count=len(new), missing_original_exports=sorted(old - new),
    build_inputs={str(p.relative_to(root)): digest(p) for p in [runtime / 'CMakeLists.txt', repo / 'unexported_symbols',
        runtime / 'objc-private.h', runtime / 'objc-object.h', runtime / 'objc.h', root / 'scripts/build-objc-source.py']},
    compile_input_reports={str(p.with_suffix('.inputs.json').relative_to(root)): digest(p.with_suffix('.inputs.json')) for p in objects},
    initializer_sections=initializer_sections,
    original_runtime_sha256=digest(root / 'runtime/rootfs/usr/libexec/darling/usr/lib/libobjc.A.dylib'),
    command=command, runtime_execution_verified=False, full_xcode_build_ready=False, signing_ready=False)
(root / args.report).write_text(json.dumps(report, indent=2) + '\n')
print('Built complete isolated source objc4 runtime')
