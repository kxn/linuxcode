#!/usr/bin/env python3
"""Index and byte-preservation checks for extractor-appended indirect aliases."""
from pathlib import Path
import runpy
import struct
import unittest

root = Path(__file__).resolve().parent.parent
normalize = runpy.run_path(str(root/'scripts/normalize-dysymtab-aliases.py'))['normalize']


def fixture():
    strings = b'\0local\0defined\0undefined\0alias\0'
    offsets = [strings.index(s) for s in [b'local',b'defined',b'undefined',b'alias']]
    records = [(offsets[0],2,0,0,37),(offsets[1],3,0,0,43),
        (offsets[2],1,0,0x240,0),(offsets[3],0xb,0,0,offsets[3])]
    symbols = b''.join(struct.pack('<IBBHQ',*r) for r in records)
    dynamic = bytearray(struct.pack('<20I',0xb,80,0,1,1,1,2,1,*([0]*12)))
    struct.pack_into('<II',dynamic,56,4096,5)
    indirect = struct.pack('<5I',2,3,0,0x80000000,0xc0000000)
    return symbols, strings, dynamic, indirect


class AliasNormalization(unittest.TestCase):
    def test_reorders_whole_records_and_preserves_every_reference(self):
        a,s,d,i=fixture();b,e,j,p=normalize(a,s,d,i)
        self.assertEqual(bytes(b),a[:32]+a[48:64]+a[32:48])
        self.assertEqual(struct.unpack_from('<6I',e,8),(0,1,1,2,3,1))
        self.assertEqual(struct.unpack('<5I',j),(3,2,0,0x80000000,0xc0000000))
        self.assertEqual(p['appended_external_aliases'],1)
        self.assertEqual(p['remapped_indirect_entries'],2)
        self.assertEqual(bytes(e[:8])+bytes(e[32:]),bytes(d[:8])+bytes(d[32:]))

    def test_well_formed_tables_are_exact_noop(self):
        a,s,d,i=fixture();struct.pack_into('<I',d,60,1)
        result=normalize(a[:48],s,d,struct.pack('<I',2))
        self.assertEqual(tuple(map(bytes,result[:3])),(a[:48],s and bytes(d),struct.pack('<I',2)))
        self.assertFalse(result[3]['repaired'])

    def test_refuses_unmodelled_tail_and_alias_changes(self):
        for offset,value in [(4,1),(5,1),(6,1),(8,0),(8,9999)]:
            with self.subTest(offset=offset,value=value):
                a,s,d,i=fixture();a=bytearray(a)
                struct.pack_into('<B' if offset in (4,5) else '<H' if offset==6 else '<Q',a,48+offset,value)
                with self.assertRaises(ValueError):normalize(a,s,d,i)

    def test_refuses_index_bearing_side_tables(self):
        for field in [6,7,8,9,10,11,14,15,16,17]:
            with self.subTest(field=field):
                a,s,d,i=fixture();struct.pack_into('<I',d,8+4*field,1)
                with self.assertRaises(ValueError):normalize(a,s,d,i)

    def test_refuses_bad_indirect_index(self):
        a,s,d,i=fixture();i=struct.pack('<5I',4,3,0,0x80000000,0xc0000000)
        with self.assertRaises(ValueError):normalize(a,s,d,i)

    def test_refuses_noncontiguous_groups(self):
        a,s,d,i=fixture();struct.pack_into('<I',d,24,1)
        with self.assertRaises(ValueError):normalize(a,s,d,i)

    def test_refuses_truncated_tables(self):
        for part in [0,2,3]:
            a=list(fixture());a[part]=a[part][:-1]
            with self.assertRaises(ValueError):normalize(*a)

    def test_refuses_misclassified_existing_groups(self):
        for index,kind in [(0,3),(1,1),(2,3)]:
            a,s,d,i=fixture();a=bytearray(a);a[index*16+4]=kind
            with self.assertRaises(ValueError):normalize(a,s,d,i)


if __name__=='__main__':
    unittest.main(verbosity=2)
