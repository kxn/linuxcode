"""Provide Unity's pinned native Linux CLI without a graphical Hub or shell edits."""
from pathlib import Path
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
    # Authentication, license selection, terms acceptance and credential storage
    # remain in the original CLI. No password/token arguments or logs are added.
    return subprocess.call([str(binary), *(arguments or ['--help'])])
