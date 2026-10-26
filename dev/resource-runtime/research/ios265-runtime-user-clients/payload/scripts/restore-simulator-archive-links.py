#!/usr/bin/env python3
"""Restore relative runtime symlinks rejected by 7-Zip after matching archive metadata."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,posixpath,os
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--listing',required=True);p.add_argument('--extraction-log',required=True);p.add_argument('--report',required=True);a=p.parse_args();root=Path(a.root).resolve();report=Path(a.report);assert not report.exists();expected={}
for line in Path(a.extraction_log).read_text().splitlines():
 if line.startswith('ERROR:'):
  prefix=next((x for x in ['ERROR: Dangerous link path was ignored : ','ERROR: Dangerous link via another link was ignored : '] if line.startswith(x)),None);assert prefix,line;name,target=line[len(prefix):].split(' : ',1);assert name not in expected;expected[name]=target
assert expected;found={};current=None;h=hashlib.sha256()
with Path(a.listing).open('rb') as f:
 for raw in f:
  h.update(raw);line=raw.decode().rstrip('\n\r')
  if line.startswith('Path = '):current=line[7:]
  elif line.startswith('Symbolic Link = ') and current in expected:
   target=line[len('Symbolic Link = '):];assert posixpath.normpath(target)==posixpath.normpath(expected[current]),(current,target,expected[current]);found[current]=target
assert found.keys()==expected.keys()
for name,target in found.items():
 path=PurePosixPath(name);assert not path.is_absolute() and '..' not in path.parts and not target.startswith('/')
 boundary=str(path).split('/Contents/Resources/RuntimeRoot/')[0]+'/Contents/Resources/RuntimeRoot/'
 assert '/Contents/Resources/RuntimeRoot/' in name and posixpath.normpath(str(path.parent/target)).startswith(boundary)
 dest=root.joinpath(*path.parts);assert dest.parent.resolve().is_relative_to(root)
 if dest.is_symlink():assert os.readlink(dest)==target;continue
 if dest.exists():assert dest.is_file() and dest.stat().st_size==0,name;dest.unlink()
 dest.symlink_to(target)
report.write_text(json.dumps(dict(verified=True,restored_links=found,restored_count=len(found),archive_listing_sha256=h.hexdigest(),original_link_text_preserved=True,no_outside_root_writes=True,full_goal_complete=False),indent=2)+'\n');print('RESTORED',len(found),'original symlinks')
