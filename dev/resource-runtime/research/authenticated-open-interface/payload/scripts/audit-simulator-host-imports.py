#!/usr/bin/env python3
"""Check original simulator system imports against wrappers and host exports."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse, hashlib, json, re, subprocess
root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--simulator-system', required=True)
p.add_argument('--host-root', required=True)
p.add_argument('--report', required=True)
p.add_argument('--scan-directory', action='append', default=[])
p.add_argument('--framework-directory', action='append', default=[])
p.add_argument('--image', action='append', default=[])
p.add_argument('--libsystem', action='store_true', help='Include the actual simulator libSystem reexport closure')
a = p.parse_args()
sim, host = root / a.simulator_system, root / a.host_root / 'usr/lib/system'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
providers = {}
for kind in ['kernel', 'pthread', 'platform']:
    name = 'libsystem_sim_' + kind
    paths = [sim / (name + '.dylib'), host / ('libsystem_' + kind + '.dylib')]
    symbols = set()
    for path in paths:
        text = subprocess.check_output(['llvm-objdump-19', '--macho', '--arch=x86_64', '--exports-trie', str(path)], text=True)
        symbols.update(re.findall(r'^(?:0x[\da-fA-F]+|\[re-export\])\s+(\S+)', text, re.M))
    providers[name] = dict(paths=paths, exports=symbols)
if a.libsystem:
    umbrella = sim.parent / 'libSystem.B.dylib'
    dependencies = subprocess.check_output(['llvm-objdump-19', '--macho', '--arch=x86_64', '--dylibs-used', str(umbrella)], text=True)
    names = re.findall(r'^\s+(/\S+) .*reexport\)', dependencies, re.M)
    assert len(names) >= 30
    paths, symbols = [umbrella], set()
    for name in names:
        key = Path(name).stem
        if key in providers:
            paths.extend(providers[key]['paths']); symbols.update(providers[key]['exports'])
        else:
            path = sim / Path(name).name
            text = subprocess.check_output(['llvm-objdump-19', '--macho', '--arch=x86_64', '--exports-trie', str(path)], text=True)
            paths.append(path); symbols.update(re.findall(r'^(?:0x[\da-fA-F]+|\[re-export\])\s+(\S+)', text, re.M))
    providers['libSystem'] = dict(paths=list(dict.fromkeys(paths)), exports=symbols)
def inspect(path):
    result = subprocess.run(['llvm-nm-19', '--arch=x86_64', '--format=darwin', '--undefined-only', str(path)],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        return dict(image=str(path.relative_to(root)), sha256=sha(path),
                    inspection_error=result.stderr, host_import_counts={}, absent_wrapper_and_host_exports=[])
    text = result.stdout
    missing, counts = [], {}
    for line in text.splitlines():
        match = re.search(r'external (\S+) \(from (\S+)\)', line)
        if not match: continue
        symbol, provider = match.groups()
        if provider not in providers: continue
        counts[provider] = counts.get(provider, 0) + 1
        if symbol not in providers[provider]['exports']:
            missing.append(dict(symbol=symbol, provider=provider, weak='weak external' in line))
    return dict(image=str(path.relative_to(root)), sha256=sha(path), host_import_counts=counts,
                absent_wrapper_and_host_exports=missing)
inputs = set(sim.glob('*.dylib'))
for directory in a.scan_directory:
    inputs.update((root / directory).glob('*.dylib'))
for directory in a.framework_directory:
    for framework in (root / directory).rglob('*.framework'):
        image = framework / framework.stem
        if image.is_file(): inputs.add(image)
inputs.update(root / name for name in a.image)
with ThreadPoolExecutor(max_workers=8) as pool:
    rows = list(pool.map(inspect, sorted(inputs)))
report = dict(scope='Static named imports of selected original x86_64 simulator images against wrapper and host export names, optionally including libSystem umbrella names. This name audit does not validate every export target/ordinal, ABI, conditional use, dynamic loading or execution.',
              providers={n: dict(files={str(p.relative_to(root)): sha(p) for p in row['paths']},
                                 export_count=len(row['exports'])) for n, row in providers.items()},
              images=rows, image_count=len(rows), inspection_error_count=sum('inspection_error' in row for row in rows),
              missing_count=sum(len(row['absent_wrapper_and_host_exports']) for row in rows),
              tool=str(Path(__file__).relative_to(root)), tool_sha256=sha(Path(__file__)), full_goal_complete=False)
target = root / a.report
assert not target.exists()
target.write_text(json.dumps(report, indent=2) + '\n')
print('Scanned', len(rows), 'images; absent named imports:', report['missing_count'])
for row in rows:
    if row['absent_wrapper_and_host_exports']: print(row['image'], row['absent_wrapper_and_host_exports'])
