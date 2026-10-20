#!/usr/bin/env python3
"""Compare all Unity Data bytes after canonical filename normalization."""
from pathlib import Path
import argparse,hashlib,json,unicodedata
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--destination',required=True);p.add_argument('--report',required=True);a=p.parse_args();root=Path(__file__).resolve().parent.parent;dest=root/a.report;assert not dest.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(folder):
 assert folder.is_dir();files={};directories=set();spellings={};symlinks=[]
 for path in sorted(folder.rglob('*')):
  relative=str(path.relative_to(folder));key=unicodedata.normalize('NFC',relative)
  assert key not in spellings,('Ambiguous canonical names',key,spellings.get(key),relative)
  spellings[key]=relative
  if path.is_symlink():symlinks.append(relative)
  if path.is_dir():directories.add(key)
  elif path.is_file():files[key]=dict(bytes=path.stat().st_size,sha256=sha(path))
  else:raise ValueError('Unexpected non-file resource: '+relative)
 return files,directories,spellings,symlinks
s,sd,ss,sl=inventory(root/a.source);d,dd,ds,dl=inventory(root/a.destination);missing=sorted(set(s)-set(d));extra=sorted(set(d)-set(s));different=sorted(k for k in set(s)&set(d) if s[k]!=d[k]);verified=not missing and not extra and not different and sd==dd and not sl and not dl
report=dict(verified=verified,source=a.source,destination=a.destination,source_file_count=len(s),destination_file_count=len(d),source_directory_count=len(sd),destination_directory_count=len(dd),file_bytes_equal=not missing and not extra and not different,missing=missing,extra=extra,different=different,source_symlinks=sl,destination_symlinks=dl,filename_spellings_changed=sum(ss[k]!=ds[k] for k in set(s)&set(d)),normalization='NFC for comparison only; no files renamed or modified',files=s,verifier_source_sha256=sha(Path(__file__)),full_goal_complete=False);dest.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2));raise SystemExit(0 if verified else 1)
