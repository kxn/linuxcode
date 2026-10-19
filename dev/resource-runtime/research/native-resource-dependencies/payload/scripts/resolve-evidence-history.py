"""Resolve exact older inputs without replacing the evidence of prior builds."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent.parent
histories=[
    'artifacts/ios-resource-initial-history/manifest.json',
    'artifacts/global-fsevents-initial-history/manifest.json',
    'artifacts/fsevents-history-initial-history/manifest.json',
    'artifacts/xcode-initialization-initial-history/manifest.json',
    'artifacts/mobileasset-query-initial-history/manifest.json',
    'artifacts/xpc-activation-initial-history/manifest.json',
    'artifacts/fileidtree-volume-initial-history/manifest.json',
    'artifacts/mount-flags-initial-history/manifest.json',
    'artifacts/mount-path-canonicalization-history/manifest.json',
    'artifacts/iokit-matching-initial-history/manifest.json',
    'artifacts/iokit-power-initial-history/manifest.json',
    'artifacts/diskarbitration-initial-history/manifest.json',
    'artifacts/fsevents-device-initial-history/manifest.json',
    'artifacts/sandbox-before-unrestricted-profile-history/manifest.json',
    'artifacts/sandbox-before-fs-mutations-history/manifest.json',
    'artifacts/sandbox-policy-before-launchd-history/manifest.json',
    'artifacts/native-crypto-before-policy-vm-history/manifest.json',
]
def resolve(name,sha):
    digest=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest()
    if (root/name).is_file() and digest(name)==sha:return name
    for manifest in histories:
        entry=json.loads((root/manifest).read_text()).get(str(name))
        if entry and entry['sha256']==sha:
            assert digest(entry['archived'])==sha,(name,manifest)
            return entry['archived']
    entry=json.loads((root/'runtime/source-input-history/manifest.json').read_text()).get(str(name))
    if entry:
        path=entry['snapshot'] if entry['sha256']==sha else entry.get('revisions',{}).get(sha)
        if path:
            assert path=='runtime/source-input-history/'+sha and digest(path)==sha,name
            return path
    raise AssertionError('Missing exact historical input: '+str(name)+' '+sha)
