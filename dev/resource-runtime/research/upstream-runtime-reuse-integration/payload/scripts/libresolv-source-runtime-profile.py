#!/usr/bin/env python3
"""Select the complete source DNS resolver for one private consumer scope."""
from pathlib import Path
import hashlib, json, runpy

root = Path(__file__).resolve().parent.parent


def select(profile, report):
    build = json.loads((root / report).read_text())
    assert build['full_libresolv_source_build'] and build['complete_source_files'] == 27
    library = root / build['library']
    assert hashlib.sha256(library.read_bytes()).hexdigest() == build['library_sha256']
    directories = ['/Volumes/SystemRoot/workspace/' + str(library.parent.relative_to(root))]
    selected = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))['prepend_library_directories'](profile, directories)
    return {**selected, 'source_libresolv_build': report}
