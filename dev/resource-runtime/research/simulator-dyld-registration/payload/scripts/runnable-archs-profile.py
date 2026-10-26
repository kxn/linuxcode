#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/mobilegestalt-native-profile.py'));environment=m['environment']
def profile():
 p=m['profile']();stage=json.loads((root/'artifacts/runnable-archs-source-stage.json').read_text())
 digest=lambda n:verified_digest((root/n))
 for key in ['base','library','source_library','build_report']:assert digest(stage[key])==stage[key+'_sha256']
 build=json.loads((root/stage['build_report']).read_text())
 resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
 for n,sha in {**build['source_files'],**build['source_build_inputs']}.items():resolve('vendor/darling/src/external/dyld/'+n,sha)
 relative=stage['source_library'];selected={k:dict(v) for k,v in p['source_runtime'].items()};selected['LINUXCODE_LIBDYLD']=dict(path=relative,sha256=digest(relative))
 for key,name in [('LINUXCODE_LIBSYSTEM_KERNEL','libsystem_kernel.dylib'),('LINUXCODE_QUARANTINE','libquarantine.dylib'),('LINUXCODE_SANDBOX','libsystem_sandbox.dylib'),('LINUXCODE_LIBXPC','libxpc.dylib')]:assert digest('runtime/runnable-archs-source/darling-root/usr/lib/system/'+name)==selected[key]['sha256']
 assert digest('runtime/runnable-archs-source/darling-root/sbin/launchd')==selected['LINUXCODE_LAUNCHD']['sha256']
 c=list(p['command']);i=next(i for i,v in enumerate(c) if v.startswith('DYLD_LIBRARY_PATH='));c[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/runnable-archs-source/libraries:'+c[i].split('=',1)[1]
 return {**p,'command':c,'source_runtime':selected,'runnable_archs':stage,'source_libdyld':build}
