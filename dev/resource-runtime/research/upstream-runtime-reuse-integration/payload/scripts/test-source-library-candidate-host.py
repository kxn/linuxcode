#!/usr/bin/env python3
"""Exercise the production first-run source-library gate without starting Darling."""
from pathlib import Path
import argparse,ast,copy,hashlib,json,runpy,subprocess,sys,tempfile,types

root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',default='runtime/libunwind-common-source-reuse-v1/build.json')
p.add_argument('--output',required=True)
a=p.parse_args();source=root/'scripts/direct-resource-tool-runtime-profile.py'
tree=ast.parse(source.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_source_build_candidate')
queries=[]
def check_output(*args,**kwargs):
 queries.append(args[0]);return subprocess.check_output(*args,**kwargs)
sys.modules.pop('_linuxcode_source_candidate_symbols_v1',None)
namespace=dict(Path=Path,root=root,json=json,subprocess=types.SimpleNamespace(check_output=check_output),sys=sys,types=types)
exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),namespace)
validate=namespace[function.name];digest=runpy.run_path(str(root/'scripts/verified-file-digest.py'))['digest'];resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
build=json.loads((root/a.build).read_text())
selected=dict(component='libunwind',scope='all',validation='source-build-only',candidate_library_sha256=build['library_sha256'])
positive=validate(selected,build,digest=digest,resolve=resolve)
assert positive['native_pending'] and not positive['native_verified']
checks=['complete real source candidate accepted with native pending']
assert len(queries)==4
assert validate(selected,build,digest=digest,resolve=resolve)==positive and len(queries)==4
checks.append('unchanged verified binary symbols cached without caching runtime proof')
def rejected(name,mutate):
 s,b=copy.deepcopy(selected),copy.deepcopy(build);mutate(s,b)
 try:validate(s,b,digest=digest,resolve=resolve)
 except (AssertionError,KeyError):checks.append(name);return
 raise AssertionError('Unexpected acceptance: '+name)
rejected('resource-only candidate rejected',lambda s,b:s.update(scope='resource-tools'))
rejected('unknown validation rejected',lambda s,b:s.update(validation='trust-me'))
rejected('unselected candidate hash rejected',lambda s,b:s.update(candidate_library_sha256='0'*64))
rejected('invented verified probe rejected',lambda s,b:s.update(probe='fake.json'))
rejected('native claim rejected',lambda s,b:b.update(native_verified=True))
rejected('runtime execution claim rejected',lambda s,b:b.update(runtime_execution_verified=True))
rejected('missing declared export rejected',lambda s,b:b.update(exports=b['exports'][:-1]))
rejected('changed import set rejected',lambda s,b:b.update(imports_identical=False))
rejected('missing source unit rejected',lambda s,b:b.update(sources=b['sources'][:-1]))
rejected('source hash mismatch rejected',lambda s,b:b['sources'][0].update(sha256='0'*64))
object_name=next(n for n in build['files'] if n.endswith('.o'))
rejected('object hash mismatch rejected',lambda s,b:b['files'].update({object_name:'0'*64}))
# Self-consistent new report digests do not excuse an object omitted from the link.
folder=Path(tempfile.mkdtemp(prefix='source-library-candidate-host-',dir=root/'runtime'))
original=json.loads((root/build['original_build']).read_text());link=original['commands'][-1];link.remove(str(root/object_name))
modified=folder/'missing-link-object.json';modified.write_text(json.dumps(original));modified_hash=digest(modified)
rejected('compiled object absent from link rejected',lambda s,b:b.update(original_build=str(modified.relative_to(root)),original_build_sha256=modified_hash))
# There is no new default: legacy selection still enters the original proof branch.
assert "validation = selected.get('validation', 'verified-probe')" in source.read_text()
report=dict(verified=True,native_execution=False,production_source=str(source.relative_to(root)),production_source_sha256=digest(source),candidate_build=a.build,candidate_build_sha256=digest(root/a.build),positive=positive,checks=checks,check_count=len(checks),recompiled=False,relinked=False,prior_native_matrices_repeated=False)
out=root/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'verified':True,'checks':len(checks),'native_pending':positive['native_pending'],'output':a.output}))
