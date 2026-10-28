"""Resolve exact older inputs without replacing the evidence of prior builds."""
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,os,sys,threading,time,types
root=Path(__file__).resolve().parent.parent
# Profile selectors load this file repeatedly with runpy. Share parsed history
# only within this Python process and invalidate it whenever file identity or
# timestamps change. Actual source/snapshot bytes still use the existing digest
# verifier below; this cache never stands in for a successful runtime test.
_cache_name='_linuxcode_evidence_history_cache_v1'
if _cache_name not in sys.modules:
    _state=types.ModuleType(_cache_name)
    _state.entries={}
    _state.lock=threading.RLock()
    _state.hits=_state.reads=0
    sys.modules[_cache_name]=_state
_state=sys.modules[_cache_name]

def _identity(value):
    return (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)

def _history(path):
    path=Path(path).absolute()
    with _state.lock:
        current=_identity(path.stat())
        cached=_state.entries.get(str(path))
        # Coarse filesystem timestamps can hide rapid same-size rewrites.
        # As in verified-file-digest.py, recent writes must be read again.
        aged=time.time_ns()-current[-1]>1_000_000_000
        if aged and cached is not None and cached[0]==current:
            _state.hits+=1
            return cached[1]
        for attempt in range(3):
            with path.open() as source:
                opened=_identity(os.fstat(source.fileno()))
                content=source.read()
                stable=opened==_identity(os.fstat(source.fileno()))==_identity(path.stat())
            if stable:
                value=json.loads(content)
                if not isinstance(value,dict):
                    raise ValueError('History manifest must be an object: '+str(path))
                _state.entries[str(path)]=(opened,value)
                _state.reads+=1
                return value
        raise RuntimeError('History manifest changed during reading: '+str(path))
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
    digest=lambda n:verified_digest((root/n))
    if (root/name).is_file() and digest(name)==sha:return name
    for manifest in histories:
        entry=_history(root/manifest).get(str(name))
        if entry and entry['sha256']==sha:
            assert digest(entry['archived'])==sha,(name,manifest)
            return entry['archived']
    entry=_history(root/'runtime/source-input-history/manifest.json').get(str(name))
    if entry:
        path=entry['snapshot'] if entry['sha256']==sha else entry.get('revisions',{}).get(sha)
        if path:
            # Older snapshots use a flat digest name; named snapshots preserve
            # the original basename inside the same digest directory. Both
            # forms must identify the exact historical bytes, never a fallback.
            prefix='runtime/source-input-history/'+sha
            assert path in (prefix,prefix+'/'+Path(name).name) and digest(path)==sha,name
            return path
    raise AssertionError('Missing exact historical input: '+str(name)+' '+sha)
