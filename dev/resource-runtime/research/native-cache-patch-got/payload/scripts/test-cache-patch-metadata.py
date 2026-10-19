#!/usr/bin/env python3
"""Check v4 patch parsing against a small independent packed binary fixture."""
from pathlib import Path
from types import SimpleNamespace as S
import runpy
import struct
import unittest

module = runpy.run_path(str(Path(__file__).with_name('cache-patch-metadata.py')))


class Table:
    def __init__(self):
        self.address = 0x900000
        self.implementation = 0x200040
        self.client = 0x100000
        self.slot = self.client + 0x20
        self.got = self.client + 0x3000
        arrays = [
            ('images', struct.pack('<8I', 0, 0, 0, 0, 0, 1, 0, 1), 2),
            ('exports', struct.pack('<II', 0x40, 0), 1),
            ('clients', struct.pack('<III', 0, 0, 1), 1),
            ('client_exports', struct.pack('<III', 0, 0, 1), 1),
            ('locations', struct.pack('<II', 0x20, 3 << 9), 1),
            ('names', b'_test\0', 6),
            ('got_clients', struct.pack('<4I', 0, 0, 0, 1), 2),
            ('got_exports', struct.pack('<III', 0, 0, 1), 1),
            ('got_locations', struct.pack('<QII', 0x3000, 0x100, 0), 1),
        ]
        self.data = bytearray(152)
        self.offsets = {}
        fields = []
        for name, payload, count in arrays:
            self.offsets[name] = len(self.data)
            fields += [self.address + len(self.data), count]
            self.data.extend(payload)
        struct.pack_into('<II18Q', self.data, 0, 4, 0, *fields)
        self.header = S(patchInfoAddr=self.address, patchInfoSize=len(self.data), sharedRegionStart=self.client)
        images = [S(address=self.client, pathFileOffset=0), S(address=0x200000, pathFileOffset=1)]
        self.context = S(header=self.header, images=images, readString=lambda off: b'/provider\0')
        self.original = S(base=self.client, sections=[('__text', '__TEXT', self.client, 0x100, 0x80000400)],
            segments=[('__TEXT', self.client, 0x100, 0, 0x100)])
        self.pointers = {self.slot: self.implementation + 3, self.got: self.implementation}
        self.resolved = self.implementation
        self.ns = dict(cache=dict(contexts=[self.context]),
            read=self.read, image=lambda path: self.original,
            pointer=lambda addr: self.pointers[addr], resolve=lambda path, name: self.resolved)
        self.imports = {self.implementation: [('_test', 7, False)]}

    def read(self, address, length):
        assert address == self.address and length == len(self.data)
        return self.data

    def parse(self, got=True):
        return module['read_image_bindings'](self.ns, '/client', self.imports if got else None)

    def set(self, array, offset, fmt, *values):
        struct.pack_into(fmt, self.data, self.offsets[array] + offset, *values)


class PatchTests(unittest.TestCase):
    def test_exact_addend_and_image_ordinal(self):
        t = Table()
        m = t.parse()
        self.assertEqual(module['addend_imports'](m, t.imports), {t.slot: ('_test', 7, False, 3)})

    def test_pooled_identity_retains_this_images_weak_semantics(self):
        t = Table()
        m = t.parse()
        self.assertTrue(m['got_records'][0]['weak_import'])
        self.assertEqual(module['exact_imports'](m['got_records'], t.imports, pooled=True),
            {t.got: ('_test', 7, False, 0)})

    def test_version_and_location_version_rejected(self):
        for version, locations in [(3, 0), (4, 1)]:
            t = Table()
            struct.pack_into('<II', t.data, 0, version, locations)
            with self.assertRaises(ValueError): t.parse()

    def test_array_and_subrange_bounds(self):
        t = Table()
        struct.pack_into('<Q', t.data, 8, t.address + len(t.data) + 1)
        with self.assertRaises(ValueError): t.parse()
        t = Table()
        t.set('clients', 8, '<I', 2)
        with self.assertRaises(ValueError): t.parse()

    def test_client_and_provider_indexes_rejected(self):
        for array, offset in [('clients', 0), ('client_exports', 0), ('got_exports', 0)]:
            t = Table()
            t.set(array, offset, '<I', 9)
            with self.assertRaises(ValueError): t.parse()

    def test_unterminated_and_out_of_bounds_names(self):
        t = Table()
        t.data[t.offsets['names'] + 5] = ord('X')
        with self.assertRaises(ValueError): t.parse()
        t = Table()
        t.set('exports', 4, '<I', 6)
        with self.assertRaises(ValueError): t.parse()

    def test_pointer_and_export_must_both_match(self):
        for got in [False, True]:
            t = Table()
            t.pointers[t.got if got else t.slot] += 1
            with self.assertRaises(ValueError): t.parse()
        t = Table()
        t.resolved += 1
        with self.assertRaises(ValueError): t.parse()

    def test_authenticated_locations_and_got_padding_rejected(self):
        for array, offset, value in [('locations', 4, 1), ('got_locations', 8, 1),
                                    ('got_locations', 12, 1)]:
            t = Table()
            t.set(array, offset, '<I', value)
            with self.assertRaises(ValueError): t.parse()

    def test_no_nearest_symbol_fallback_or_ambiguous_ordinal(self):
        t = Table()
        m = t.parse()
        for imports in [{t.implementation + 1: [('_test', 7, False)]},
                        {t.implementation: [('_other', 7, False)]},
                        {t.implementation: [('_test', 7, False), ('_test', 8, False)]}]:
            with self.assertRaises(ValueError): module['addend_imports'](m, imports)

    def test_conflicting_original_slot_rejected(self):
        t = Table()
        m = t.parse()
        record = m['records'][0]
        m['records'].append({**record, 'addend': 4})
        with self.assertRaises(ValueError): module['addend_imports'](m, t.imports)

    def test_other_pool_outside_rip_reach_not_copied(self):
        t = Table()
        t.set('got_locations', 0, '<Q', 1 << 33)
        self.assertEqual(t.parse()['got_records'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
