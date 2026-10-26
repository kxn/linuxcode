#!/usr/bin/env python3
"""Private complete original CoreCrypto + original CryptoKit experiment."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/cryptokit-original-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);report='runtime/rebuilt-corecrypto-original-native-v2/reconstruction.json';d=json.loads((root/report).read_text());digest=lambda n:verified_digest((root/n))
    original='runtime/fullsystem-libraries/usr/lib/system/libcorecrypto.dylib';library='runtime/rebuilt-corecrypto-original-native-v2/libcorecrypto.dylib'
    assert digest(original)==d['original_image_sha256'] and digest(library)==d['staged_image_sha256']
    assert not d['backend_call_overrides'] and d['redirected_imports']==['_malloc_type_malloc']
    malloc=json.loads((root/'artifacts/corecrypto-malloc-source-build.json').read_text())
    for key in ['source','library']:assert digest(malloc[key])==malloc[key+'_sha256']
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_LIBRARY_PATH='))
    command[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/rebuilt-corecrypto-original-native-v2:/Volumes/SystemRoot/workspace/runtime/corecrypto-malloc-source/libraries:'+command[i].split('=',1)[1]
    return {**p,'command':command,'corecrypto_malloc':malloc,'native_original_corecrypto':dict(original=original,original_sha256=digest(original),library=library,library_sha256=digest(library),reconstruction=report,reconstruction_sha256=digest(report),exports=d['exports'],cryptographic_call_overrides=False,typed_allocator_redirect=True)}
def environment(p):return m['environment'](p)
