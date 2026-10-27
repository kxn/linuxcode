#!/usr/bin/env python3
"""Select the complete source CoreTLS CF helpers in one consumer scope."""
from pathlib import Path
import hashlib, json

root = Path(__file__).resolve().parent.parent


def select(profile, report):
    build = json.loads((root / report).read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert build['full_coretls_cfhelpers_source_build'] and build['complete_source_files'] == 3
    assert build['original_exports_preserved'] == 19 and build['Security_load_is_upward']
    assert sha(root / build['library']) == build['library_sha256']
    assert sha(root / build['coretls_build']) == build['coretls_build_sha256']
    selected_tls = json.loads((root / profile['source_coretls_build']).read_text())
    linked_tls = json.loads((root / build['coretls_build']).read_text())
    assert selected_tls['full_coretls_source_build'] and selected_tls['complete_source_files'] == 31
    assert all(selected_tls[key] == linked_tls[key] for key in ['backend_sha256', 'umbrella_sha256'])
    directory = (root / build['library']).parent
    prefix = '/Volumes/SystemRoot/workspace/' + str(directory.relative_to(root)) + ':'
    command = list(profile['command'])
    index = next(i for i, value in enumerate(command) if value.startswith('DYLD_LIBRARY_PATH='))
    command[index] = 'DYLD_LIBRARY_PATH=' + prefix + command[index].split('=', 1)[1]
    direct = dict(profile['direct_resource_environment']); scope = dict(direct['tool_environment'])
    scope['DYLD_LIBRARY_PATH'] = prefix + scope['DYLD_LIBRARY_PATH']; direct['tool_environment'] = scope
    return {**profile, 'command': command, 'direct_resource_environment': direct, 'source_coretls_cfhelpers_build': report}
