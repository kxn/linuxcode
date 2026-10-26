#!/usr/bin/env python3
"""Use a matched original CommonCrypto/CoreCrypto ABI privately."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/local-authentication-error-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);report='runtime/rebuilt-commoncrypto-original-native/reconstruction.json';d=json.loads((root/report).read_text());digest=lambda n:verified_digest((root/n))
    original='runtime/fullsystem-libraries/usr/lib/system/libcommonCrypto.dylib';library='runtime/rebuilt-commoncrypto-original-native/libcommonCrypto.dylib'
    assert digest(original)==d['original_image_sha256'] and digest(library)==d['staged_image_sha256'];assert not d['backend_call_overrides'] and d['redirected_imports']==['_malloc_type_malloc']
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_LIBRARY_PATH='));command[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/rebuilt-commoncrypto-original-native:'+command[i].split('=',1)[1]
    return {**p,'command':command,'native_original_commoncrypto':dict(original=original,original_sha256=digest(original),library=library,library_sha256=digest(library),reconstruction=report,reconstruction_sha256=digest(report),exports=d['exports'],cryptographic_call_overrides=False,typed_allocator_redirect=True)}
def environment(p):return m['environment'](p)
