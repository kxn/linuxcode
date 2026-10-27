#!/usr/bin/env python3
"""Build the complete pinned Darling resolver source with file-config fixes."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse, hashlib, json, re, shlex, struct, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--header-environment', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='libresolv-source-', dir=root / 'runtime'))
repo = root / 'vendor/darling/src/external/libresolv'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
state = json.loads(((root / args.header_environment).parent / 'compile-state.json').read_text())
prototype = state[next(k for k in state if k.endswith('/securityd/src/main.cpp'))]['command']
flags = [x for x in prototype[1:prototype.index('-MMD')] if not x.startswith(('-std=', '-stdlib=', '-fobjc-arc', '-fobjc-weak'))]
flags += ['-std=gnu99', '-fblocks', '-DUSE__RES_9', '-Wno-deprecated-declarations',
          '-I' + str(repo), '-I' + str(root / 'vendor/darling/src/external/configd/dnsinfo')]
cmake = (repo / 'CMakeLists.txt').read_text()
names = re.search(r'set\(resolv_sources\s+(.*?)\)', cmake, re.S)[1].split()
assert names and all((repo / name).is_file() for name in names)
print('BUILDING', folder.relative_to(root), len(names), flush=True)

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

with ThreadPoolExecutor(max_workers=8) as pool: units = list(pool.map(compile_one, names))
(folder / 'compile.json').write_text(json.dumps(units, indent=2) + '\n')
failed = [u for u in units if u['status'] != 0]
if failed:
    for unit in failed:
        errors = [x for x in (root / unit['log']).read_text().splitlines() if 'error:' in x]
        print(unit['source'], '\n'.join(errors[:3]))
    raise SystemExit(1)
guest = root / 'runtime/rootfs/usr/libexec/darling'
baseline = guest / 'usr/lib/libresolv.9.dylib'
payload = baseline.read_bytes(); offset = 0
if payload[:4] == b'\xca\xfe\xba\xbe':
    arches = [struct.unpack_from('>5I', payload, 8 + 20 * i) for i in range(struct.unpack_from('>I', payload, 4)[0])]
    offset = next(a[2] for a in arches if a[0] == 0x1000007)
cursor = offset + 32; dependencies = []
for _ in range(struct.unpack_from('<I', payload, offset + 16)[0]):
    kind, size = struct.unpack_from('<II', payload, cursor)
    if kind == 0xc:
        start = cursor + struct.unpack_from('<I', payload, cursor + 8)[0]
        dependencies.append(payload[start:cursor + size].split(b'\0')[0].decode())
    cursor += size
binary = folder / 'libraries/libresolv.9.dylib'; binary.parent.mkdir()
command = ['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
           '-syslibroot', str(guest), '-install_name', '/usr/lib/libresolv.9.dylib', '-compatibility_version', '1',
           '-current_version', '1', '-no_fixup_chains', '-no_adhoc_codesign',
           *[str(root / u['object']) for u in units], *[str(guest / name.lstrip('/')) for name in dependencies], '-o', str(binary)]
with (folder / 'link.log').open('w') as stream: result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
(folder / 'link.json').write_text(json.dumps(dict(command=command, status=result.returncode), indent=2) + '\n')
if result.returncode:
    print((folder / 'link.log').read_text()[-4000:]); raise SystemExit(1)
def exports(path):
    output = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
    return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)', output, re.M))
original, actual = exports(baseline), exports(binary)
assert not original - actual, sorted(original - actual)
(binary.parent / 'libresolv.dylib').symlink_to(binary.name)
record = dict(full_libresolv_source_build=True, complete_source_files=len(units), units=units,
              library=str(binary.relative_to(root)), library_sha256=sha(binary),
              baseline=str(baseline.relative_to(root)), baseline_sha256=sha(baseline),
              original_exports_preserved=len(original), added_exports=sorted(actual - original),
              link_command=command, header_environment=args.header_environment,
              header_environment_sha256=sha(root / args.header_environment), driver_sha256=sha(Path(__file__)),
              source_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
              runtime_execution_verified=False, full_goal_complete=False)
(folder / 'build.json').write_text(json.dumps(record, indent=2) + '\n'); print(folder.relative_to(root) / 'build.json')
