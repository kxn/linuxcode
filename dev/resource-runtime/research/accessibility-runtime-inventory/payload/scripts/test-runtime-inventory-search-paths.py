#!/usr/bin/env python3
"""Resolve real Mach-O fixtures through isolated inventory search-path trees."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

root=Path(__file__).resolve().parent.parent

class InventorySearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='inventory-search-tests-',dir=root/'runtime')
        self.workspace=Path(self.tmp.name)/'workspace'
        (self.workspace/'scripts').mkdir(parents=True)
        shutil.copy2(root/'scripts/inventory-runtime-dependencies.py',self.workspace/'scripts/inventory-runtime-dependencies.py')
        for name in ['runtime/state/prefix','runtime/private','runtime/frameworks','runtime/libraries','artifacts']:
            (self.workspace/name).mkdir(parents=True)
    def tearDown(self):self.tmp.cleanup()
    def fixture(self,path,source):
        p=self.workspace/path;p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(root/source)
    def inventory(self,seed):
        output=self.workspace/'artifacts/result.json'
        result=subprocess.run([sys.executable,'scripts/inventory-runtime-dependencies.py',
            '--seed',seed,'--runtime-root',str(self.workspace/'runtime/private'),
            '--framework-stage',str(self.workspace/'runtime/frameworks'),
            '--library-stage',str(self.workspace/'runtime/libraries'),'--output',str(output)],
            cwd=self.workspace,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(output.read_text())
    def test_embedded_original_dylib_uses_library_path(self):
        source='runtime/coregraphics-native-v128/libraries/libSessionUtility.dylib'
        self.fixture('runtime/libraries/libSessionUtility.dylib',source)
        self.fixture('runtime/frameworks/AudioSession.framework/libSessionUtility.dylib',source)
        report=self.inventory('/System/Library/PrivateFrameworks/AudioSession.framework/libSessionUtility.dylib')
        row=next(x for x in report['images'] if x['image'].endswith('AudioSession.framework/libSessionUtility.dylib'))
        self.assertEqual(row['host'],'runtime/libraries/libSessionUtility.dylib')
    def test_vision_embedded_original_dylib_is_not_missing(self):
        self.fixture('runtime/libraries/libfaceCore.dylib','runtime/rebuilt-vision-closure-libfacecore-resource-v2/libfaceCore.dylib')
        report=self.inventory('/System/Library/Frameworks/Vision.framework/libfaceCore.dylib')
        self.assertTrue(any(x['host']=='runtime/libraries/libfaceCore.dylib' for x in report['images']))
        self.assertFalse(any(x['name'].endswith('Vision.framework/libfaceCore.dylib') for x in report['missing_required_images']))
    def test_real_framework_uses_framework_path(self):
        source='runtime/rebuilt-avfoundation-reexport-facade-v2/AVFoundation'
        self.fixture('runtime/frameworks/AVFoundation.framework/AVFoundation',source)
        report=self.inventory('/System/Library/Frameworks/AVFoundation.framework/Versions/A/AVFoundation')
        row=next(x for x in report['images'] if x['image'].endswith('/AVFoundation'))
        self.assertEqual(row['host'],'runtime/frameworks/AVFoundation.framework/AVFoundation')
    def test_nested_framework_uses_innermost_framework_name(self):
        source='runtime/rebuilt-avfoundation-reexport-facade-v2/AVFoundation'
        self.fixture('runtime/frameworks/AVFoundation.framework/AVFoundation',source)
        report=self.inventory('/System/Library/Frameworks/Outer.framework/Versions/A/Frameworks/AVFoundation.framework/Versions/A/AVFoundation')
        self.assertEqual(report['images'][0]['host'],'runtime/frameworks/AVFoundation.framework/AVFoundation')

if __name__=='__main__':unittest.main(verbosity=2)
