#!/usr/bin/env python3
"""Reject malformed optimized TLS descriptors, including a real cache control."""
from pathlib import Path
from types import SimpleNamespace as S
import runpy
import struct
import unittest

root = Path(__file__).resolve().parent.parent
validate = runpy.run_path(str(root/'scripts/cache-tlv-optimization.py'))['validate']


class TLVTests(unittest.TestCase):
    def setUp(self):
        self.slot, self.bootstrap, self.start = 0x2000, 0x1000, 0x2100
        self.object = S(sections=[('__thread_vars', '__DATA', self.slot, 48, 0x13),
                                 ('__thread_bss', '__DATA', self.start, 64, 0x12)])
        self.export = dict(symbol='__tlv_bootstrap', provider='/usr/lib/system/libdyld.dylib', implementation=self.bootstrap)
        self.raw = struct.pack('<QIIiI', self.bootstrap+8, 133, 8, 0, 64)
        self.ns = dict(resolve=lambda path, name: self.bootstrap, read=lambda slot, size: self.raw)

    def check(self, **options):
        args = dict(ns=self.ns, original=self.object, slot=self.slot, export=self.export,
                    target=self.bootstrap+8, expected=self.bootstrap, flags=0)
        args.update(options)
        return validate(**args)

    def test_zero_fill_descriptor(self):
        p = self.check()
        self.assertEqual((p['variable_offset'], p['template_size'], p['cache_key']), (8, 64, 133))
        self.assertTrue(p['requires_disk_ABI_restoration'])

    def test_initialized_descriptor_requires_its_exact_relative_template(self):
        self.object.sections[1] = ('__thread_data', '__DATA', self.start, 64, 0x11)
        self.raw = struct.pack('<QIIiI', self.bootstrap+8, 133, 8, self.start-self.slot-16, 64)
        self.check()
        self.raw = struct.pack('<QIIiI', self.bootstrap+8, 133, 8, 0, 64)
        with self.assertRaises(ValueError): self.check()

    def test_wrong_entry_flags_or_provider(self):
        for options in [dict(target=self.bootstrap+16), dict(flags=0x100),
                        dict(export={**self.export, 'provider': '/unrelated'}),
                        dict(export={**self.export, 'symbol': '_another_function'})]:
            with self.subTest(options=options), self.assertRaises(ValueError): self.check(**options)

    def test_wrong_export_identity(self):
        with self.assertRaises(ValueError): self.check(expected=self.bootstrap+8, target=self.bootstrap+16)

    def test_requires_complete_aligned_typed_descriptor(self):
        with self.assertRaises(ValueError): self.check(slot=self.slot+8)
        self.object.sections[0] = ('__thread_vars', '__DATA', self.slot, 47, 0x13)
        with self.assertRaises(ValueError): self.check()
        self.object.sections[0] = ('__const', '__DATA', self.slot, 48, 0)
        with self.assertRaises(ValueError): self.check()

    def test_template_extent_offset_and_delta(self):
        for offset, delta, size in [(64, 0, 64), (8, 1, 64), (8, 0, 63)]:
            self.raw = struct.pack('<QIIiI', self.bootstrap+8, 133, offset, delta, size)
            with self.subTest(offset=offset, delta=delta, size=size), self.assertRaises(ValueError): self.check()

    def test_missing_template(self):
        self.object.sections = self.object.sections[:1]
        with self.assertRaises(ValueError): self.check()

    def test_real_security_patch_table_and_corrupt_template_control(self):
        ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
            'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
            'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
        reader = runpy.run_path(str(root/'scripts/cache-patch-metadata.py'))['read_image_bindings']
        provider = '/System/Library/Frameworks/Security.framework/Versions/A/Security'
        metadata = reader(ns, provider)
        rows = metadata['optimized_tlv_records']
        self.assertEqual(len(rows), 2)
        slot = int(rows[0]['slot'], 16)
        original_read = ns['read']
        original = original_read(slot, 24)
        def corrupted(address, length):
            data = original_read(address, length)
            if address == slot and length == 24:
                bad = bytearray(data)
                bad[20] ^= 1
                return bytes(bad)
            return data
        changed = {**ns, 'read': corrupted}
        with self.assertRaisesRegex(ValueError, 'template bounds'):
            reader(changed, provider)
        self.assertEqual(original_read(slot, 24), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
