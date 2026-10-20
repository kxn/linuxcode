#!/usr/bin/env python3
"""Check convergence against real original exports and adversarial export graphs."""
from pathlib import Path
import argparse, copy, hashlib, json, runpy
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
out=root/args.output;assert not out.exists()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
verify=runpy.run_path(str(root/'scripts/equivalent-original-reexports.py'))['verify']
audit=json.loads((root/'artifacts/remoteui-original-coalesced-reexport-import-audit-v1.json').read_text())
rows=[row for row in audit['rows'] if row.get('equivalent_reexport_proof')];assert len(rows)==1
row=rows[0];target=int(row['target'],16);choices=row['exports'];libraries=root/'runtime/fullsystem-libraries'
proof=verify(ns['image'],choices,target,libraries);assert proof==row['equivalent_reexport_proof']
forward=next(chain[0] for chain in proof['chains'] if len(chain)>1)
provider=forward['provider'];name=forward['symbol'];original=ns['image'](provider)
def changed(value, dependencies=None):
    node=copy.copy(original);node.exports=dict(original.exports);node.exports[name]=value
    if dependencies is not None:node.dependencies=dependencies
    return lambda path:node if path==provider else ns['image'](path)
# The same address in two definitions does not prove identity.
assert verify(changed(('address',target,0)),choices,target,libraries) is None
assert verify(ns['image'],choices,target+8,libraries) is None
different_names=copy.deepcopy(choices);different_names[0][0]+='-different'
assert verify(ns['image'],different_names,target,libraries) is None
assert verify(changed(None),choices,target,libraries) is None
for value,deps,word in [(('reexport',len(original.dependencies)+1,''),None,'ordinal'),
                         (('reexport',1,''),[provider],'Cyclic')]:
    try:verify(changed(value,deps),choices,target,libraries)
    except ValueError as error:assert word in str(error)
    else:raise AssertionError('Accepted invalid export graph')
report=dict(verified=True,original_import_rows=len(audit['rows']),original_convergent_rows=len(rows),
    selected=proof['selected'],same_address_separate_definitions_rejected=True,
    renamed_symbols_rejected=True,wrong_target_rejected=True,missing_export_rejected=True,
    invalid_ordinal_rejected=True,cyclic_reexport_rejected=True,
    controls_are_in_memory_export_graph_mutations=True,
    source_sha256={n:sha(n) for n in ['scripts/equivalent-original-reexports.py',
        'scripts/test-equivalent-original-reexports.py','artifacts/remoteui-original-coalesced-reexport-import-audit-v1.json']})
out.write_text(json.dumps(report,indent=2)+'\n');print('VERIFIED one real convergent export and six rejecting controls')
