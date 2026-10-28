#!/usr/bin/env python3
"""Select the complete source CoreTLS CF helpers in one consumer scope."""
from pathlib import Path
import hashlib, json, runpy

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
    directories = ['/Volumes/SystemRoot/workspace/' + str(directory.relative_to(root))]
    selected = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))['prepend_library_directories'](profile, directories)
    return {**selected, 'source_coretls_cfhelpers_build': report}
