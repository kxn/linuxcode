#!/usr/bin/env python3
"""Keep ordered library lookup while shortening a composed native environment.

Original Mac UBA copies DYLD_LIBRARY_PATH into a fixed 1024-byte buffer when
starting Clang's cc1 child. Our long research directory list exceeds that.
Each contiguous workspace-directory group becomes a private first-match link
directory; non-workspace fallback directories retain their original positions.
Library contents and existing search directories are never changed.
"""
from pathlib import Path
import json
import os
import tempfile

root = Path(__file__).resolve().parent.parent
guest_root = '/Volumes/SystemRoot/workspace/'


def select(profile):
    folder = Path(tempfile.mkdtemp(prefix='dyld-library-paths-', dir=root / 'runtime'))
    substitutions = {}
    groups = []

    def compact(value):
        if value in substitutions:
            return substitutions[value]
        output = []
        pending = []

        def flush():
            if not pending:
                return
            library_dir = folder / ('libraries-' + str(len(groups)))
            library_dir.mkdir()
            selected = {}
            for name in pending:
                path = root / name[len(guest_root):]
                assert path.is_dir() and path.resolve().is_relative_to(root)
                for source in sorted(path.iterdir()):
                    if source.name in selected:
                        continue
                    destination = library_dir / source.name
                    destination.symlink_to(os.path.relpath(source, library_dir))
                    # The new lookup entry refers to the same original object.
                    # Some original symlinks are guest-absolute; preserve those
                    # chains rather than attempting to resolve them on Linux.
                    if source.exists():
                        assert os.path.samestat(source.stat(), destination.stat())
                    selected[source.name] = str(source.relative_to(root))
            short = guest_root + str(library_dir.relative_to(root))
            output.append(short)
            groups.append(dict(original_directories=list(pending), directory=short,
                               first_matching_entries=selected))
            pending.clear()

        for path in value.split(':'):
            assert path.startswith('/') and '..' not in Path(path).parts
            if path.startswith(guest_root) and (root / path[len(guest_root):]).is_dir():
                pending.append(path)
            else:
                flush()
                output.append(path)
        flush()
        result = ':'.join(output)
        assert len(result.encode()) < 700, 'Keep space for UBA prepending its own directory'
        substitutions[value] = result
        return result

    command = []
    for argument in profile['command']:
        if argument.startswith(('DYLD_LIBRARY_PATH=', 'DARLING_DYLD_OVERRIDE_LIBRARY_PATH=')):
            key, value = argument.split('=', 1)
            argument = key + '=' + compact(value)
        command.append(argument)
    metadata = dict(substitutions=substitutions, groups=groups,
                    original_libraries_modified=False,
                    scope='First matching basename in each ordered workspace directory group; guest fallback positions retained',
                    runtime_verified=False)
    report = folder / 'stage.json'
    report.write_text(json.dumps(metadata, indent=2) + '\n')
    return {**profile, 'command': command,
            'compact_library_search_paths': dict(report=str(report.relative_to(root)), **metadata)}
