#!/usr/bin/env python3
"""Start the existing source Security services without replacing consumer APIs."""
from pathlib import Path
import plistlib
import runpy
import tempfile

root = Path(__file__).resolve().parent.parent


def select(profile, candidate):
    folder = Path(tempfile.mkdtemp(prefix='native-security-services-', dir=root / 'runtime'))
    folder.chmod(0o700)
    store = folder / 'empty-identities.plist'
    store.write_bytes(plistlib.dumps(dict(version=1, locked=False, items=[])))
    store.chmod(0o600)
    module = runpy.run_path(str(root / 'scripts/native-certificate-runtime.py'))
    selected = module['select'](profile, candidate, str(store.relative_to(root)),
                                session_directory=folder / 'services')
    # Reuse only the daemon composition. The original consumer keeps its exact
    # framework/library scope, including its certificate and TLS implementation.
    selected['command'] = list(profile['command'])
    evidence = dict(selected['native_certificate_runtime'])
    evidence.update(consumer_framework_scope_preserved=True,
                    consumer_identity_facade_selected=False,
                    empty_identity_store=True,
                    TLS_certificate_trust_verified=False)
    selected['native_security_services'] = evidence
    selected.pop('native_certificate_runtime')
    return selected
