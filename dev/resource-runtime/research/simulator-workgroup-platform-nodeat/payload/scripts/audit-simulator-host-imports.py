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
a = p.parse_args()
sim, host = root / a.simulator_system, root / a.host_root / 'usr/lib/system'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
providers = {}
for kind in ['kernel', 'pthread', 'platform']:
    name = 'libsystem_sim_' + kind
    paths = [sim / (name + '.dylib'), host / ('libsystem_' + kind + '.dylib')]
    symbols = set()
    for path in paths:
        text = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
        symbols.update(re.findall(r'^0x[\da-fA-F]+\s+(\S+)', text, re.M))
    providers[name] = dict(paths=paths, exports=symbols)
def inspect(path):
    text = subprocess.check_output(['llvm-nm-19', '--format=darwin', '--undefined-only', str(path)],
                                   text=True, stderr=subprocess.DEVNULL)
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
with ThreadPoolExecutor(max_workers=8) as pool:
    rows = list(pool.map(inspect, sorted(sim.glob('*.dylib'))))
report = dict(scope='Static named imports of original simulator system libraries against actual simulator wrappers plus selected reexported host kernel/pthread/platform. Other images and actual behavior require separate checks.',
              providers={n: dict(files={str(p.relative_to(root)): sha(p) for p in row['paths']},
                                 export_count=len(row['exports'])) for n, row in providers.items()},
              images=rows, image_count=len(rows), missing_count=sum(len(row['absent_wrapper_and_host_exports']) for row in rows),
              tool=str(Path(__file__).relative_to(root)), tool_sha256=sha(Path(__file__)), full_goal_complete=False)
target = root / a.report
assert not target.exists()
target.write_text(json.dumps(report, indent=2) + '\n')
print('Scanned', len(rows), 'images; absent named imports:', report['missing_count'])
for row in rows:
    if row['absent_wrapper_and_host_exports']: print(row['image'], row['absent_wrapper_and_host_exports'])
