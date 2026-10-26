#!/usr/bin/env python3
"""Private original sandbox compiler and Match engine on the source directory runtime."""
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/coreservices-directories-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);digest=lambda n:verified_digest((root/n));images={}
    for target,name in [('sandbox-compiler-native','libsandbox.1.dylib'),('match-sandbox-native','libMatch.1.dylib')]:
        reconstruction='runtime/rebuilt-'+target+'/reconstruction.json';d=json.loads((root/reconstruction).read_text());assert not d['backend_call_overrides']
        original='runtime/fullsystem-libraries/usr/lib/'+name;library='runtime/rebuilt-'+target+'/'+name
        assert digest(original)==d['original_image_sha256'] and digest(library)==d['staged_image_sha256']
        images[target]=dict(original=original,original_sha256=digest(original),library=library,library_sha256=digest(library),reconstruction=reconstruction,reconstruction_sha256=digest(reconstruction),exports=d['exports'],redirected_imports=d['redirected_imports'],backend_call_overrides=False)
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_LIBRARY_PATH='));command[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/rebuilt-sandbox-compiler-native:/Volumes/SystemRoot/workspace/runtime/rebuilt-match-sandbox-native:'+command[i].split('=',1)[1]
    return {**p,'command':command,'native_sandbox_compiler':images}
def environment(p):return m['environment'](p)
