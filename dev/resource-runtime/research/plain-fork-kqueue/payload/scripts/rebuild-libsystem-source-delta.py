#!/usr/bin/env python3
"""Recompile changed libSystem initializer/queue units while preserving other objects."""
from pathlib import Path
import argparse, copy, hashlib, json, runpy, shlex, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--template-objects', required=True)
parser.add_argument('--changed-source', action='append', required=True)
parser.add_argument('--changed-header', action='append', default=[])
args = parser.parse_args()
data = json.loads((root / args.template_objects).read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
changed = {str((root / p).resolve()) for p in args.changed_source}
changed_headers = {str((root / p).resolve()) for p in args.changed_header}
# A header change is closed over the explicitly recompiled units. Old objects
# cannot silently retain a different declaration from a shared changed header.
for original in data['commands']:
    dep = Path(original[original.index('-MF') + 1])
    dependencies = {str(Path(p).resolve()) for p in shlex.split(dep.read_text().split(':', 1)[1].replace('\\\n', ' '))}
    if dependencies & changed_headers:
        assert any(value in changed for value in original), original
commands = copy.deepcopy(data['commands']); folder = Path(tempfile.mkdtemp(prefix='libsystem-fork-queue-source-', dir=root / 'runtime'))
replacements = {}; observed = set()
for command in commands:
    source = next((value for value in command if value in changed), None)
    if source is None: continue
    observed.add(source); old = command[command.index('-o') + 1]; obj = folder / Path(old).name; dep = obj.with_suffix('.d')
    command[command.index('-o') + 1] = str(obj); command[command.index('-MF') + 1] = str(dep)
    with obj.with_suffix('.log').open('w') as stream: subprocess.run(command, check=True, stdout=stream, stderr=subprocess.STDOUT)
    replacements[str(Path(old).relative_to(root))] = str(obj.relative_to(root))
assert observed == changed
for name, digest in data['sources'].items():
    if str((root / name).resolve()) in changed: data['sources'][name] = sha(root / name)
    else: resolve(name, digest)
for name, digest in list(data['dependency_sha256'].items()):
    path = Path(name) if Path(name).is_absolute() else root / name
    if str(path.resolve()) in changed: data['dependency_sha256'][name] = sha(path)
    elif path.is_relative_to(root): resolve(str(path.relative_to(root)), digest)
    else: assert sha(path) == digest, path
for name, digest in data['object_sha256'].items(): assert sha(root / name) == digest
for dep in folder.glob('*.d'):
    for name in shlex.split(dep.read_text().split(':', 1)[1].replace('\\\n', ' ')):
        path = Path(name).resolve(); key = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        if str(path) not in changed | changed_headers and key in data['dependency_sha256']:
            assert sha(path) == data['dependency_sha256'][key], path
        data['dependency_sha256'][key] = sha(path)
data['objects'] = [replacements.get(name, name) for name in data['objects']]
data['object_sha256'] = {name: sha(root / name) for name in data['objects']}
data.update(commands=commands, delta_parent_object_report=args.template_objects,
            recompiled_objects=len(replacements), reused_objects=len(data['objects']) - len(replacements),
            changed_headers=sorted(args.changed_header),
            delta_builder_sha256=sha(Path(__file__)))
(folder / 'objects.json').write_text(json.dumps(data, indent=2) + '\n')
print(folder.relative_to(root) / 'objects.json')
