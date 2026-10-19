#!/usr/bin/env python3
"""Validate the LFS engine archive and every Mach-O member without executing it."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import struct
import tempfile

root = Path(__file__).resolve().parent.parent
library = root / 'runtime/unity-uemuera-libiPhone-original-v1.a'
data = library.read_bytes()
assert len(data) == 217810216
digest = hashlib.sha256(data).hexdigest()
assert digest == '8f2d0dd1749da9fc055e87b2c6117b8dee68d41caa441b9521d272e88f8ab485'
assert data[:8] == b'!<arch>\n'
cursor = 8
members = []
platforms = Counter()
while cursor < len(data):
    header = data[cursor:cursor + 60]
    assert len(header) == 60 and header[58:] == b'`\n'
    length = int(header[48:58])
    assert cursor + 60 + length <= len(data)
    content = data[cursor + 60:cursor + 60 + length]
    name = header[:16].decode().strip()
    if name.startswith('#1/'):
        name_length = int(name[3:])
        assert 0 < name_length <= len(content)
        name = content[:name_length].rstrip(b'\0').decode()
        content = content[name_length:]
    if name not in ('__.SYMDEF', '__.SYMDEF SORTED'):
        assert content[:4] == bytes.fromhex('cffaedfe'), name
        _, cpu, subtype, kind, commands, command_bytes, _, _ = struct.unpack_from('<8I', content)
        assert cpu == 0x100000c and kind == 1, (name, cpu, kind)
        assert 32 + command_bytes <= len(content)
        at = 32
        targets = []
        for _ in range(commands):
            command, size = struct.unpack_from('<II', content, at)
            assert size >= 8 and at + size <= 32 + command_bytes
            if command == 0x32:
                assert size >= 24
                platform = struct.unpack_from('<I', content, at + 8)[0]
                assert platform == 2, (name, platform)  # PLATFORM_IOS, not simulator.
                targets.append('iOS')
            elif command == 0x25:
                assert size >= 16
                targets.append('iOS-legacy')
            elif command in (0x24, 0x2f, 0x30):
                raise ValueError('Unexpected deployment platform in ' + name)
            at += size
        assert at == 32 + command_bytes and len(targets) == 1, (name, targets)
        platforms.update(targets)
        members.append(dict(name=name, cpu='arm64', subtype=subtype, platform=targets[0], sha256=hashlib.sha256(content).hexdigest()))
    cursor += 60 + length
    cursor += cursor % 2
assert cursor == len(data) and members
folder = Path(tempfile.mkdtemp(prefix='unity-device-engine-input-', dir=root / 'runtime'))
record = dict(verified=True, library=str(library.relative_to(root)), size=len(data), sha256=digest,
    LFS_oid_verified=True, object_members=len(members), platforms=dict(platforms), members=members,
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    linked_product_verified=False, engine_build_verified=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('ENGINE_INPUT_VERIFIED', len(members), dict(platforms))
print('EVIDENCE', folder / 'result.json')
