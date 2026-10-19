#!/usr/bin/env python3
"""Check overlay isolation using temporary clones of a fixed local Git object."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, stat, subprocess, sys, tempfile, unittest
HERE=Path(__file__).resolve().parent.parent
MANIFEST=json.loads((HERE/'overlay.json').read_text())
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',required=True,type=Path)
OPTIONS,remaining=parser.parse_known_args();BASE=OPTIONS.base.resolve(strict=True)
assert subprocess.check_output(['git','-C',str(BASE),'rev-parse','HEAD'],text=True).strip()==MANIFEST['base']['commit']

def run(*args,**kwargs):return subprocess.run(list(args),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,**kwargs)

class OverlayChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name);self.workspace=self.folder/'workspace'
  subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(BASE),str(self.workspace)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  subprocess.run(['git','-C',str(self.workspace),'-c','advice.detachedHead=false','checkout','--quiet','--detach',MANIFEST['base']['commit']],check=True)
 def tearDown(self):self.tmp.cleanup()
 def call(self,*args,success=True):
  result=run(sys.executable,str(HERE/'apply-overlay.py'),'--workspace',str(self.workspace),*args)
  if success:self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
  self.assertNotEqual(result.returncode,0);return result
 def snapshot(self):
  result={}
  for name in MANIFEST['files']:
   p=self.workspace/name
   result[name]=(hashlib.sha256(p.read_bytes()).hexdigest(),stat.S_IMODE(p.stat().st_mode)) if p.is_file() else None
  return result
 def test_plan_never_changes_files_or_creates_backups(self):
  before=self.snapshot();result=self.call('--plan')
  self.assertFalse(result['changed']);self.assertEqual(set(result['files_to_change']),set(MANIFEST['files']))
  self.assertEqual(before,self.snapshot());self.assertFalse((self.workspace/'.linuxcode-overlays').exists())
 def test_apply_repeat_and_exact_rollback_preserve_permissions(self):
  p=self.workspace/'scripts/rebuild-c-cache-image.py';p.chmod(0o664);before=self.snapshot();result=self.call()
  self.assertTrue(result['changed']);self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o664)
  for name,entry in MANIFEST['files'].items():self.assertEqual(hashlib.sha256((self.workspace/name).read_bytes()).hexdigest(),entry['sha256'])
  self.assertFalse(self.call()['changed']);self.assertFalse(self.call('--plan')['changed'])
  self.assertTrue(self.call('--rollback',result['backup'])['rolled_back']);self.assertEqual(before,self.snapshot())
 def test_late_target_conflict_is_detected_before_any_change(self):
  name=list(MANIFEST['files'])[-1];p=self.workspace/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('developer source\n')
  before=self.snapshot();result=self.call(success=False)
  self.assertIn('Developer changes preserved',result.stderr);self.assertEqual(before,self.snapshot());self.assertFalse((self.workspace/'.linuxcode-overlays').exists())
 def test_staged_edit_is_preserved_even_when_worktree_matches_baseline(self):
  name='scripts/rebuild-c-cache-image.py';p=self.workspace/name;original=p.read_bytes();p.write_bytes(original+b'\n# staged developer edit\n')
  subprocess.run(['git','-C',str(self.workspace),'add','--',name],check=True);p.write_bytes(original)
  before=subprocess.check_output(['git','-C',str(self.workspace),'diff','--cached','--binary']);files=self.snapshot();result=self.call(success=False)
  self.assertIn('Staged developer changes preserved',result.stderr);self.assertEqual(files,self.snapshot())
  self.assertEqual(before,subprocess.check_output(['git','-C',str(self.workspace),'diff','--cached','--binary']))
 def test_symlink_target_is_preserved_and_never_followed(self):
  name='scripts/rebuild-c-cache-image.py';p=self.workspace/name;p.unlink();outside=self.folder/'outside.py';outside.write_text('outside developer file\n');p.symlink_to(outside)
  result=self.call(success=False);self.assertIn('symlink',result.stderr);self.assertTrue(p.is_symlink());self.assertEqual(outside.read_text(),'outside developer file\n');self.assertFalse((self.workspace/'.linuxcode-overlays').exists())
 def test_rollback_refuses_later_developer_edits(self):
  result=self.call();p=self.workspace/'scripts/rebuild-c-cache-image.py';p.write_bytes(p.read_bytes()+b'\n# later developer edit\n');before=self.snapshot()
  failed=self.call('--rollback',result['backup'],success=False);self.assertIn('later developer edits',failed.stderr);self.assertEqual(before,self.snapshot())
 def test_changed_checkpoint_is_rejected_before_mutation(self):
  p=self.workspace/'checkpoint/source-manifest.json';p.write_bytes(p.read_bytes()+b'\n');before=self.snapshot();result=self.call(success=False)
  self.assertIn('checkpoint changed',result.stderr);self.assertEqual(before,self.snapshot());self.assertFalse((self.workspace/'.linuxcode-overlays').exists())
 def test_unrelated_staged_work_is_unchanged_by_apply_and_rollback(self):
  p=self.workspace/'developer-notes.txt';p.write_text('keep staged notes\n');subprocess.run(['git','-C',str(self.workspace),'add','--',p.name],check=True)
  before=subprocess.check_output(['git','-C',str(self.workspace),'diff','--cached','--binary']);result=self.call();self.call('--rollback',result['backup'])
  self.assertEqual(before,subprocess.check_output(['git','-C',str(self.workspace),'diff','--cached','--binary']));self.assertEqual(p.read_text(),'keep staged notes\n')

if __name__=='__main__':unittest.main(argv=[sys.argv[0],*remaining])
