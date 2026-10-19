#!/usr/bin/env python3
"""Verify exact reexport identity, ambiguity, renamed edges and malformed chains."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import runpy
import tempfile
import unittest

discover = runpy.run_path(str(Path(__file__).with_name('exact-reexport-imports.py')))['discover']


class ReexportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = {
            '/front': SimpleNamespace(dependencies=['/middle'], exports={'_public': ('reexport', 1, '_alias')}),
            '/middle': SimpleNamespace(dependencies=['/leaf'], exports={'_alias': ('reexport', 1, '_real')}),
            '/leaf': SimpleNamespace(dependencies=[], exports={'_real': ('address', 0x1000, 0)}),
        }
        for name in self.images:
            (self.root/name.lstrip('/')).write_bytes(name.encode())

    def run_discovery(self, wanted=None):
        return discover(self.images.__getitem__, ['/front'], wanted or {0x1000}, self.root)

    def test_renamed_chain_keeps_original_import_name_and_hashes_every_provider(self):
        exact, proof = self.run_discovery()
        self.assertEqual(exact, {0x1000: [['_public', '/front']]})
        self.assertEqual([s['symbol'] for s in proof['chains'][0]['chain']], ['_public', '_alias', '_real'])
        self.assertEqual(proof['original_provider_sha256'],
            {p: hashlib.sha256(p.encode()).hexdigest() for p in self.images})

    def test_no_nearest_address_matching(self):
        self.assertEqual(self.run_discovery({0x1001}), ({0x1001: []}, {'chains': [], 'original_provider_sha256': {}}))

    def test_folded_aliases_remain_ambiguous(self):
        self.images['/front'].exports['_other'] = ('reexport', 1, '_alias')
        self.assertEqual(len(self.run_discovery()[0][0x1000]), 2)

    def test_no_implicit_dependency_search(self):
        del self.images['/middle'].exports['_alias']
        self.assertEqual(self.run_discovery()[0], {0x1000: []})

    def test_invalid_ordinal_rejected(self):
        self.images['/middle'].exports['_alias'] = ('reexport', 2, '_real')
        with self.assertRaisesRegex(ValueError, 'ordinal'):
            self.run_discovery()

    def test_cycle_rejected(self):
        self.images['/middle'].dependencies = ['/front']
        self.images['/middle'].exports['_alias'] = ('reexport', 1, '_public')
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            self.run_discovery()


if __name__ == '__main__':
    unittest.main(verbosity=2)
