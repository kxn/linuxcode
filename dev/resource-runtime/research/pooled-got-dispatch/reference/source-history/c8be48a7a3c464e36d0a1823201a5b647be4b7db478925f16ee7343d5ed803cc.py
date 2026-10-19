#!/usr/bin/env python3
"""Give original resource tools an exact-path library scope while preserving the caller's environment."""
from pathlib import Path
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/private-procfs-runtime-profile.py'))

def select(p, configuration='config/direct-resource-tool-environment-v1.json'):
    config = json.loads((root / configuration).read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    for key in ['resource_stage', 'graphics_stage']:
        assert sha(root / config[key]) == config[key+'_sha256']
    assert config['executables'] and len(set(config['executables'])) == len(config['executables'])
    assert all(path.startswith('/') and ':' not in path for path in config['executables'])
    resource = runpy.run_path(str(root / 'scripts/coregraphics-native-security-profile.py'))['profile'](
        stage=config['resource_stage'], graphics_stage=config['graphics_stage'])
    environment = dict(arg.split('=', 1) for arg in resource['command'] if arg.startswith(('DYLD_FRAMEWORK_PATH=', 'DYLD_LIBRARY_PATH=')))
    runtime = json.loads((root / p['private_procfs_stage']).read_text())
    system_path = '/Volumes/SystemRoot/workspace/' + str(Path(runtime['system_library']).parent)
    environment['DYLD_LIBRARY_PATH'] = system_path + ':' + environment['DYLD_LIBRARY_PATH']
    additions = ['DARLING_DYLD_OVERRIDE_EXECUTABLES=' + ':'.join(config['executables']),
        'DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH=' + environment['DYLD_FRAMEWORK_PATH'],
        'DARLING_DYLD_OVERRIDE_LIBRARY_PATH=' + environment['DYLD_LIBRARY_PATH']]
    command = p['command'][:-2] + additions + p['command'][-2:]
    return {**p, 'command': command, 'direct_resource_environment': dict(configuration=configuration,
        configuration_sha256=sha(root / configuration), tool_environment=environment,
        executables=config['executables'], parent_DYLD_paths_changed=False,
        original_tool_binaries_modified=False, original_resource_compilation_verified=False)}

def profile(stage, configuration='config/direct-resource-tool-environment-v1.json'):
    return select(parent['profile'](stage=stage), configuration)

def environment(p):
    return parent['environment'](p)
