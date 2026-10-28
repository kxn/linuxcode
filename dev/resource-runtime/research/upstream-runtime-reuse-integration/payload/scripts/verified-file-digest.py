"""Reuse a file digest only while its filesystem identity and timestamps agree.

The cache is disposable private build state, never a replacement for an expected
SHA-256 from a build report. Callers continue to compare against that expected
value. Every cache hit stats the actual file; modified or replaced files hash
again. No runtime execution result is cached by this module.
"""
from pathlib import Path
import atexit,fcntl,hashlib,json,os,re,stat,sys,tempfile,threading,types,time
root=Path(__file__).resolve().parent.parent
name='_linuxcode_verified_file_digest_state_v1'
if name not in sys.modules:
    state=types.ModuleType(name)
    state.file=Path(os.environ.get('LINUXCODE_FILE_DIGEST_CACHE',str(root/'runtime/verified-file-digests-v1.json')))
    state.entries={};state.dirty={};state.lock=threading.RLock();state.hits=state.misses=state.bytes_hashed=0
    try:
        saved=json.loads(state.file.read_text())
        if saved.get('schema')==1 and isinstance(saved.get('entries'),dict):state.entries=saved['entries']
    except (OSError,ValueError,AttributeError):pass
    sys.modules[name]=state
    def flush(s=state):
        if not s.dirty:return
        s.file.parent.mkdir(parents=True,exist_ok=True)
        with s.file.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                old=json.loads(s.file.read_text());entries=old['entries'] if old.get('schema')==1 and isinstance(old.get('entries'),dict) else {}
            except (OSError,ValueError,KeyError,AttributeError):entries={}
            entries.update(s.dirty)
            fd,pending=tempfile.mkstemp(prefix=s.file.name+'.',dir=s.file.parent)
            try:
                with os.fdopen(fd,'w') as out:json.dump(dict(schema=1,entries=entries),out,separators=(',',':'));out.write('\n')
                os.replace(pending,s.file)
            finally:
                if os.path.exists(pending):os.unlink(pending)
    state.flush=flush;atexit.register(flush)
state=sys.modules[name]
def identity(value):
    if not stat.S_ISREG(value.st_mode):raise ValueError('Digest input is not a regular file')
    return [value.st_dev,value.st_ino,value.st_mode,value.st_size,value.st_mtime_ns,value.st_ctime_ns]
def digest(path):
    path=Path(path).absolute();key=str(path)
    with state.lock:
        before=identity(path.stat());row=state.entries.get(key)
        # Recent writes may share a coarse filesystem timestamp; hash until it ages.
        aged = time.time_ns()-before[-1] > 1_000_000_000
        if (aged and isinstance(row,list) and len(row)==2 and row[0]==before and
            isinstance(row[1],str) and re.fullmatch('[0-9a-f]{64}',row[1])):
            state.hits+=1;return row[1]
        for attempt in range(3):
            with path.open('rb') as source:
                opened=identity(os.fstat(source.fileno()))
                value=hashlib.file_digest(source,'sha256').hexdigest()
                stable=opened==identity(os.fstat(source.fileno()))==identity(path.stat())
            if stable:
                row=[opened,value];state.entries[key]=row;state.dirty[key]=row
                state.misses+=1;state.bytes_hashed+=opened[3];return value
        raise RuntimeError('Digest input changed during hashing: '+key)
def statistics():
    with state.lock:return dict(cache_hits=state.hits,files_hashed=state.misses,bytes_hashed=state.bytes_hashed)
