#!/usr/bin/env python3
"""Select Xcode's actual MobileDevice payload before Darling's older image."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/pid-generation-source-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources)
    mobile=p['native_mdns']['mobile_device']
    path=mobile['payload_root']+'/System/Library/PrivateFrameworks/MobileDevice.framework/Versions/A/MobileDevice'
    assert verified_digest((root/path))==mobile['files'][path]
    c=list(p['command'])
    if include_system_resources:
        i=next(i for i,a in enumerate(c) if a.startswith('DYLD_FRAMEWORK_PATH='))
        c[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/'+mobile['payload_root']+'/System/Library/PrivateFrameworks:'+c[i].split('=',1)[1]
    return {**p,'command':c,'native_mobile_device_selection':dict(image=path,sha256=mobile['files'][path],selected=include_system_resources,binary_modified=False)}
def environment(p):return m['environment'](p)
