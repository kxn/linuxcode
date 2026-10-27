"""Provide Unity's pinned native Linux CLI without a graphical Hub or shell edits."""
from pathlib import Path
import ctypes
import errno
import hashlib
import os
import platform
import subprocess
import tempfile
import urllib.request

VERSION = '1.0.0-beta.14'
SHA256 = 'd9a2c1716ce723b970898f7f40adc09cceee04e84ce2f1f1638f07ac3e9898aa'
SIZE = 35929504
URL = 'https://public-cdn.cloud.unity3d.com/hub/prod/cli/' + VERSION + '/unity-linux-x64'



def _prepare_keyring_session():
    # SSH/automation parents can retain a revoked session keyring. Repair only
    # that missing/expired session in this process; the parent's ring is intact.
    try:
        library = ctypes.CDLL('libkeyutils.so.1', use_errno=True)
    except OSError:
        return  # The official CLI may use another available OS credential backend.
    library.keyctl_get_keyring_ID.argtypes = [ctypes.c_int, ctypes.c_int]
    library.keyctl_get_keyring_ID.restype = ctypes.c_int
    ctypes.set_errno(0)
    if library.keyctl_get_keyring_ID(-3, 0) >= 0:
        return
    if ctypes.get_errno() not in (getattr(errno, 'ENOKEY', 126), getattr(errno, 'EKEYEXPIRED', 127), getattr(errno, 'EKEYREVOKED', 128)):
        return
    library.keyctl_join_session_keyring.argtypes = [ctypes.c_char_p]
    library.keyctl_join_session_keyring.restype = ctypes.c_int
    session = library.keyctl_join_session_keyring(b'linuxcode-unity-cli')
    user = library.keyctl_get_keyring_ID(-4, 1)
    library.keyctl_link.argtypes = [ctypes.c_int, ctypes.c_int]
    library.keyctl_link.restype = ctypes.c_long
    if session < 0 or user < 0 or library.keyctl_link(session, user) < 0:
        raise RuntimeError('Cannot prepare the native Unity CLI credential keyring; no login was started.')


def run(workspace, arguments):
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise RuntimeError('This pinned Unity CLI entry currently supports Linux x86_64.')
    binary = workspace / ('runtime/unity-cli-native-' + VERSION) / 'bin/unity'
    if binary.exists():
        if binary.stat().st_size != SIZE or hashlib.sha256(binary.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError('Existing Unity CLI differs from the official pinned binary; it has been preserved.')
    else:
        binary.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.unity-download-', dir=binary.parent)
        pending = Path(name)
        try:
            digest = hashlib.sha256(); count = 0
            with os.fdopen(fd, 'wb') as out, urllib.request.urlopen(URL, timeout=45) as source:
                while data := source.read(1024 * 1024):
                    count += len(data)
                    if count > SIZE: raise RuntimeError('Unity CLI download exceeds the pinned size.')
                    out.write(data); digest.update(data)
                out.flush(); os.fsync(out.fileno())
            if count != SIZE or digest.hexdigest() != SHA256:
                raise RuntimeError('Unity CLI download does not match the official SHA256.')
            pending.chmod(0o755)
            os.link(pending, binary)
        finally:
            pending.unlink(missing_ok=True)
    if arguments[:1] == ['--']: arguments = arguments[1:]
    if arguments[:1] and arguments[0] in ('auth', 'license', 'doctor', 'shell'):
        _prepare_keyring_session()
    # Authentication, license selection, terms acceptance and credential storage
    # remain in the original CLI. No password/token arguments or logs are added.
    return subprocess.call([str(binary), *(arguments or ['--help'])])
