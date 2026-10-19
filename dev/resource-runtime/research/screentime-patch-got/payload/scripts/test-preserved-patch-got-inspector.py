#!/usr/bin/env python3
"""Reject damaged real reconstructed code, bindings, and segment layout."""
from pathlib import Path
import copy
import json
import runpy
import struct
import unittest

root = Path(__file__).resolve().parent.parent
module = runpy.run_path(str(root / 'scripts/inspect-preserved-patch-got.py'))


class SerializedImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = json.loads((root/'config/coregraphics-image-pins.json').read_text())['appleidsso-patch-got-v4']
        cls.original = (root/('runtime/fullsystem-libraries'+cls.pin['path'])).read_bytes()
        folder = root/'runtime/rebuilt-appleidsso-patch-got-v4'
        cls.candidate = (folder/'AppleIDSSOAuthentication').read_bytes()
        cls.report = json.loads((folder/'reconstruction.json').read_text())

    def test_control(self):
        r = module['inspect'](self.original, self.candidate, self.report)
        self.assertEqual(r['got_cells_verified'], 144)
        self.assertEqual(r['nonzero_addends_verified'], 17)

    def test_original_instruction_byte_damage(self):
        damaged = bytearray(self.candidate)
        _, sections, _ = module['macho'](self.original)
        address, _, _, _ = sections['__TEXT', '__text']
        segments, _, _ = module['macho'](self.candidate)
        base = next(s[1] for s in module['macho'](self.original)[0] if s[0] == '__TEXT')
        text = next(s for s in segments if s[0] == '__TEXT')
        damaged[text[3] + address-base-text[1]] ^= 1
        with self.assertRaisesRegex(AssertionError, 'executable bytes differ'):
            module['inspect'](self.original, damaged, self.report)

    def test_serialized_binding_symbol_damage(self):
        damaged = bytearray(self.candidate)
        _, _, streams = module['macho'](damaged)
        offset, size = streams[2:4]
        at = damaged.index(b'_xpc_get_type\0', offset, offset+size)
        damaged[at+len('_xpc_get_type')-1] = ord('f')
        with self.assertRaisesRegex(AssertionError, 'Serialized binding differs'):
            module['inspect'](self.original, damaged, self.report)

    def test_overlapping_segment_damage(self):
        damaged = bytearray(self.candidate)
        cursor = 32
        for _ in range(struct.unpack_from('<I', damaged, 16)[0]):
            command, size = struct.unpack_from('<II', damaged, cursor)
            if command == 0x19 and damaged[cursor+8:cursor+24].rstrip(b'\0') == b'__PATCH_GOT':
                struct.pack_into('<Q', damaged, cursor+24, 0)
                break
            cursor += size
        else: self.fail('Missing candidate GOT segment')
        with self.assertRaisesRegex(AssertionError, 'Overlapping candidate segments'):
            module['inspect'](self.original, damaged, self.report)


if __name__ == '__main__':
    unittest.main(verbosity=2)
