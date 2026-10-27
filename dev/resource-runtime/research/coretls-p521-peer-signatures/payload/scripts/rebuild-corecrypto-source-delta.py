#!/usr/bin/env python3
"""Recompile explicitly changed CoreCrypto units into a fresh complete library."""
from pathlib import Path
import argparse, copy, hashlib, json, re, runpy, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--template', required=True)
parser.add_argument('--changed-source', action='append', required=True)
args = parser.parse_args()
base = json.loads((root / args.template).read_text())
assert base['full_CoreCrypto_source_build'] and base['complete_source_files'] == len(base['sources'])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
assert sha(root / base['library']) == base['library_sha256']
assert sha(root / base['BoringSSL']['archive']) == base['BoringSSL']['archive_sha256']
for name, digest in base['source_headers'].items(): assert sha(root / name) == digest, name
changed = set(args.changed_source)
assert changed <= {u['source'] for u in base['sources']}
folder = Path(tempfile.mkdtemp(prefix='corecrypto-source-delta-', dir=root / 'runtime'))
units = []; replacements = {}
for entry in base['sources']:
    row = copy.deepcopy(entry); source = row['source']; old = root / row['object']
    assert sha(old) == row['object_sha256']
    if source in changed:
        obj = folder / old.name; command = list(row['command']); command[command.index('-o') + 1] = str(obj)
        log = obj.with_suffix('.log')
        with log.open('w') as stream: result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        assert result.returncode == 0, log
        replacements[str(old)] = str(obj)
        row.update(sha256=sha(root / source), object=str(obj.relative_to(root)), object_sha256=sha(obj), command=command, reused=False)
    else:
        resolve(source, row['sha256']); row['reused'] = True
    units.append(row)
output = folder / 'libraries/libcorecrypto.dylib'; output.parent.mkdir()
command = [replacements.get(value, value) for value in base['link_command']]
command[command.index('-o') + 1] = str(output)
with (folder / 'link.log').open('w') as stream: result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
assert result.returncode == 0, folder / 'link.log'
def exports(path):
    text = subprocess.check_output(['llvm-objdump-19', '--macho', '--exports-trie', str(path)], text=True)
    return set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)', text, re.M))
assert exports(output) == exports(root / base['library'])
record = {**base, 'sources': units, 'library': str(output.relative_to(root)), 'library_sha256': sha(output),
          'parent_build': args.template, 'parent_build_sha256': sha(root / args.template),
          'recompiled_units': len(changed), 'reused_units': len(units) - len(changed),
          'link_command': command, 'driver_sha256': sha(Path(__file__)),
          'runtime_execution_verified': False, 'P521_runtime_verified': False}
(folder / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
print(folder.relative_to(root) / 'build.json')
