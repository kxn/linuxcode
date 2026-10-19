#!/usr/bin/env python3
"""Reconstruct selected pinned resource images on Linux; never run Darling or install them."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, subprocess, sys, uuid
here=Path(__file__).resolve().parent
manifest=json.loads((here/'overlay.json').read_text())
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--workspace',required=True,type=Path)
parser.add_argument('--target',action='append',choices=manifest['targets'])
parser.add_argument('--plan',action='store_true')
parser.add_argument('--stage-tag',help='After successful reconstruction, copy this selected set into a new private stage')
args=parser.parse_args();workspace=args.workspace.expanduser().resolve(strict=True)
commands=[]
for target in args.target or manifest['targets']:
 commands.append([sys.executable,str(workspace/'scripts/rebuild-c-cache-image.py'),
  '--target-manifest',str(workspace/'config/ios-resource-image-pins.json'),'--target',target,
  *manifest['build_arguments'][target]])
stage_command=None
if args.stage_tag:
 stage_command=[sys.executable,str(workspace/'scripts/stage-ios-resource-closure.py'),'--tag',args.stage_tag]
 for target in args.target or manifest['targets']:stage_command+=['--target',target]
if args.plan:
 print(json.dumps({'workspace':str(workspace),'commands':commands+([stage_command] if stage_command else []),'Darling_execution':False,'runtime_installation':False},indent=2))
else:
 logs=workspace/'logs'/('developer-resources-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]);logs.mkdir(parents=True)
 results=[]
 for target,command in zip(args.target or manifest['targets'],commands):
  log=logs/(target+'.log')
  with log.open('w') as stream:r=subprocess.run(command,cwd=workspace,stdout=stream,stderr=subprocess.STDOUT)
  results.append(dict(target=target,command=command,exit_status=r.returncode,log=str(log.relative_to(workspace)),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
  (logs/'result.json').write_text(json.dumps(dict(cases=results,expected_targets=args.target or manifest['targets'],Darling_execution=False,runtime_installation=False),indent=2)+'\n')
  print(target,'OK' if r.returncode==0 else 'FAILED',str(log),flush=True)
  if r.returncode:
   print(log.read_text()[-2000:],file=sys.stderr);raise SystemExit(r.returncode)
 if stage_command:subprocess.run(stage_command,cwd=workspace,check=True)
