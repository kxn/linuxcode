#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/log-pack-profile.py'))
verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
def profile(include_system_resources=True):
    p=m['profile']();stage=json.loads((root/'artifacts/mdns-native-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    for image in stage['images']:
        for key in ['source','library','reconstruction']:assert digest(image[key])==image[key+'_sha256']
    for name,target in stage['overlay_links'].items():assert os.readlink(root/name)==target
    for key in ['base','library','provider','source']:
        assert digest(stage['security_identifier'][key])==stage['security_identifier'][key+'_sha256']
    values=stage['security_value_classes'];assert digest(values['library'])==values['library_sha256']
    for name,sha in values['build']['sources'].items():verify_source(dict(source=name,sha256=sha))
    mobile=stage['mobile_device']
    for name,sha in mobile['files'].items():assert digest(name)==sha
    for name,target in mobile['symlinks'].items():assert os.readlink(root/name)==target
    c=list(p['command'])
    for key,folder in [('DYLD_LIBRARY_PATH','libraries'),('DYLD_FRAMEWORK_PATH','frameworks')]:
        i=next(i for i,a in enumerate(c) if a.startswith(key+'='));c[i]=key+'=/Volumes/SystemRoot/workspace/runtime/mdns-native/'+folder+':'+c[i].split('=',1)[1]
    runtime=json.loads((root/'artifacts/xpc-collections-runtime-stage.json').read_text())
    assert runtime['previous_source_runtime']==p['source_runtime']
    assert digest(runtime['source_build'])==runtime['source_build_sha256']
    source=json.loads((root/runtime['source_build']).read_text())
    for name,sha in source['source_files'].items():verify_source(dict(source='vendor/darling/src/external/libxpc/'+name,sha256=sha))
    for name,sha in source['modified_files'].items():verify_source(dict(source='vendor/darling/src/external/libxpc/'+name,sha256=sha))
    assert digest('vendor/darling/src/external/libxpc/include/xpc/xpc.h')==source['public_header_sha256']
    for item in runtime['source_runtime'].values():assert digest(item['path'])==item['sha256']
    p={**p,'source_runtime':runtime['source_runtime'],'source_xpc_collections':source,'xpc_collections_runtime':runtime}
    return {**p,'command':c,'native_mdns':stage,'use_original_developer_overlay':include_system_resources}
def environment(p):
    result=m['environment'](p)
    if p['use_original_developer_overlay']:
        result['LINUXCODE_DEVELOPER_OVERLAY']=str(root/p['native_mdns']['developer_overlay'])
        result['LINUXCODE_APPLE_OVERLAY']=str(root/p['native_mdns']['mobile_device']['payload_root'])
    return result
