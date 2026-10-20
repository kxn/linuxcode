#!/usr/bin/env python3
"""Separate unmapped ancestor copies from verified current-stage launch inputs.

No libraries or old reports are changed. Historical hashes remain in the new
report and its original source report. Only explicitly linked ancestor trees
can move out of the files/links maps consumed by runtime profiles.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import runpy
import time

root=Path(__file__).resolve().parent.parent

def relative(name):
    path=Path(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected a workspace-relative path')
    return path

def stage_root(report):
    if 'frameworks' in report and 'libraries' in report:
        folder=relative(report['frameworks']).parent
        if (relative(report['frameworks'])!=folder/'frameworks'
                or relative(report['libraries'])!=folder/'libraries'
                or not folder.name.startswith('resource-framework-overlay-')):
            raise ValueError('Unsupported resource overlay layout')
        kind='overlay';parent='parent_overlay'
    else:
        path=relative(report['library'])
        if len(path.parents)<5:raise ValueError('Unsupported graphics stage layout')
        folder=path.parents[4]
        if not folder.name.startswith('coregraphics-native-'):
            raise ValueError('Unsupported graphics stage layout')
        kind='graphics';parent='parent_stage'
    if folder.parent!=Path('runtime'):
        raise ValueError('Stage must have its own top-level runtime tree')
    return folder,kind,parent

def compact(workspace,source_name,output_name,resolve):
    source=workspace/relative(source_name);output=workspace/relative(output_name)
    if output.exists():raise ValueError('Refusing to replace an existing report')
    raw=source.read_bytes();report=json.loads(raw);active,kind,parent_key=stage_root(report)
    digest=lambda p:hashlib.sha256((workspace/p).read_bytes()).hexdigest()
    ancestors=[];seen={str(relative(source_name))};entry=report
    while entry.get(parent_key):
        parent_name=str(relative(entry[parent_key]))
        if parent_name in seen:raise ValueError('Cyclic stage ancestry')
        seen.add(parent_name)
        if digest(parent_name)!=entry[parent_key+'_sha256']:
            raise ValueError('Ancestor report checksum changed')
        entry=json.loads((workspace/parent_name).read_text())
        folder,parent_kind,parent_field=stage_root(entry)
        if parent_kind!=kind or parent_field!=parent_key or folder==active:
            raise ValueError('Invalid ancestor stage family')
        ancestors.append(folder)
    for name,expected in report['files'].items():
        relative(name);resolve(name,expected)
    for name,target in report.get('links',{}).items():
        if os.readlink(workspace/relative(name))!=target:
            raise ValueError('Stage symlink changed: '+name)
    actual_files=set();actual_links=set()
    for path in (workspace/active).rglob('*'):
        name=str(path.relative_to(workspace))
        if path.is_symlink():
            actual_links.add(name)
            if not path.resolve(strict=True).is_relative_to((workspace/active).resolve()):
                raise ValueError('Current stage symlink escapes its verified tree')
        elif path.is_file():actual_files.add(name)
    current_files={name for name in report['files'] if relative(name).is_relative_to(active)}
    current_links={name for name in report.get('links',{}) if relative(name).is_relative_to(active)}
    if not actual_files or actual_files!=current_files or actual_links!=current_links:
        raise ValueError('Current stage inventory differs from the report')
    obsolete=lambda name:any(relative(name).is_relative_to(folder) for folder in ancestors)
    removed_files={name:sha for name,sha in report['files'].items() if obsolete(name)}
    removed_links={name:target for name,target in report.get('links',{}).items() if obsolete(name)}
    result=copy.deepcopy(report)
    for key,moved in [('historical_stage_files',removed_files),('historical_stage_links',removed_links)]:
        history=result.setdefault(key,{})
        for name,value in moved.items():
            if name in history and history[name]!=value:
                raise ValueError('Conflicting historical stage input')
            history[name]=value
    result['files']={name:sha for name,sha in report['files'].items() if name not in removed_files}
    result['links']={name:target for name,target in report.get('links',{}).items() if name not in removed_links}
    result['files'][str(relative(source_name))]=hashlib.sha256(raw).hexdigest()
    helper='scripts/compact-resource-stage-inputs.py'
    result['files'][helper]=digest(helper)
    result['runtime_input_compaction']=dict(source_report=str(relative(source_name)),
        source_report_sha256=hashlib.sha256(raw).hexdigest(),current_runtime_tree=str(active),
        ancestor_runtime_trees=[str(folder) for folder in ancestors],
        source_files_revalidated=len(report['files']),current_tree_files=len(current_files),
        unmapped_ancestor_files_moved=len(removed_files),unmapped_ancestor_links_moved=len(removed_links),
        unmapped_ancestor_bytes=sum((workspace/name).stat().st_size for name in removed_files),
        libraries_changed=False,old_reports_changed=False,historical_hashes_preserved=True,
        runtime_execution_verified=False,
        scope='Current launch inputs remain verified; ancestor copies remain historical evidence and are not claimed revalidated on every future launch.')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    return result['runtime_input_compaction']

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args();started=time.monotonic()
    resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
    proof=compact(root,args.stage,args.output,resolve)
    print(json.dumps(dict(report=args.output,elapsed_seconds=time.monotonic()-started,**proof),indent=2))

if __name__=='__main__':main()
