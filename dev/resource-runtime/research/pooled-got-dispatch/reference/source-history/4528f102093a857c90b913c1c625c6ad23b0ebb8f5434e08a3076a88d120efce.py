#!/usr/bin/env python3
"""Give original resource tools an exact-path library scope while preserving the caller's environment."""
from pathlib import Path
import hashlib
import json
import os
import runpy

root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/private-procfs-runtime-profile.py'))

def select(p, configuration='config/direct-resource-tool-environment-v2.json'):
    config = json.loads((root / configuration).read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    for key in ['resource_stage', 'graphics_stage']:
        assert sha(root / config[key]) == config[key+'_sha256']
    assert config['executables'] and len(set(config['executables'])) == len(config['executables'])
    assert all(path.startswith('/') and ':' not in path for path in config['executables'])
    resource = runpy.run_path(str(root / 'scripts/coregraphics-native-security-profile.py'))['profile'](
        stage=config['resource_stage'], graphics_stage=config['graphics_stage'])
    environment = dict(arg.split('=', 1) for arg in resource['command'] if arg.startswith(('DYLD_FRAMEWORK_PATH=', 'DYLD_LIBRARY_PATH=')))
    objc_directory = None
    objc_scope = config.get('objc_source_scope', 'all')
    assert objc_scope in ('all', 'resource-tools')
    if config.get('objc_source_build'):
        assert sha(root/config['objc_source_build']) == config['objc_source_build_sha256']
        objc = json.loads((root/config['objc_source_build']).read_text())
        assert objc['full_objc_source_build'] and objc['complete_source_files'] == 43
        assert not objc['missing_original_exports'] and objc['source_export_count'] >= 771
        assert sha(root/objc['library']) == objc['library_sha256']
        resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        for name, digest in objc['source_files'].items():
            resolve('vendor/darling/src/external/objc4/runtime/'+name, digest)
        for name, digest in objc['build_inputs'].items():
            resolve(name, digest)
        objc_directory = '/Volumes/SystemRoot/workspace/'+str(Path(objc['library']).parent)
        environment['DYLD_LIBRARY_PATH'] = objc_directory+':'+environment['DYLD_LIBRARY_PATH']
    if config.get('resource_overlay_stage'):
        assert sha(root/config['resource_overlay_stage']) == config['resource_overlay_stage_sha256']
        overlay = json.loads((root/config['resource_overlay_stage']).read_text())
        resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        for name, digest in overlay['files'].items():
            resolve(name, digest)
        for name, target in overlay.get('links', {}).items():
            assert os.readlink(root/name) == target
        for key, field in [('DYLD_FRAMEWORK_PATH', 'frameworks'), ('DYLD_LIBRARY_PATH', 'libraries')]:
            paths = [overlay[field]]
            if field == 'frameworks':
                paths += overlay.get('extra_framework_paths', [])
            resolved = []
            for value in paths:
                path = (root/value).resolve()
                assert path.is_dir() and path.is_relative_to(root/'runtime')
                resolved.append('/Volumes/SystemRoot/workspace/'+str(path.relative_to(root)))
            assert len(resolved) == len(set(resolved)), 'Duplicate resource overlay search path'
            environment[key] = ':'.join(resolved)+':'+environment[key]
    resource_system = None
    if config.get('resource_system_build'):
        assert sha(root / config['resource_system_build']) == config['resource_system_build_sha256']
        resource_system = json.loads((root / config['resource_system_build']).read_text())
        assert resource_system['full_initializer_and_queue_source_build'] and resource_system['complete_source_files'] == 20
        assert resource_system['original_source_instructions_preserved']
        assert sha(root / resource_system['output']) == resource_system['output_sha256']
        resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
        for name, digest in resource_system['files'].items():
            resolve(name, digest)
        for name, digest in resource_system['link_inputs'].items():
            assert sha(root / name) == digest, name
        system_library = resource_system['output']
    else:
        runtime = json.loads((root / p['private_procfs_stage']).read_text())
        system_library = runtime['system_library']
    if config.get('resource_dispatch_build'):
        build_path = config['resource_dispatch_build']
        assert sha(root/build_path) == config['resource_dispatch_build_sha256']
        dispatch = json.loads((root/build_path).read_text())
        assert dispatch['full_libdispatch_source_build'] and dispatch['complete_source_files'] == 32
        assert dispatch['original_exports_preserved'] == 654 and dispatch['source_exports'] == 655
        assert sha(root/dispatch['library']) == dispatch['library_sha256']
        resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        for row in dispatch['sources']:
            resolve(row['source'], row['sha256'])
        for name, digest in dispatch['source_headers'].items():
            resolve(name, digest)
        probe_path = config['resource_dispatch_probe']
        assert sha(root/probe_path) == config['resource_dispatch_probe_sha256']
        probe = json.loads((root/probe_path).read_text())
        assert probe['verified'] and probe['scalar_ABI_match'] and probe['backend_filter_rejected']
        assert probe['build'] == build_path and probe['build_sha256'] == sha(root/build_path)
        assert probe['dispatch_library_sha256'] == dispatch['library_sha256']
        for case in probe['cases']:
            assert case['verified'] and case['outer_status'] == 0 and case['native_status'] == ['0']
            assert sha(root/case['log']) == case['log_sha256']
        for name, digest in probe['sources'].items():
            resolve(name, digest)
        directory = (root/dispatch['library']).parent.resolve()
        assert directory.is_relative_to(root/'runtime')
        environment['DYLD_LIBRARY_PATH'] = '/Volumes/SystemRoot/workspace/'+str(directory.relative_to(root))+':'+environment['DYLD_LIBRARY_PATH']
    system_path = '/Volumes/SystemRoot/workspace/' + str(Path(system_library).parent)
    environment['DYLD_LIBRARY_PATH'] = system_path + ':' + environment['DYLD_LIBRARY_PATH']
    additions = ['DARLING_DYLD_OVERRIDE_EXECUTABLES=' + ':'.join(config['executables']),
        'DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH=' + environment['DYLD_FRAMEWORK_PATH'],
        'DARLING_DYLD_OVERRIDE_LIBRARY_PATH=' + environment['DYLD_LIBRARY_PATH']]
    command = p['command'][:-2] + additions + p['command'][-2:]
    if objc_directory and objc_scope == 'all':
        index = next(i for i, value in enumerate(command) if value.startswith('DYLD_LIBRARY_PATH='))
        command[index] = 'DYLD_LIBRARY_PATH='+objc_directory+':'+command[index].split('=', 1)[1]
    return {**p, 'command': command, 'direct_resource_environment': dict(configuration=configuration,
        configuration_sha256=sha(root / configuration), tool_environment=environment,
        resource_system_build=config.get('resource_system_build'),
        resource_dispatch_build=config.get('resource_dispatch_build'),
        resource_dispatch_probe=config.get('resource_dispatch_probe'),
        resource_overlay_stage=config.get('resource_overlay_stage'),
        objc_source_build=config.get('objc_source_build'),
        objc_source_scope=objc_scope if objc_directory else None,
        executables=config['executables'], parent_DYLD_paths_changed=bool(objc_directory and objc_scope == 'all'),
        original_tool_binaries_modified=False, original_resource_compilation_verified=False)}

def profile(stage, configuration='config/direct-resource-tool-environment-v2.json'):
    return select(parent['profile'](stage=stage), configuration)

def environment(p):
    return parent['environment'](p)
