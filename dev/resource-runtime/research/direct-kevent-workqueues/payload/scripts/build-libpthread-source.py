#!/usr/bin/env python3
"""Build all Darling x86_64 pthread sources into a private runtime variant."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse, fcntl, hashlib, json, re, shutil, subprocess

root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output-dir', required=True)
p.add_argument('--variant-base', required=True)
p.add_argument('--report', required=True)
a = p.parse_args()
build = (root / a.output_dir).resolve()
assert build.is_relative_to(root / 'runtime') and not build.exists()
build.mkdir()
(build / 'include').mkdir()
(build / 'include/System').symlink_to(root / 'vendor/darling/src/external/xnu/osfmk', target_is_directory=True)
darling = root / 'vendor/darling'
repo = darling / 'src/external/libpthread'
src = repo / 'src'
sdk = darling / 'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource = Path(subprocess.check_output(['clang-19', '-print-resource-dir'], text=True).strip())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
cmake = (src / 'CMakeLists.txt').read_text()
common = re.search(r'set\(pthread_common_sources\s+(.*?)\)', cmake, re.S)[1]
common = re.sub(r'#[^\n]*', '', common).split()
extra = re.search(r'set\(pthread_sources\s+\$\{pthread_common_sources\}\s+(.*?)\)', cmake, re.S)[1].split()
sources = [src / name for name in common + extra]
assert len(sources) == 13 and all(path.is_file() for path in sources)
defs = ['PLATFORM_MacOSX', 'DARLING', 'PRIVATE', '__LIBC__', '__DARWIN_UNIX03=1', '__DARWIN_64_BIT_INO_T=1',
        '__DARWIN_NON_CANCELABLE=1', '__DARWIN_VERS_1050=1', '_FORTIFY_SOURCE=0',
        '__PTHREAD_BUILDING_PTHREAD__=1', '__PTHREAD_EXPOSE_INTERNALS__', '__POSIX_LIB__']
includes = [build / 'include', src, src / 'resolver', repo / 'private', repo, repo / 'include',
            sdk / 'usr/include', resource / 'include', darling / 'src/external/xnu/EXTERNAL_HEADERS',
            darling / 'src/external/xnu/osfmk']
flags = ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-nostdinc',
         '-std=gnu11', '-w', '-O2', '-fPIC', '-fblocks', '-fno-stack-protector',
         '-Wno-error=int-conversion', '-Wno-error=incompatible-pointer-types',
         '-Wno-error=implicit-function-declaration', *['-D' + d for d in defs],
         *['-I' + str(path) for path in includes]]
objects, manifest = [], []
for index, path in enumerate(sources):
    obj = build / (str(index) + '-' + path.stem + '.o')
    aliases = re.search(r'SET_SOURCE_FILES_PROPERTIES\(' + re.escape(path.name) + r' PROPERTIES COMPILE_FLAGS "(.*?)"\)', cmake)
    aliases = re.findall(r'-D\S+', aliases[1]) if aliases else []
    command = flags + aliases + ['-c', str(path), '-o', str(obj)]
    objects.append(obj)
    manifest.append(dict(source=str(path.relative_to(root)), sha256=sha(path), command=command))

def compile_one(item):
    i, entry = item
    r = subprocess.run(entry['command'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (build / (str(i) + '.log')).write_text(r.stdout)
    if r.returncode:
        raise RuntimeError(entry['source'] + '\n' + r.stdout[-6000:])

with ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(compile_one, enumerate(manifest)))
print('Compiled all', len(sources), 'pthread translation units', flush=True)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
filelist = build / 'objects.filelist'
filelist.write_text(''.join(guest(obj) + '\n' for obj in objects))
output = build / 'libsystem_pthread.dylib'
baseline = root / a.variant_base / 'usr/lib/system/libsystem_pthread.dylib'
ld = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld'
sysroot = '/Volumes/SystemRoot/usr/libexec/darling'
link = [str(root / 'bin/darling'), 'shell', ld, '-dylib', '-arch', 'x86_64',
        '-platform_version', 'macos', '11', '11', '-no_compact_unwind',
        '-install_name', '/usr/lib/system/libsystem_pthread.dylib', '-compatibility_version', '1',
        '-syslibroot', sysroot, '-L', sysroot + '/usr/lib/system', '-lsystem_platform',
        '-lsystem_kernel', '-ldyld', '-lsystem_c', '-alias_list', guest(repo / 'xcodescripts/pthread.aliases'),
        '-filelist', guest(filelist), '-o', guest(output)]
subprocess.run(link, check=True, timeout=120)
def exports(path):
    t = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
    return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)', t, re.M))
old, new = exports(baseline), exports(output)
missing = old - new
if missing:
    raise ValueError('Missing existing pthread exports: ' + repr(sorted(missing)))
assert '__pthread_workqueue_add_cooperativethreads' in new
variant = build / 'darling-root'
with (root / 'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    subprocess.run(['cp', '-a', '--reflink=auto', str(root / a.variant_base), str(variant)], check=True)
    shutil.copy2(output, variant / 'usr/lib/system/libsystem_pthread.dylib')
report = dict(full_libpthread_source_build=True, complete_source_files=len(sources), sources=manifest,
              source_headers={str(path.relative_to(root)): sha(path) for path in sorted(repo.rglob('*.h'))},
              link_command=link, baseline=str(baseline.relative_to(root)), baseline_sha256=sha(baseline),
              binary=str(output.relative_to(root)), binary_sha256=sha(output),
              baseline_exports_preserved=len(old), exports=len(new), variant_root=str(variant.relative_to(root)),
              files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), src / 'CMakeLists.txt',
                     repo / 'xcodescripts/pthread.aliases']}, runtime_execution_verified=False, full_goal_complete=False)
(root / a.report).write_text(json.dumps(report, indent=2) + '\n')
print('Built source pthread:', output, flush=True)
