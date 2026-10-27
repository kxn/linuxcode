#!/usr/bin/env python3
"""Select the complete source DNS resolver for one private consumer scope."""
from pathlib import Path
import hashlib, json

root = Path(__file__).resolve().parent.parent


def select(profile, report):
    build = json.loads((root / report).read_text())
    assert build['full_libresolv_source_build'] and build['complete_source_files'] == 27
    library = root / build['library']
    assert hashlib.sha256(library.read_bytes()).hexdigest() == build['library_sha256']
    prefix = '/Volumes/SystemRoot/workspace/' + str(library.parent.relative_to(root)) + ':'
    command = list(profile['command'])
    index = next(i for i, value in enumerate(command) if value.startswith('DYLD_LIBRARY_PATH='))
    command[index] = 'DYLD_LIBRARY_PATH=' + prefix + command[index].split('=', 1)[1]
    direct = dict(profile['direct_resource_environment']); scope = dict(direct['tool_environment'])
    scope['DYLD_LIBRARY_PATH'] = prefix + scope['DYLD_LIBRARY_PATH']; direct['tool_environment'] = scope
    return {**profile, 'command': command, 'direct_resource_environment': direct, 'source_libresolv_build': report}
