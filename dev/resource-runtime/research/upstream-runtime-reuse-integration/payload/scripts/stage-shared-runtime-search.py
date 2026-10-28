#!/usr/bin/env python3
"""Index a complete run's existing providers without changing their priority.

Only location-independent Intel dylibs take the fast path. Libraries using
@loader_path keep their original directories. Framework aliases retain all
original fallback directories for versioned and image-suffix lookups.
"""
from pathlib import Path
import argparse, hashlib, json, os, struct, tempfile, unicodedata

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile', required=True)
args = parser.parse_args()
profile_path = root / args.profile
profile = json.loads(profile_path.read_text())
assert profile['direct_resource_environment']['runtime_mode'] == 'unified'
environment = profile['direct_resource_environment']['tool_environment']
folder = Path(tempfile.mkdtemp(prefix='shared-runtime-search-', dir=root / 'runtime'))
libraries, frameworks = folder / 'libraries', folder / 'frameworks'
libraries.mkdir(); frameworks.mkdir()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
links, inputs, choices = {}, {}, {}
ascii_fold = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')

def normalized_name(name):
    # Match vchroot's decomposed spelling and ASCII-only case comparison.
    return unicodedata.normalize('NFD', name).translate(ascii_fold)

def normalized_collisions(candidates):
    groups = {}
    for name in candidates:
        groups.setdefault(normalized_name(name), []).append(name)
    return {key: names for key, names in groups.items() if len(names) > 1}

def macho(path):
    """Read load commands, not entire library images."""
    try:
        with path.open('rb') as stream:
            header = stream.read(4096)
            if len(header) < 32:
                return None
            magic = struct.unpack_from('>I', header)[0]
            offsets = [0]
            if magic in (0xcafebabe, 0xcafebabf):
                count = struct.unpack_from('>I', header, 4)[0]
                if count > 64:
                    return None
                size = 32 if magic == 0xcafebabf else 20
                stream.seek(8); table = stream.read(size * count)
                offsets = []
                for index in range(count):
                    row = struct.unpack_from('>IIQQII' if size == 32 else '>IIIII', table, size * index)
                    if row[0] == 0x1000007:
                        offsets.append(row[2])
                if not offsets:
                    return None
            loader_relative = False
            for offset in offsets:
                stream.seek(offset); header = stream.read(32)
                if struct.unpack_from('<I', header)[0] != 0xfeedfacf:
                    return None
                fields = struct.unpack_from('<8I', header)
                if fields[1] != 0x1000007 or fields[3] not in (6, 8) or fields[5] > 16 * 1024 * 1024:
                    return None
                stream.seek(offset + 32); commands = stream.read(fields[5])
                if len(commands) != fields[5]:
                    return None
                loader_relative |= b'@loader_path' in commands
            return dict(loader_relative=loader_relative, filetype=fields[3])
    except (OSError, ValueError, struct.error):
        return None

def alias(destination, source):
    target = os.path.relpath(source, destination.parent)
    destination.symlink_to(target, target_is_directory=source.is_dir())
    links[str(destination.relative_to(root))] = target

candidates = {}
original_directories = environment['DYLD_LIBRARY_PATH'].split(':')
retained = set()
for directory in original_directories:
    prefix = '/Volumes/SystemRoot/workspace/'
    if not directory.startswith(prefix):
        retained.add(directory); continue
    path = root / directory[len(prefix):]
    if not path.is_dir():
        continue
    for entry in sorted(path.iterdir()):
        if not entry.is_file():
            continue
        info = macho(entry)
        if info is None and not entry.name.endswith('.dylib'):
            continue
        candidates.setdefault(entry.name, []).append((directory, entry, info))

library_collisions = normalized_collisions(candidates)
for name, providers in candidates.items():
    directory, source, info = providers[0]
    collision = library_collisions.get(normalized_name(name))
    if collision:
        provider_directories = {row[0] for spelling in collision for row in candidates[spelling]}
        retained.update(provider_directories)
        choices[name] = dict(mode='original-directories', reason='normalized-name-collision',
            names=collision, directories=[value for value in original_directories if value in provider_directories])
    elif info is None or info['loader_relative']:
        retained.update(row[0] for row in providers)
        choices[name] = dict(mode='original-directories', directories=[row[0] for row in providers])
    else:
        alias(libraries / name, source)
        inputs[str(source.relative_to(root))] = sha(source)
        choices[name] = dict(mode='indexed-first-provider', source=str(source.relative_to(root)))

framework_choices, framework_candidates = {}, {}
for directory in environment['DYLD_FRAMEWORK_PATH'].split(':'):
    prefix = '/Volumes/SystemRoot/workspace/'
    assert directory.startswith(prefix)
    path = root / directory[len(prefix):]
    if not path.is_dir():
        continue
    for entry in sorted(path.iterdir()):
        if not normalized_name(entry.name).endswith('.framework') or not entry.is_dir():
            continue
        framework_candidates.setdefault(entry.name, []).append(entry)
framework_collisions = normalized_collisions(framework_candidates)
for name, providers in framework_candidates.items():
    if normalized_name(name) in framework_collisions:
        continue # All original framework directories already remain below.
    # The first framework directory remains the first candidate, including
    # its original Resources, symlinks and versioned executable layout.
    framework_choices[name] = str(providers[0].relative_to(root))
    alias(frameworks / name, providers[0])

selected = dict(
    DYLD_LIBRARY_PATH=':'.join([guest(libraries)] + [value for value in original_directories if value in retained]),
    DYLD_FRAMEWORK_PATH=guest(frameworks) + ':' + environment['DYLD_FRAMEWORK_PATH'])
inputs[args.profile] = sha(profile_path)
inputs[str(Path(__file__).relative_to(root))] = sha(Path(__file__))
record = dict(runtime_mode='unified', original_environment=environment, environment=selected,
              libraries=str(libraries.relative_to(root)), frameworks=str(frameworks.relative_to(root)),
              files=inputs, links=links, library_choices=choices, framework_choices=framework_choices,
              library_normalized_name_collisions=library_collisions,
              framework_normalized_name_collisions=framework_collisions,
              original_library_directories=len(original_directories),
              selected_library_directories=len(selected['DYLD_LIBRARY_PATH'].split(':')),
              original_framework_fallbacks_preserved=True, original_provider_bytes_modified=False,
              native_verified=False)
(folder / 'stage.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(dict(stage=str((folder / 'stage.json').relative_to(root)),
                     library_directories_before=record['original_library_directories'],
                     library_directories_after=record['selected_library_directories'],
                     indexed_libraries=sum(row['mode']=='indexed-first-provider' for row in choices.values()),
                     indexed_frameworks=len(framework_choices))))
