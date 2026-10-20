#!/usr/bin/env python3
"""Exercise launch-input guards with isolated metadata and file-tree fixtures."""
from pathlib import Path
import copy
import hashlib
import json
import os
import runpy
import tempfile
import unittest

root=Path(__file__).resolve().parent.parent
module=runpy.run_path(str(root/'scripts/compact-resource-stage-inputs.py'))

class StageInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='stage-input-tests-',dir=root/'runtime')
        self.folder=Path(self.tmp.name)
        self.helper='scripts/compact-resource-stage-inputs.py'
        self.write(self.helper,(root/self.helper).read_bytes())
        self.old=Path('runtime/coregraphics-native-test-old')
        self.active=Path('runtime/coregraphics-native-test-current')
        self.tail=Path('frameworks/CoreGraphics.framework/Versions/A/CoreGraphics')
        self.write(str(self.old/self.tail),b'old metadata fixture; not a Mach-O library\n')
        self.write(str(self.active/self.tail),b'current metadata fixture; not a Mach-O library\n')
        self.extra='runtime/coregraphics-native-unrelated/input.json';self.write(self.extra,b'{}\n')
        (self.folder/self.active/'frameworks/CoreGraphics.framework/CoreGraphics').symlink_to('Versions/A/CoreGraphics')
        self.link=str(self.active/'frameworks/CoreGraphics.framework/CoreGraphics')
        self.write('artifacts/old.json',json.dumps(dict(library=str(self.old/self.tail),files={str(self.old/self.tail):self.sha(str(self.old/self.tail))})).encode())
        self.report=dict(library=str(self.active/self.tail),parent_stage='artifacts/old.json',
            parent_stage_sha256=self.sha('artifacts/old.json'),files={name:self.sha(name) for name in [str(self.old/self.tail),str(self.active/self.tail),self.extra]},
            links={self.link:'Versions/A/CoreGraphics'})
    def tearDown(self):self.tmp.cleanup()
    def write(self,name,data):
        p=self.folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    def sha(self,name):return hashlib.sha256((self.folder/name).read_bytes()).hexdigest()
    def run_case(self,report=None):
        self.write('artifacts/current.json',json.dumps(report or self.report).encode())
        def resolve(name,expected):
            if self.sha(name)!=expected:raise ValueError('Current input checksum changed')
        return module['compact'](self.folder,'artifacts/current.json','artifacts/compact.json',resolve)
    def test_only_explicit_ancestor_copies_move_and_all_hashes_survive(self):
        before=self.sha(str(self.active/self.tail));proof=self.run_case();out=json.loads((self.folder/'artifacts/compact.json').read_text())
        self.assertEqual(proof['unmapped_ancestor_files_moved'],1)
        self.assertEqual(out['historical_stage_files'],{str(self.old/self.tail):self.report['files'][str(self.old/self.tail)]})
        self.assertIn(self.extra,out['files']);self.assertIn(str(self.active/self.tail),out['files'])
        self.assertEqual(before,self.sha(str(self.active/self.tail)))
    def test_changed_selected_file_is_rejected(self):
        self.write(str(self.active/self.tail),b'changed current input')
        with self.assertRaisesRegex(ValueError,'checksum changed'):self.run_case()
    def test_changed_ancestor_input_is_checked_before_compaction(self):
        self.write(str(self.old/self.tail),b'changed ancestor input')
        with self.assertRaisesRegex(ValueError,'checksum changed'):self.run_case()
    def test_missing_selected_inventory_entry_is_rejected(self):
        report=copy.deepcopy(self.report);del report['files'][str(self.active/self.tail)]
        with self.assertRaisesRegex(ValueError,'inventory'):self.run_case(report)
    def test_changed_parent_report_is_rejected(self):
        self.write('artifacts/old.json',b'{}\n')
        with self.assertRaisesRegex(ValueError,'Ancestor report checksum'):self.run_case()
    def test_external_selected_symlink_is_rejected(self):
        p=self.folder/self.link;p.unlink();p.symlink_to(self.folder/self.old/self.tail)
        report=copy.deepcopy(self.report);report['links'][self.link]=os.readlink(p)
        with self.assertRaisesRegex(ValueError,'escapes'):self.run_case(report)
    def test_cycle_is_rejected(self):
        report=copy.deepcopy(self.report);report['parent_stage']='artifacts/current.json'
        with self.assertRaisesRegex(ValueError,'Cyclic'):self.run_case(report)
    def test_existing_report_is_preserved(self):
        self.write('artifacts/compact.json',b'keep existing report\n')
        with self.assertRaisesRegex(ValueError,'replace'):self.run_case()
        self.assertEqual((self.folder/'artifacts/compact.json').read_bytes(),b'keep existing report\n')
    def test_explicit_original_overlay_ancestor_can_have_its_legacy_name(self):
        old=Path('runtime/security-resource-original-test')
        active=Path('runtime/resource-framework-overlay-test-current')
        oldfile=str(old/'frameworks/fixture.json');newfile=str(active/'frameworks/fixture.json')
        self.write(oldfile,b'old metadata fixture\n');self.write(newfile,b'current metadata fixture\n')
        (self.folder/active/'libraries').mkdir()
        self.write('artifacts/overlay-old.json',json.dumps(dict(frameworks=str(old/'frameworks'),
            libraries=str(old/'libraries'),files={oldfile:self.sha(oldfile)})).encode())
        report=dict(frameworks=str(active/'frameworks'),libraries=str(active/'libraries'),
            parent_overlay='artifacts/overlay-old.json',parent_overlay_sha256=self.sha('artifacts/overlay-old.json'),
            files={p:self.sha(p) for p in [oldfile,newfile]},links={})
        proof=self.run_case(report)
        self.assertEqual(proof['unmapped_ancestor_files_moved'],1)
        self.assertEqual(proof['current_runtime_tree'],str(active))

if __name__=='__main__':unittest.main(verbosity=2)
