#!/usr/bin/env python3
"""Build all three CoreTLS CF helper units with the modern SecKey accessor."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse, hashlib, json, re, shlex, struct, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--securityd-build', required=True, help='Existing pinned private-header compilation environment')
parser.add_argument('--coretls-build', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='coretls-cfhelpers-source-', dir=root / 'runtime'))
repo = root / 'vendor/darling/src/external/coretls'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
state = json.loads(((root / args.securityd_build).parent / 'compile-state.json').read_text())
prototype = state[next(k for k in state if k.endswith('/securityd/src/main.cpp'))]['command']
flags = [x for x in prototype[1:prototype.index('-MMD')] if not x.startswith(('-std=', '-stdlib=', '-fobjc-arc', '-fobjc-weak'))]
flags += ['-std=gnu99', '-fblocks', '-Wno-deprecated-declarations', '-D__ASSERT_MACROS_DEFINE_VERSIONS_WITHOUT_UNDERSCORES=1',
          '-I' + str(repo / 'lib'), '-I' + str(repo / 'coretls_cfhelpers')]
names = ['lib/sslMemory.c', 'coretls_cfhelpers/tls_helpers_identity.c', 'coretls_cfhelpers/tls_helpers.c']

def compile_one(name):
    source = repo / name; obj = folder / (source.stem + '.o'); dep = obj.with_suffix('.d'); log = obj.with_suffix('.log')
    command = ['clang-19', *flags, '-MMD', '-MF', str(dep), '-c', str(source), '-o', str(obj)]
    with log.open('w') as stream: result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    dependencies = {}
    if result.returncode == 0:
        for value in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(value)
            if path.is_file() and path.is_relative_to(root): dependencies[str(path.relative_to(root))] = sha(path)
    return dict(source=str(source.relative_to(root)), source_sha256=sha(source), command=command,
                object=str(obj.relative_to(root)), object_sha256=sha(obj) if obj.exists() else None,
                dependencies=dependencies, status=result.returncode, log=str(log.relative_to(root)))

with ThreadPoolExecutor(max_workers=3) as pool: units = list(pool.map(compile_one, names))
(folder / 'compile.json').write_text(json.dumps(units, indent=2) + '\n')
assert all(unit['status'] == 0 for unit in units), folder
tls = json.loads((root / args.coretls_build).read_text())
assert sha(root / tls['umbrella']) == tls['umbrella_sha256']
security = root / 'runtime/resource-framework-overlay-iokitcore3/frameworks/Security.framework/Versions/A/Security'
baseline = root / 'runtime/rootfs/usr/libexec/darling/usr/lib/libcoretls_cfhelpers.dylib'
binary = folder / 'libraries/libcoretls_cfhelpers.dylib'; binary.parent.mkdir()
command = ['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
           '-syslibroot', str(root / 'runtime/rootfs/usr/libexec/darling'), '-install_name', '/usr/lib/libcoretls_cfhelpers.dylib',
           '-compatibility_version', '1', '-current_version', '167', '-no_fixup_chains', '-no_adhoc_codesign',
           *[str(root / u['object']) for u in units], str(root / tls['umbrella']), '-lSystem', '-framework',
           'CoreFoundation', str(security), '-o', str(binary)]
with (folder / 'link.log').open('w') as stream: result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
assert result.returncode == 0, folder / 'link.log'
# LLVM's linker ignores -upward_library. Restore precisely the load-command
# kind used by upstream's circular CoreTLS/Security build; payload is unchanged.
payload = bytearray(binary.read_bytes()); cursor = 32; changed = 0
for _ in range(struct.unpack_from('<I', payload, 16)[0]):
    kind, size = struct.unpack_from('<II', payload, cursor)
    if kind == 0xc:
        offset = struct.unpack_from('<I', payload, cursor + 8)[0]
        name = bytes(payload[cursor + offset:cursor + size]).split(b'\0')[0]
        if name == b'/System/Library/Frameworks/Security.framework/Versions/A/Security':
            struct.pack_into('<I', payload, cursor, 0x80000023); changed += 1
    cursor += size
assert changed == 1
binary.write_bytes(payload)
def exports(path):
    output = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
    return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)', output, re.M))
original, actual = exports(baseline), exports(binary)
assert actual == original
record = dict(full_coretls_cfhelpers_source_build=True, complete_source_files=3, units=units,
              library=str(binary.relative_to(root)), library_sha256=sha(binary),
              baseline=str(baseline.relative_to(root)), baseline_sha256=sha(baseline),
              original_exports_preserved=len(original), link_command=command, Security_load_is_upward=True,
              security_framework=str(security.relative_to(root)), security_framework_sha256=sha(security),
              coretls_build=args.coretls_build, coretls_build_sha256=sha(root / args.coretls_build),
              private_header_environment=args.securityd_build, private_header_environment_sha256=sha(root / args.securityd_build),
              driver_sha256=sha(Path(__file__)), runtime_execution_verified=False,
              completed_TLS_handshake_or_certificate_trust_verified=False)
(folder / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
print(folder.relative_to(root) / 'build.json')
