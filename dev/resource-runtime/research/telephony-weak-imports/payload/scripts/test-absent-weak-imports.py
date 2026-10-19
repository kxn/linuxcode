#!/usr/bin/env python3
"""Independent packed Mach-O cases for absent weak-provider auditing."""
from pathlib import Path
import runpy
import struct
import tempfile
import unittest

audit = runpy.run_path(str(Path(__file__).with_name('absent-weak-imports.py')))['audit']

def fixture(command=0x80000018,desc=0x140,value=0):
    name = b'/absent/libOptional.dylib\0'
    size = (24+len(name)+7)&~7
    load = struct.pack('<6I',command,size,24,0,0x10000,0x10000)+name.ljust(size-24,b'\0')
    strings = b'\0_optional\0'
    symoff = 32+size+24
    symtab = struct.pack('<6I',2,24,symoff,1,symoff+16,len(strings))
    header = struct.pack('<8I',0xfeedfacf,0x1000007,3,6,2,size+24,0,0)
    return header+load+symtab+struct.pack('<IBBHQ',1,1,0,desc,value)+strings

def missing(path): raise KeyError(path)

class WeakImports(unittest.TestCase):
    def test_original_undefined_weak_and_absent_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            p = audit(fixture(),Path(folder),missing)
            self.assertEqual(p['dependencies'][0]['undefined_weak_symbols'],['_optional'])
            self.assertEqual(p['dependencies'][0]['load_command'],'0x80000018')

    def test_strong_load_is_never_classified_as_absent_weak(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(audit(fixture(command=0xc),Path(folder),missing)['dependencies'],[])

    def test_strong_symbol_and_nonzero_symbol_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for data in [fixture(desc=0x100),fixture(value=1)]:
                with self.assertRaises(ValueError): audit(data,Path(folder),missing)

    def test_existing_cached_provider_is_not_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(audit(fixture(),Path(folder),lambda path: object())['dependencies'],[])

    def test_existing_standalone_provider_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'absent/libOptional.dylib'
            path.parent.mkdir();path.write_bytes(b'provider-present')
            with self.assertRaises(ValueError): audit(fixture(),Path(folder),missing)

    def test_truncated_symbols_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): audit(fixture()[:-5],Path(folder),missing)

if __name__ == '__main__': unittest.main(verbosity=2)
