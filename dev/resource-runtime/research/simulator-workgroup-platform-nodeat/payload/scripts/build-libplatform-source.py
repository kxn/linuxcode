#!/usr/bin/env python3
"""Build the complete Darling x86_64 platform library into a private root."""
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
darling = root / 'vendor/darling'
repo = darling / 'src/external/libplatform'
sdk = darling / 'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource = Path(subprocess.check_output(['clang-19', '-print-resource-dir'], text=True).strip())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
cmake = (repo / 'CMakeLists.txt').read_text()
def source_set(name):
    value = re.search(r'set\(' + name + r'\s+(.*?)\)', cmake, re.S)[1]
    return re.sub(r'#[^\n]*', '', value).split()
sources = [repo / name for name in source_set('platform_sources') + source_set('platform_64bit_sources')]
assert re.search(r'SOURCES \$\{platform_sources\} src/string/generic/memcmp_zero.c', cmake)
sources.append(repo / 'src/string/generic/memcmp_zero.c')
assert len(sources) >= 45 and all(path.is_file() for path in sources)
headers = build / 'include'
headers.mkdir()
(headers / 'System').symlink_to(darling / 'src/external/xnu/osfmk', target_is_directory=True)
includes = [headers, *[repo / n for n in ['include', 'private', 'internal', 'os/resolver']],
            sdk / 'usr/include', resource / 'include', darling / 'src/external/xnu/EXTERNAL_HEADERS',
            darling / 'src/external/xnu/osfmk']
flags = ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-nostdinc',
         '-O2', '-fPIC', '-fblocks', '-fno-stack-protector', '-fno-builtin', '-fno-common', '-w',
         '-Wno-error=int-conversion', '-Wno-error=incompatible-pointer-types',
         '-Wno-error=implicit-function-declaration', '-DDARLING', '-DPRIVATE', '-DPLATFORM_MacOSX',
         '-D_FORTIFY_SOURCE=0', *['-I' + str(path) for path in includes]]
objects, manifest = [], []
for index, path in enumerate(sources):
    obj = build / (str(index) + '-' + path.stem + '.o')
    command = flags + ['-c', str(path), '-o', str(obj)]
    objects.append(obj)
    manifest.append(dict(source=str(path.relative_to(root)), sha256=sha(path), command=command))
def compile_one(item):
    i, entry = item
    r = subprocess.run(entry['command'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (build / (str(i) + '.log')).write_text(r.stdout)
    if r.returncode: raise RuntimeError(entry['source'] + '\n' + r.stdout[-6000:])
with ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(compile_one, enumerate(manifest)))
print('Compiled all', len(sources), 'platform translation units', flush=True)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
filelist = build / 'objects.filelist'
filelist.write_text(''.join(guest(obj) + '\n' for obj in objects))
output = build / 'libsystem_platform.dylib'
baseline = root / a.variant_base / 'usr/lib/system/libsystem_platform.dylib'
ld = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld'
sysroot = '/Volumes/SystemRoot/usr/libexec/darling'
link = [str(root / 'bin/darling'), 'shell', ld, '-dylib', '-arch', 'x86_64',
        '-platform_version', 'macos', '11', '11', '-no_compact_unwind', '-bind_at_load',
        '-install_name', '/usr/lib/system/libsystem_platform.dylib', '-compatibility_version', '1',
        '-syslibroot', sysroot, '-L', sysroot + '/usr/lib/system', '-lsystem_kernel', '-lcompiler_rt',
        '-ldyld', '-lsystem_c', '-alias_list', guest(repo / 'xcodeconfig/libplatform.aliases'),
        '-filelist', guest(filelist), '-o', guest(output)]
subprocess.run(link, check=True, timeout=120)
def exports(path):
    text = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
    return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)', text, re.M))
old, new = exports(baseline), exports(output)
missing = old - new
if missing: raise ValueError('Missing platform exports: ' + repr(sorted(missing)))
assert '__platform_memcmp_zero_aligned8' in new
variant = build / 'darling-root'
with (root / 'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    subprocess.run(['cp', '-a', '--reflink=auto', str(root / a.variant_base), str(variant)], check=True)
    shutil.copy2(output, variant / 'usr/lib/system/libsystem_platform.dylib')
report = dict(full_libplatform_source_build=True, complete_source_files=len(sources), sources=manifest,
              source_headers={str(path.relative_to(root)): sha(path) for path in sorted(repo.rglob('*.h'))},
              link_command=link, baseline=str(baseline.relative_to(root)), baseline_sha256=sha(baseline),
              binary=str(output.relative_to(root)), binary_sha256=sha(output),
              baseline_exports_preserved=len(old), exports=len(new), variant_root=str(variant.relative_to(root)),
              files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), repo / 'CMakeLists.txt',
                     repo / 'xcodeconfig/libplatform.aliases']}, runtime_execution_verified=False, full_goal_complete=False)
(root / a.report).write_text(json.dumps(report, indent=2) + '\n')
print('Built source platform:', output, flush=True)
