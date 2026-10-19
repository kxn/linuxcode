#!/usr/bin/env python3
"""Exercise stub identity and reexport guards with independent packed cache data."""
from pathlib import Path
from types import SimpleNamespace as S
import copy
import runpy
import struct
import tempfile
import unittest

folder = Path(__file__).resolve().parent
Table = runpy.run_path(str(folder/'test-cache-patch-metadata.py'))['Table']
verify = runpy.run_path(str(folder/'verify-original-pooled-import.py'))['verify']


class OriginalPooledImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.t = Table()
        t = self.t
        t.set('got_locations', 8, '<I', 0)
        t.original.path = '/client'
        t.original.dependencies = ['/facade']
        t.original.exports = {}
        t.original.reexports = []
        self.stub = t.client+0x80
        t.original.sections.append(('__stubs', '__TEXT', self.stub, 6, 0x80000408))
        self.code = bytes.fromhex('ff25')+struct.pack('<i', t.got-self.stub-6)
        t.ns['read'] = lambda address, size: self.code if address == self.stub and size == 6 else t.read(address, size)
        self.images = {'/client': t.original,
            '/facade': S(path='/facade', dependencies=['/provider'], reexports=['/provider'], exports={}),
            '/provider': S(path='/provider', dependencies=[], reexports=[], exports={
                '_test': ('address', t.implementation, 0),
                '_alias': ('address', t.implementation, 0)})}
        t.ns['image'] = lambda path: self.images[path]
        for name in self.images:
            (self.root/name.lstrip('/')).write_text('original fixture '+name+'\n')

    def check(self, symbol='_test', provider='/facade'):
        return verify(self.t.ns, '/client', self.t.implementation,
                      [hex(self.t.got)], symbol, provider, self.root)

    def test_whole_library_reexport_uses_original_GOT_name(self):
        proof = self.check()
        self.assertEqual(proof['selected'], ['_test', '/facade'])
        self.assertEqual(proof['route'][0]['kind'], 'whole-library-reexport')
        self.assertEqual(proof['records'][0]['symbol'], '_test')
        self.assertEqual(len(proof['stubs']), 1)

    def test_folded_function_alias_is_not_selected(self):
        with self.assertRaises(AssertionError):
            self.check('_alias')

    def test_matching_address_without_reexport_edge_is_rejected(self):
        self.images['/facade'].reexports = []
        with self.assertRaises(AssertionError):
            self.check()

    def test_provider_must_be_an_original_direct_dependency(self):
        with self.assertRaises(AssertionError):
            self.check(provider='/provider')

    def test_changed_original_pointer_is_rejected(self):
        self.t.pointers[self.t.got] += 1
        with self.assertRaises(AssertionError):
            self.check()

    def test_wrong_stub_displacement_is_rejected(self):
        self.code = bytes.fromhex('ff25')+struct.pack('<i', self.t.got-self.stub+2)
        with self.assertRaises(AssertionError):
            self.check()

    def test_changed_patch_symbol_is_rejected(self):
        self.t.data[self.t.offsets['names']+1] = ord('X')
        with self.assertRaises(AssertionError):
            self.check()

    def test_pooled_weak_semantics_are_not_guessed(self):
        self.t.set('got_locations', 8, '<I', 0x100)
        with self.assertRaises(AssertionError):
            self.check()

    def test_explicit_rename_requires_the_actual_terminal_symbol(self):
        self.images['/facade'].exports['_public'] = ('reexport', 1, '_test')
        proof = self.check('_public')
        self.assertEqual(proof['records'][0]['symbol'], '_test')
        self.assertEqual(proof['route'][0]['kind'], 'symbol-reexport')
        self.images['/facade'].exports['_public'] = ('reexport', 1, '_alias')
        with self.assertRaises(AssertionError):
            self.check('_public')

    def test_changed_provider_bytes_change_the_recomputed_proof(self):
        proof = self.check()
        (self.root/'provider').write_text('different original provider bytes\n')
        self.assertNotEqual(self.check(), proof)

    def test_reexport_cycle_is_rejected(self):
        self.images['/facade'].dependencies = ['/facade']
        self.images['/facade'].reexports = ['/facade']
        with self.assertRaises(AssertionError):
            self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
