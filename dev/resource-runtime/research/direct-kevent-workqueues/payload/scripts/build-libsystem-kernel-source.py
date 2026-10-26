#!/usr/bin/env python3
"""Build Darling's complete x86_64 libsystem_kernel into a private variant.

Source lists and MIG interfaces come from the upstream CMake files. No binary
interposition is used for this component. Publication never changes the default
runtime, and requires the same coherent libxpc/launchd directory as the tests.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import fcntl
import argparse
import hashlib
import json
import re
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', default='runtime/libsystem-kernel-source')
parser.add_argument('--variant-base', default='runtime/launchd-source/darling-root')
parser.add_argument('--report', default='artifacts/libsystem-kernel-source.json')
parser.add_argument('--direct-kevent-workqueue', action='store_true',
                    help='Enable the experimental paired pthread event pump / direct event workqueue variant')
parser.add_argument('--skywalk-client', action='store_true',
                    help='Include the complete source channel client with explicit unsupported kernel transport')
parser.add_argument('--darwin-release', default='20.6.0',
                    help='Virtual compatibility target release; Linux host and API coverage are unchanged')
parser.add_argument('--source-manifest', type=Path,
                    help='Also accept the exact saved fork revisions whose base matches the locked source configuration')
parser.add_argument('--test-source-override', action='append', default=[], metavar='ORIGINAL=FIXTURE',
                    help='Test-only replacement of one translation unit; recorded in the build manifest')
args = parser.parse_args()
assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', args.darwin_release)
kernel_version = 'Darwin Kernel Version 20.6.0' if args.darwin_release == '20.6.0' else 'Darling compatibility kernel ' + args.darwin_release
darling = root / 'vendor/darling'
xnu = darling / 'src/external/xnu'
kernel = xnu / 'darling/src/libsystem_kernel'
emulation = kernel / 'emulation'
syscall = xnu / 'libsyscall'
# Duplicate designated indices silently select the last handler in C.
from collections import Counter
indices = Counter(re.findall(r'^\s*\[(\d+)\]\s*=', (emulation / 'src/xnu_syscall/bsd/bsd_syscall_table.c').read_text(), re.M))
assert not any(count > 1 for count in indices.values()), {index: count for index, count in indices.items() if count > 1}

server_build = root / 'runtime/darlingserver-source-build'
build = (root / args.output_dir).resolve()
assert build.is_relative_to(root / 'runtime')
generated = build / 'generated'
generated.mkdir(parents=True, exist_ok=True)
sdk = darling / 'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource = Path(subprocess.check_output(['clang-19', '-print-resource-dir'], text=True).strip())
guest = root / 'runtime/rootfs/usr/libexec/darling'
baseline = guest / 'usr/lib/system/libsystem_kernel.dylib'
config_path = root / 'config/libsystem-kernel-source-build.json'
config = json.loads(config_path.read_text())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source_heads = {}
saved_sources = {item['path']: item for item in json.loads(args.source_manifest.read_text())['repositories']} if args.source_manifest else {}
for relative, commit in config['source_repositories'].items():
    actual = subprocess.check_output(['git', '-C', str(root / relative), 'rev-parse', 'HEAD'], text=True).strip()
    saved = saved_sources.get(relative, {})
    if actual != commit and not (saved.get('base_commit') == commit and saved.get('commit') == actual):
        raise ValueError('Changed source revision: ' + relative)
    source_heads[relative] = actual
if digest(baseline) != config['baseline_sha256']:
    raise ValueError('Changed baseline libsystem_kernel')


def cmake_sets(path, substitutions):
    text = re.sub(r'#[^\n]*', '', path.read_text())
    values = dict(substitutions)
    for name, value in re.findall(r'set\((\w+)\s+([^)]*)\)', text, re.S):
        if not name.endswith('_sources') and name not in ('LIBSYSCALL_MIGS', 'LIBSYSCALL_MIGS_INTERNAL'):
            continue
        def expand(match):
            key = match[1]
            if key not in values:
                raise ValueError('Unknown source-list variable: ' + key)
            item = values[key]
            return ' '.join(item) if isinstance(item, list) else str(item)
        value = re.sub(r'\$\{([^}]+)\}', expand, value)
        values[name] = [word.strip('"') for word in value.split() if word != '""']
    return values


sys_sets = cmake_sets(syscall / 'CMakeLists.txt', {})
emu_sets = cmake_sets(emulation / 'CMakeLists.txt', {
    'CMAKE_CURRENT_BINARY_DIR': str(generated / 'emulation'),
    'CMAKE_BINARY_DIR': str(server_build),
})
# The standalone server has a different binary directory layout than the full
# Darling build. Only this generated input's location changes, not its content.
emu_sources = [Path(p) if p.startswith('/') else emulation / p for p in emu_sets['emulation_sources']]
emu_sources = [server_build / 'darlingserver/src/rpc.c' if str(p).endswith('/src/external/darlingserver/src/rpc.c') else p for p in emu_sources]
definitions = ['-DDARLING', '-DPRIVATE=1', '-DHAVE_STDINT_H=1', '-D__DARWIN_UNIX03',
               '-D_DARWIN_C_SOURCE', '-D_POSIX_C_SOURCE', '-DDARWIN', '-DTARGET_OS_MAC=1', '-DPLATFORM_MacOSX',
               '-D__DARWIN_C_LEVEL=20150101', '-D__XNU_PRIVATE_EXTERN=', '-DIOKIT_ALL_IPC=1', '-DIOKIT=1']
syscall_includes = [syscall / p for p in ('wrappers', 'mach', 'os', 'wrappers/libproc', 'wrappers/spawn', 'wrappers/string')]
includes = [generated / 'libsyscall', *syscall_includes,
            kernel, server_build / 'darlingserver/include', root / 'vendor/darlingserver/include',
            darling / 'src/libsimple/include', server_build / 'src/startup', generated / 'emulation/src/other',
            generated / 'include', server_build / 'include', darling / 'src/include',
            sdk / 'usr/include', resource / 'include', xnu / 'EXTERNAL_HEADERS', xnu / 'osfmk']
# The full Darling build exposes private XNU headers beneath System/. Keep this
# alias local to the build rather than modifying the source SDK.
(generated / 'include').mkdir(exist_ok=True)
system_headers = generated / 'include/System'
if not system_headers.exists():
    system_headers.symlink_to(xnu / 'osfmk', target_is_directory=True)
emulation_headers = generated / 'include/darling/emulation'
emulation_headers.parent.mkdir(exist_ok=True)
if not emulation_headers.exists():
    emulation_headers.symlink_to(emulation / 'include', target_is_directory=True)
common = ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-nostdinc',
          *['-I' + str(p) for p in includes], '-F', str(sdk / 'System/Library/Frameworks'),
          '-I' + str(darling / 'framework-include'), '-I' + str(darling / 'framework-private-include'),
          *definitions, '-fblocks', '-ffreestanding',
          '-fPIC', '-msse', '-msse2', '-msse3', '-fno-common', '-fno-stack-protector', '-O2', '-w',
          '-Wno-error=int-conversion', '-Wno-error=incompatible-pointer-types', '-Wno-error=implicit-function-declaration']
mig = server_build / 'build-mig'


def generate_mig(source, prefix, interface=False):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    command = [str(mig), '-arch', 'x86_64', '-target', 'x86_64-apple-macos11',
               '-isysroot', str(sdk), '-nostdinc', *['-I' + str(p) for p in includes], *definitions,
               *(['-DLIBSYSCALL_INTERFACE=1'] if interface else []),
               '-user', str(prefix) + 'User.c', '-header', str(prefix) + '.h',
               '-server', str(prefix) + 'Server.c', '-sheader', str(prefix) + 'Server.h', str(source)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


mig_objects = []
for name in sys_sets['LIBSYSCALL_MIGS'] + ['mach/servers/netname']:
    print('MIG interface', name, flush=True)
    generate_mig(syscall / (name + '.defs'), generated / 'libsyscall' / name, interface=True)
for name in sys_sets['LIBSYSCALL_MIGS']:
    prefix = generated / 'libsyscall' / (name + '-x86_64-')
    generate_mig(syscall / (name + '.defs'), prefix)
    mig_objects.append(Path(str(prefix) + 'User.c'))
    if name == 'mach/exc':
        mig_objects.append(Path(str(prefix) + 'Server.c'))
for name in sys_sets['LIBSYSCALL_MIGS_INTERNAL']:
    generate_mig(syscall / (name + '.defs'), generated / 'libsyscall' / (name + '_internal'))
for name in ('mach_exc', 'exc'):
    generate_mig(emulation / 'src/other/signal' / (name + '.defs'), generated / 'emulation/src/other/signal' / name)

sys_inputs = list(dict.fromkeys(syscall / p for p in sys_sets['syscall_sources'] + sys_sets['syscall_dynamic_sources']))
skywalk = syscall / 'wrappers/skywalk'
if args.skywalk_client:
    sys_inputs.extend(syscall / name for name in sys_sets['skywalk_client_sources'])
sys_sources = [p for p in sys_inputs if p.suffix in ('.c', '.S', '.s')]
sources = [(p, 'skywalk' if p.is_relative_to(skywalk) else 'syscall') for p in [*sys_sources, *mig_objects]] + [(p, 'emulation') for p in emu_sources]
sources.append((darling / 'src/libsimple/src/lock.c', 'libsimple'))
if args.direct_kevent_workqueue:
    # Simulator libSystem is Apple's original image and does not contain
    # Darling's host libkqueue objects. Own the real backend here as well.
    queue = darling / 'src/external/libkqueue'
    queue_inputs = [queue / 'src/posix/platform.c']
    queue_inputs += [queue / ('src/linux/' + name + '.c') for name in
        ['platform', 'signal', 'socket', 'timer', 'user', 'vnode', 'write', 'read', 'proc', 'machport', 'fs']]
    queue_inputs += [queue / ('src/common/' + name + '.c') for name in ['filter', 'knote', 'map', 'kevent', 'kqueue']]
    queue_inputs += sorted((queue / 'src/darling').glob('*.c'))
    queue_inputs = [path for path in queue_inputs if path.is_file()]
    assert len(queue_inputs) == 17
    sources += [(path, 'kqueue') for path in queue_inputs]
    queue_alias = generated / 'kqueue/include/System'
    queue_alias.mkdir(parents=True)
    for directory in [xnu / 'osfmk', xnu / 'bsd']:
        for path in directory.iterdir():
            if path.is_dir() and not (queue_alias/path.name).exists():
                (queue_alias/path.name).symlink_to(path, target_is_directory=True)

if len(sources) < 700:
    raise ValueError('Incomplete libsystem_kernel source list: ' + str(len(sources)))
test_overrides = {}
for replacement in args.test_source_override:
    original, fixture = replacement.split('=', 1)
    original, fixture = (root / original).resolve(), (root / fixture).resolve()
    assert original in {p.resolve() for p, _ in sources}, original
    assert fixture.is_relative_to(root / 'fixtures') and fixture.is_file(), fixture
    assert original not in test_overrides, original
    test_overrides[original] = fixture
manifest = []
objects = []
for index, (path, group) in enumerate(sources):
    production_path = path
    path = test_overrides.get(path.resolve(), path)
    if not path.is_file():
        raise FileNotFoundError(path)
    obj = build / 'objects' / (str(index) + '-' + path.stem + '.o')
    obj.parent.mkdir(exist_ok=True)
    objects.append(obj)
    command = [*common]
    if group == 'syscall':
        command += ['-std=c99', '-include', str(syscall / 'nolegacy.h')]
        if path.is_relative_to(syscall) and str(path.relative_to(syscall)) in sys_sets['syscall_legacy_sources']:
            command += ['-U_DARWIN_C_SOURCE', '-U_POSIX_C_SOURCE', '-U__DARWIN_UNIX03', '-D__DARWIN_UNIX03=0', '-U__DARWIN_C_LEVEL']
        elif path.name == 'select-pre1050.c':
            command += ['-U_DARWIN_C_SOURCE', '-DSYSCALL_PRE1050']
        elif path.name in ('select.c', 'select-cancel.c') and '/cancelable/' in str(path):
            command += ['-U_DARWIN_C_SOURCE']
    elif group == 'skywalk':
        modern_sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
        command = ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(modern_sdk), '-nostdinc',
                   '-I' + str(skywalk / 'include'), '-I' + str(modern_sdk / 'usr/include'),
                   '-I' + str(resource / 'include'), '-I' + str(sdk / 'usr/include'),
                   '-I' + str(xnu / 'EXTERNAL_HEADERS'), '-I' + str(xnu / 'osfmk'),
                   '-DDARLING', '-DPRIVATE', '-DPLATFORM_MacOSX', '-DLIBSYSCALL_INTERFACE=1',
                   '-D__counted_by(x)=', '-include', str(skywalk / 'skywalk_build_compat.h'),
                   '-ffreestanding', '-fblocks', '-fPIC', '-fno-stack-protector', '-O2', '-w',
                   '-Wno-error=int-conversion']
        if path.suffix == '.c':
            command += ['-std=gnu11']
    elif group == 'kqueue':
        queue_include = [queue_alias.parent, queue, queue / 'src/common', queue / 'include', xnu,
            server_build / 'include', server_build / 'darlingserver/include', root / 'vendor/darlingserver/include',
            emulation / 'include/linux_premigration/ext', sdk / 'usr/include', resource / 'include', xnu / 'EXTERNAL_HEADERS']
        modern_sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
        command = ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-nostdinc',
            *['-I' + str(path) for path in queue_include], '-idirafter', str(modern_sdk / 'usr/include'),
            '-DPLATFORM_MacOSX=1', '-DDARLING=1', '-DHAVE_STDINT_H=1', '-DPRIVATE=1', '-fblocks', '-fPIC',
            '-O0', '-g', '-w', '-Wno-error=incompatible-pointer-types', '-Wno-error=int-conversion',
            '-Wno-error=implicit-function-declaration', '-include', 'stdint.h', '-include', str(sdk / 'usr/include/sys/event.h'),
            '-D__linux__', '-D_DARWIN_C_SOURCE=1', '-D_XOPEN_SOURCE=600', '-DHAVE_SYS_EVENTFD_H=1',
            '-DHAVE_SYS_SIGNALFD_H=1', '-DHAVE_SYS_TIMERFD_H=1', '-std=c99', '-fvisibility=hidden']
    elif group == 'emulation':
        # emulation is a sibling of libsyscall, not its child. In particular,
        # libsyscall/mach/string.h is a deliberately restricted MIG-only header
        # and must never shadow libc's string.h in the syscall implementation.
        command = [p for p in command if p not in {'-I' + str(d) for d in syscall_includes}]
        command += ['-std=gnu99', '-fvisibility=hidden', '-fno-builtin', '-DBSDTHREAD_WRAP_LINUX_PTHREAD',
                    '-DEMULATED_SYSNAME="Darwin"', '-DEMULATED_RELEASE="' + args.darwin_release + '"',
                    '-DEMULATED_VERSION="' + kernel_version + '"', '-DEMULATED_OSVERSION="20G1120"',
                    '-DEMULATED_OSPRODUCTVERSION="26.2"']
        if args.direct_kevent_workqueue:
            command += ['-DDARLING_DIRECT_KEVENT_WORKQUEUE=1']
        if path == server_build / 'darlingserver/src/rpc.c':
            command += ['-include', str(emulation / 'include/linux_premigration/resources/dserver-rpc-defs.h')]
        if path.name == 'execve.c':
            command += ['-Werror=implicit-function-declaration']
    else:
        command += ['-DLIBSIMPLE_DARLING=1']
    command += ['-c', str(path), '-o', str(obj)]
    manifest.append(dict(source=str(path.relative_to(root)), sha256=digest(path), group=group, command=command))
    if path != production_path:
        manifest[-1].update(test_override_for=str(production_path.relative_to(root)),
                            production_source_sha256=digest(production_path))


def compile_one(item):
    index, entry = item
    result = subprocess.run(entry['command'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (build / 'objects' / (str(index) + '.log')).write_text(result.stdout)
    if result.returncode:
        print('FAILED ' + entry['source'] + '\n' + result.stdout, flush=True)
        raise RuntimeError('Source compilation failed: ' + entry['source'])
    if index % 75 == 0:
        print('Compiled', index + 1, '/', len(manifest), flush=True)


with ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(compile_one, enumerate(manifest)))
output = build / 'libsystem_kernel.dylib'
pending = output.with_suffix('.dylib.pending')
guest_path = lambda p: '/Volumes/SystemRoot/workspace/' + str(p.relative_to(root))
filelist = build / 'objects.filelist'
filelist.write_text(''.join(guest_path(p) + '\n' for p in objects))
ld = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/ld'
guest_sdk = '/Volumes/SystemRoot/usr/libexec/darling'
subprocess.run([str(root / 'bin/darling'), 'shell', ld, '-dylib', '-arch', 'x86_64',
                '-platform_version', 'macos', '11', '11', '-bind_at_load', '-no_compact_unwind',
                '-install_name', '/usr/lib/system/libsystem_kernel.dylib', '-compatibility_version', '1.0.0',
                '-syslibroot', guest_sdk, '-L', guest_sdk + '/usr/lib/system',
                '-lsystem_c', '-lcompiler_rt', '-ldyld',
                *(['-lsystem_pthread', '-lsystem_malloc', '-lsystem_platform'] if args.direct_kevent_workqueue else []), '-filelist', guest_path(filelist), '-o', guest_path(pending)],
               check=True, timeout=120)
def exports(path):
    listing = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
    return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)', listing, re.M))
# Upstream kernel emulation exported two empty weak libplatform functions.
# They must be absent so re-export traversal reaches the real libplatform ABI.
removed_empty_lock_stubs = {'_os_unfair_lock_lock', '_os_unfair_lock_unlock'}
assert not (removed_empty_lock_stubs & exports(pending)), 'Empty public lock stubs must not return'
missing = exports(baseline) - exports(pending) - removed_empty_lock_stubs
if missing:
    raise ValueError('Missing baseline exports: ' + repr(sorted(missing)))
pending.replace(output)
variant = build / 'darling-root'
base = (root / args.variant_base).resolve()
with (root / 'runtime/session.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    pending_root = build / 'darling-root.pending'
    previous = build / 'darling-root.previous'
    for owned in (pending_root, previous):
        if owned.exists():
            shutil.rmtree(owned)
    subprocess.run(['cp', '-a', '--reflink=auto', str(base), str(pending_root)], check=True)
    shutil.copy2(output, pending_root / 'usr/lib/system/libsystem_kernel.dylib')
    if variant.exists():
        variant.replace(previous)
    pending_root.replace(variant)
    if previous.exists():
        shutil.rmtree(previous)
    if args.variant_base != 'runtime/launchd-source/darling-root':
        # One coherent variant can satisfy all later source-runtime selectors.
        for filename in ['libquarantine.dylib', 'libsystem_sandbox.dylib', 'libdyld.dylib']:
            shutil.copy2(variant / 'usr/lib/system' / filename, build / filename)
report = dict(installed=False, full_darling_rebuild=False, full_libsystem_kernel_source_build=True,
              test_only_source_overrides={str(original.relative_to(root)): str(fixture.relative_to(root)) for original, fixture in test_overrides.items()},
              runtime_execution_verified=False, complete_source_files=len(sources),
              source_configuration=config, sources=manifest, binary_sha256=digest(output),
              actual_source_repositories=source_heads,
              accepted_saved_source_manifest=str(args.source_manifest) if args.source_manifest else None,
              accepted_saved_source_manifest_sha256=digest(args.source_manifest) if args.source_manifest else None,
              source_list_headers={str(p.relative_to(root)): digest(p) for p in sys_inputs if p not in sys_sources},
              baseline_exports_preserved=len(exports(baseline) & exports(output)),
              intentionally_removed_empty_weak_exports=sorted(removed_empty_lock_stubs), source_exports=len(exports(output)),
              variant_root=str(variant.relative_to(root)),
              availability_version_override='26.2; not a claim of macOS 26 implementation')
report['metadata_source_headers'] = {str(p.relative_to(root)): digest(p) for p in [
    syscall / 'wrappers/work_interval_instance.inc',
    syscall / 'wrappers/_libkernel_init.h',
    emulation / 'include/common/tsd.h',
    emulation / 'include/xnu_syscall/bsd/impl/bsdthread/workq_kernreturn.h',
    darling / 'src/libsimple/include/libsimple/lock.h',
    emulation / 'include/xnu_syscall/bsd/helper/xattr/getattrlist_generic.c',
    emulation / 'include/xnu_syscall/bsd/helper/xattr/metadata_linux.h',
    emulation / 'include/conversion/stat/common.h',
    emulation / 'include/xnu_syscall/bsd/helper/stat/mounts.h',
    syscall / 'wrappers/statfs_ext_compat.h',
    darling / 'src/include/darling-config.h.in',
    server_build / 'include/darling-config.h']}
report['experimental_direct_kevent_workqueue'] = args.direct_kevent_workqueue
if args.direct_kevent_workqueue:
    report['embedded_source_kqueue_objects'] = len(queue_inputs)
    report['metadata_source_headers'].update({str(path.relative_to(root)): digest(path) for path in
        [queue / 'CMakeLists.txt', *sorted(queue.rglob('*.h'))]})
report['skywalk_client_enabled'] = args.skywalk_client
report['virtual_darwin_release'] = args.darwin_release
report['virtual_kernel_version'] = kernel_version
report['release_is_compatibility_target_not_native_host_or_complete_API_coverage'] = True
if args.skywalk_client:
    report['skywalk_kernel_transport_implemented'] = False
    report['metadata_source_headers'].update({str(p.relative_to(root)): digest(p) for p in [
        *sorted((skywalk / 'include').rglob('*.h')), skywalk / 'skywalk_build_compat.h',
        skywalk / 'upstream-files.json', xnu / 'bsd/dev/i386/cpu_copy_in_cksum.s']})
(root / args.report).write_text(json.dumps(report, indent=2) + '\n')
print('Built complete source libsystem_kernel:', output, flush=True)
