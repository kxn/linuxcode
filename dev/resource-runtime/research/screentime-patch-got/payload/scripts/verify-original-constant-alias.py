#!/usr/bin/env python3
"""Verify one known metadata alias in both original and selected standalone images."""
from pathlib import Path
import hashlib
import re
import runpy
import subprocess

NAMES = {'_$sSo7NSErrorC15SonicFoundationE15treeDescriptionSSvpMV',
         '_$ss5ErrorP15SonicFoundationE15treeDescriptionSSvpMV'}
PROVIDER = '/System/Library/PrivateFrameworks/SonicFoundation.framework/Versions/A/SonicFoundation'

def verify(ns, address, choices, binary, root):
    assert len(choices) == 2 and {name for name, _ in choices} == NAMES
    assert {provider for _, provider in choices} == {PROVIDER}
    image = ns['image'](PROVIDER)
    assert address % 4 == 0
    for name in NAMES:
        value = image.exports[name]
        assert value[0] == 'address' and value[1] == address and value[2] == 0
    assert any(name == '__const' and segment == '__TEXT' and not flags & 0x80000400
               and start <= address and address+4 <= start+size
               for name, segment, start, size, flags in image.sections)
    assert ns['read'](address,4) == bytes(4)
    binary = Path(binary)
    assert not binary.is_absolute() and '..' not in binary.parts
    candidate = root/binary
    assert candidate.is_file() and not candidate.is_symlink()
    content = candidate.read_bytes()
    exports = subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(candidate)],text=True)
    values = []
    for name in sorted(NAMES):
        matches = re.findall(r'^0x([0-9A-Fa-f]+)\s+'+re.escape(name)+r'$',exports,re.M)
        assert len(matches) == 1
        values.append(int(matches[0],16))
    assert values[0] == values[1] == address-image.base
    segments, sections, _ = runpy.run_path(str(root/'scripts/inspect-preserved-patch-got.py'))['macho'](content)
    assert any(key == ('__TEXT','__const') and start <= values[0] and values[0]+4 <= start+size
               and not flags & 0x80000400 for key,(start,size,_,flags) in sections.items())
    owners = [segment for segment in segments if segment[1] <= values[0] and values[0]+4 <= segment[1]+segment[2]]
    assert len(owners) == 1
    segment = owners[0]
    offset = segment[3]+values[0]-segment[1]
    assert content[offset:offset+4] == bytes(4)
    return dict(provider=PROVIDER,names=sorted(NAMES),original_address=hex(address),
        original_provider_sha256=hashlib.sha256((root/'runtime/fullsystem-libraries'/PROVIDER.lstrip('/')).read_bytes()).hexdigest(),
        selected_provider=str(binary),selected_provider_sha256=hashlib.sha256(content).hexdigest(),
        selected_export_address=hex(values[0]),same_original_and_selected_object=True,
        copied_literal=False)
