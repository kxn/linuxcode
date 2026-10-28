#!/usr/bin/env python3
"""Select a complete runtime; unified candidates share providers across all processes."""
from pathlib import Path
import hashlib
import json
import os
import runpy

root = Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent = runpy.run_path(str(root / 'scripts/private-procfs-runtime-profile.py'))

def prepend_library_directories(profile, directories, *, scope='all'):
    """Keep caller, resource metadata and rendered override paths in step."""
    assert scope in ('all', 'resource-tools')
    if profile.get('direct_resource_environment', {}).get('runtime_mode') == 'unified':
        assert scope == 'all', 'Unified runtimes cannot scope a library to a program group'
    directories = list(directories)
    assert all(isinstance(path, str) and path.startswith('/') and ':' not in path for path in directories)
    if not directories:
        return profile
    prefix = ':'.join(directories) + ':'
    command = list(profile['command'])
    keys = ['DARLING_DYLD_OVERRIDE_LIBRARY_PATH']
    if scope == 'all':
        keys.insert(0, 'DYLD_LIBRARY_PATH')
    for key in keys:
        positions = [i for i, value in enumerate(command) if value.startswith(key + '=')]
        if key == 'DARLING_DYLD_OVERRIDE_LIBRARY_PATH' and not positions:
            continue
        assert len(positions) == 1, 'Expected exactly one ' + key
        index = positions[0]
        command[index] = key + '=' + prefix + command[index].split('=', 1)[1]
    direct = dict(profile['direct_resource_environment'])
    tool = dict(direct['tool_environment'])
    tool['DYLD_LIBRARY_PATH'] = prefix + tool['DYLD_LIBRARY_PATH']
    direct['tool_environment'] = tool
    return {**profile, 'command': command, 'direct_resource_environment': direct}

def select(p, configuration='config/direct-resource-tool-environment-v2.json'):
    config = json.loads((root / configuration).read_text())
    sha = lambda path: verified_digest(path)
    for key in ['resource_stage', 'graphics_stage']:
        assert sha(root / config[key]) == config[key+'_sha256']
    unified = config.get('runtime_mode') == 'unified'
    executables = config.get('executables', [])
    if unified:
        assert not executables, 'Unified runtimes cannot select libraries by executable'
    else:
        assert executables and len(set(executables)) == len(executables)
        assert all(path.startswith('/') and ':' not in path for path in executables)
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
            elif field == 'libraries':
                paths += overlay.get('extra_library_paths', [])
            resolved = []
            for value in paths:
                path = (root/value).resolve()
                assert path.is_dir() and path.is_relative_to(root/'runtime')
                resolved.append('/Volumes/SystemRoot/workspace/'+str(path.relative_to(root)))
            assert len(resolved) == len(set(resolved)), 'Duplicate resource overlay search path'
            environment[key] = ':'.join(resolved)+':'+environment[key]
    source_library_directories = []
    for selected in config.get('source_library_builds', []):
        assert selected['scope'] in ('all', 'resource-tools')
        component = selected['component']
        assert component and component.replace('_', '').isalnum()
        build_path = selected['build']
        assert sha(root/build_path) == selected['sha256']
        build = json.loads((root/build_path).read_text())
        assert build['full_'+component+'_source_build']
        assert build['complete_source_files'] == len(build['sources']) > 0
        assert not build.get('missing_original_exports', []) and build['baseline_exports_preserved'] > 0
        library = root/build['library']
        assert sha(library) == build['library_sha256']
        assert library.is_relative_to(root/'runtime')
        resolver = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        for row in build['sources']:
            resolver(row['source'], row['sha256'])
        for name, digest in {**build['source_headers'], **build['files']}.items():
            resolver(name, digest)
        proof_path = selected['probe']
        assert sha(root/proof_path) == selected['probe_sha256']
        proof = json.loads((root/proof_path).read_text())
        assert proof['verified'] and not proof.get('expected_failure', False)
        assert proof['files'][build['library']] == build['library_sha256']
        for name, digest in proof['files'].items():
            resolver(name, digest)
        directory = '/Volumes/SystemRoot/workspace/'+str(library.parent.relative_to(root))
        source_library_directories.append((directory, selected['scope']))
        environment['DYLD_LIBRARY_PATH'] = directory+':'+environment['DYLD_LIBRARY_PATH']
    resource_system = None
    if config.get('resource_system_build'):
        assert sha(root / config['resource_system_build']) == config['resource_system_build_sha256']
        resource_system = json.loads((root / config['resource_system_build']).read_text())
        runpy.run_path(str(root / 'scripts/libsystem-kqueue-runtime-profile.py'))['validate_build'](
            resource_system, p['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL'])
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
        stage_path = config['resource_dispatch_stage']
        assert sha(root/stage_path) == config['resource_dispatch_stage_sha256']
        stage = json.loads((root/stage_path).read_text())
        assert stage['source_build'] == build_path and stage['source_build_sha256'] == sha(root/build_path)
        assert sha(root/stage['library']) == stage['library_sha256'] == dispatch['library_sha256']
        directory = (root/stage['library']).parent.resolve()
        assert {path.name for path in directory.iterdir()} == {'libdispatch.dylib'}
        resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        for row in dispatch['sources']:
            resolve(row['source'], row['sha256'])
        for name, digest in dispatch['source_headers'].items():
            resolve(name, digest)
        probe_path = config['resource_dispatch_probe']
        assert sha(root/probe_path) == config['resource_dispatch_probe_sha256']
        probe = json.loads((root/probe_path).read_text())
        assert probe['verified'] and probe['scalar_ABI_match'] and probe['backend_filter_rejected']
        assert probe['namespace_providers_preserved']
        assert probe['library_stage'] == stage_path and probe['library_stage_sha256'] == sha(root/stage_path)
        assert probe['dispatch_library'] == stage['library']
        assert probe['build'] == build_path and probe['build_sha256'] == sha(root/build_path)
        assert probe['dispatch_library_sha256'] == dispatch['library_sha256']
        for case in probe['cases']:
            assert case['verified'] and case['outer_status'] == 0 and case['native_status'] == ['0']
            assert sha(root/case['log']) == case['log_sha256']
        for name, digest in probe['sources'].items():
            resolve(name, digest)
        assert directory.is_relative_to(root/'runtime')
        environment['DYLD_LIBRARY_PATH'] = '/Volumes/SystemRoot/workspace/'+str(directory.relative_to(root))+':'+environment['DYLD_LIBRARY_PATH']
    if config.get('resource_cpp_build'):
        build_path = config['resource_cpp_build']
        assert sha(root/build_path) == config['resource_cpp_build_sha256']
        cpp = json.loads((root/build_path).read_text())
        assert cpp['baseline_only_UUID_differs'] and cpp['compiler_generated_RTTI_and_vtable']
        assert cpp['class_declaration_from_actual_SDK'] and not cpp['experimental_namespace_aliased']
        assert cpp['key_function_body_unchanged'] and len(cpp['added_exports']) == 6
        assert sha(root/cpp['library']) == cpp['library_sha256']
        directory = (root/cpp['library']).parent.resolve()
        assert directory.is_relative_to(root/'runtime')
        assert {path.name for path in directory.iterdir()} == {'libc++.1.dylib'}
        resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        for field in ['source', 'upstream_source', 'SDK_header', 'parent_build', 'backend', 'new_object']:
            resolve(cpp[field], cpp[field+'_sha256'])
        for name, digest in cpp['existing_object_inputs'].items():
            resolve(name, digest)
        probe_path = config['resource_cpp_probe']
        assert sha(root/probe_path) == config['resource_cpp_probe_sha256']
        probe = json.loads((root/probe_path).read_text())
        assert probe['verified'] and probe['build'] == build_path
        assert probe['build_sha256'] == sha(root/build_path)
        assert probe['library'] == cpp['library'] and probe['library_sha256'] == cpp['library_sha256']
        assert [case['mode'] for case in probe['cases']] == ['missing', 'present', 'expected']
        for case in probe['cases']:
            assert case['verified'] and sha(root/case['log']) == case['log_sha256']
            if case['mode'] != 'missing':
                assert case['outer_status'] == 0 and case['native_status'] == ['0']
        for name, digest in probe['sources'].items():
            resolve(name, digest)
        environment['DYLD_LIBRARY_PATH'] = '/Volumes/SystemRoot/workspace/'+str(directory.relative_to(root))+':'+environment['DYLD_LIBRARY_PATH']
    if config.get('resource_cpp_backend_build'):
        assert config.get('resource_cpp_build')
        build_path = config['resource_cpp_backend_build']
        assert sha(root/build_path) == config['resource_cpp_backend_build_sha256']
        backend = json.loads((root/build_path).read_text())
        assert backend['linked'] and backend['standard'] == 'c++20'
        assert backend['Apple_force_weak_and_notweak_policies_applied']
        assert backend['existing_export_flags_preserved'] and not backend['existing_export_flags_changed']
        assert not backend['previous_backend_missing_exports'] and not backend['installed']
        assert backend['old_backend'] == cpp['backend']
        assert backend['old_backend_sha256'] == cpp['backend_sha256']
        assert sha(root/backend['library']) == backend['library_sha256']
        assert Path(backend['library']).name == Path(cpp['backend']).name == 'libc++0.dylib'
        directory = (root/backend['library']).parent.resolve()
        assert directory.is_relative_to(root/'runtime')
        assert {path.name for path in directory.iterdir()} == {'libc++0.dylib'}
        assert backend['backend_source_units'] == len(backend['compilation'])
        for item in backend['compilation']:
            assert item['returncode'] == 0 and sha(root/item['object']) == item['object_sha256']
        for name, digest in {**backend['sources'], **backend['export_policies']}.items():
            resolve(name, digest)
        for field in ['builder', 'relinker', 'parent_build', 'ABI_library']:
            resolve(backend[field], backend[field+'_sha256'])
        assert backend['original_link_tool_bytes_equal_extracted'] and backend['link_native_status'] == ['0']
        assert backend['link_outer_status'] == 0
        assert sha(root/backend['link_log']) == backend['link_log_sha256']
        original_tool = backend['original_link_tool']
        extracted = 'runtime/xcode-extract/Xcode.app/Contents/Developer'+original_tool.split('/Contents/Developer', 1)[1]
        assert sha(root/('runtime/state/prefix'+original_tool)) == backend['original_link_tool_sha256'] == sha(root/extracted)
        probe_path = config['resource_cpp_backend_probe']
        assert sha(root/probe_path) == config['resource_cpp_backend_probe_sha256']
        proof = json.loads((root/probe_path).read_text())
        assert proof['verified'] and proof['build'] == build_path and proof['build_sha256'] == sha(root/build_path)
        assert proof['library'] == backend['library'] and proof['library_sha256'] == backend['library_sha256']
        assert [case['mode'] for case in proof['cases']] == ['missing', 'present', 'pmr', 'expected', 'format']
        assert sha(root/proof['fixture']) == proof['fixture_sha256']
        for case in proof['cases']:
            assert case['verified'] and sha(root/case['log']) == case['log_sha256']
            assert sha(root/case['program']) == case['program_sha256']
            if case['mode'] == 'missing':
                assert case['outer_status'] != 0 and 'codecvt' in (root/case['log']).read_text()
            else:
                assert case['outer_status'] == 0 and case['native_status'] == ['0']
        for name, digest in proof['sources'].items():
            resolve(name, digest)
        environment['DYLD_LIBRARY_PATH'] = '/Volumes/SystemRoot/workspace/'+str(directory.relative_to(root))+':'+environment['DYLD_LIBRARY_PATH']
    if config.get('resource_cpp_abi_build'):
        assert config.get('resource_cpp_backend_build')
        build_path = config['resource_cpp_abi_build']
        probe_path = config['resource_cpp_abi_probe']
        assert sha(root/build_path) == config['resource_cpp_abi_build_sha256']
        assert sha(root/probe_path) == config['resource_cpp_abi_probe_sha256']
        validator = 'scripts/primary-exception-runtime-inputs.py'
        resolver = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        selected_validator = resolver(validator, config['resource_cpp_abi_validator_sha256'])
        directory = runpy.run_path(str(root/selected_validator))['validate'](root, build_path, probe_path, backend)
        environment['DYLD_LIBRARY_PATH'] = '/Volumes/SystemRoot/workspace/'+str(directory.relative_to(root))+':'+environment['DYLD_LIBRARY_PATH']
    system_path = '/Volumes/SystemRoot/workspace/' + str(Path(system_library).parent)
    environment['DYLD_LIBRARY_PATH'] = system_path + ':' + environment['DYLD_LIBRARY_PATH']
    if unified:
        assert objc_scope == 'all' and all(scope == 'all' for _, scope in source_library_directories)
        command = [value for value in p['command'] if not value.startswith('DARLING_DYLD_OVERRIDE_')]
        for key, value in environment.items():
            positions = [i for i, arg in enumerate(command) if arg.startswith(key + '=')]
            assert len(positions) == 1, key
            command[positions[0]] = key + '=' + value
    else:
        additions = ['DARLING_DYLD_OVERRIDE_EXECUTABLES=' + ':'.join(executables),
            'DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH=' + environment['DYLD_FRAMEWORK_PATH'],
            'DARLING_DYLD_OVERRIDE_LIBRARY_PATH=' + environment['DYLD_LIBRARY_PATH']]
        command = p['command'][:-2] + additions + p['command'][-2:]
    launcher_stage = config.get('run_launcher_stage', config.get('resource_launcher_stage'))
    if launcher_stage:
        launcher_digest = config['run_launcher_stage_sha256'] if config.get('run_launcher_stage') else config['resource_launcher_stage_sha256']
        assert sha(root/launcher_stage) == launcher_digest
        launcher = json.loads((root/launcher_stage).read_text())
        if config.get('run_launcher_stage'):
            assert unified and launcher['run_environment_shared_from_bootstrap']
            image = launcher.get('materialized_shared_runtime')
            if image:
                image_stage = root / image['runtime_stage']
                assert sha(image_stage) == image['runtime_stage_sha256']
                assert json.loads(image_stage.read_text())['source_runtime'] == p['source_runtime'], \
                    'The preinstalled system image must use the same runtime providers as this run'
        assert launcher['private_canonical_PlugInKit_mount'] and launcher['original_provider_bytes_preserved']
        resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
        for name, digest in launcher['files'].items():
            resolve(name, digest)
        assert command.count(launcher['parent_launcher']) == 1
        command[command.index(launcher['parent_launcher'])] = launcher['launcher']
    if not unified and objc_directory and objc_scope == 'all':
        index = next(i for i, value in enumerate(command) if value.startswith('DYLD_LIBRARY_PATH='))
        command[index] = 'DYLD_LIBRARY_PATH='+objc_directory+':'+command[index].split('=', 1)[1]
    for directory, scope in source_library_directories:
        if not unified and scope == 'all':
            index = next(i for i, value in enumerate(command) if value.startswith('DYLD_LIBRARY_PATH='))
            command[index] = 'DYLD_LIBRARY_PATH='+directory+':'+command[index].split('=', 1)[1]
    result = {**p, 'command': command, 'direct_resource_environment': dict(configuration=configuration,
        configuration_sha256=sha(root / configuration), tool_environment=environment,
        source_library_builds=config.get('source_library_builds', []),
        source_library_directories=[dict(directory=directory,scope=scope) for directory,scope in source_library_directories],
        resource_system_build=config.get('resource_system_build'),
        resource_dispatch_build=config.get('resource_dispatch_build'),
        resource_dispatch_probe=config.get('resource_dispatch_probe'),
        resource_dispatch_stage=config.get('resource_dispatch_stage'),
        resource_cpp_build=config.get('resource_cpp_build'),
        resource_cpp_probe=config.get('resource_cpp_probe'),
        resource_cpp_backend_build=config.get('resource_cpp_backend_build'),
        resource_cpp_backend_probe=config.get('resource_cpp_backend_probe'),
        resource_cpp_abi_build=config.get('resource_cpp_abi_build'),
        resource_cpp_abi_probe=config.get('resource_cpp_abi_probe'),
        resource_overlay_stage=config.get('resource_overlay_stage'),
        resource_launcher_stage=launcher_stage,
        objc_source_build=config.get('objc_source_build'),
        objc_source_scope=objc_scope if objc_directory else None,
        runtime_mode='unified' if unified else 'legacy-scoped', executables=executables, parent_DYLD_paths_changed=bool(unified or (objc_directory and objc_scope == 'all') or any(scope=='all' for _,scope in source_library_directories)),
        original_tool_binaries_modified=False, original_resource_compilation_verified=False)}
    for key, selector in [('coretls_source_build', 'coretls-source-runtime-profile.py'),
                          ('coretls_cfhelpers_build', 'coretls-cfhelpers-runtime-profile.py')]:
        if config.get(key):
            assert sha(root/config[key]) == config[key+'_sha256']
            result = runpy.run_path(str(root/'scripts'/selector))['select'](result, config[key])
    if unified:
        assert not any(value.startswith('DARLING_DYLD_OVERRIDE_') for value in result['command'])
        for key, value in result['direct_resource_environment']['tool_environment'].items():
            assert key+'='+value in result['command'], key
    return result

def profile(stage, configuration='config/direct-resource-tool-environment-v2.json'):
    return select(parent['profile'](stage=stage), configuration)

def environment(p):
    environment = parent['environment'](p)
    if p.get('direct_resource_environment', {}).get('runtime_mode') == 'unified':
        assert not any(argument.startswith('DARLING_DYLD_OVERRIDE_') for argument in p['command']), \
            'Program-specific library overrides are not permitted in a unified run'
        environment = {key: value for key, value in environment.items()
                       if not key.startswith('DARLING_DYLD_OVERRIDE_')}
        for key in ('DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH', 'OBJC_DISABLE_TAGGED_POINTERS'):
            values = [argument.split('=', 1)[1] for argument in p['command'] if argument.startswith(key+'=')]
            assert len(values) == 1, key
            selected = p['direct_resource_environment']['tool_environment'].get(key)
            assert selected is None or selected == values[0], \
                'The command must use the common runtime library configuration: ' + key
            environment['LINUXCODE_RUN_'+key] = values[0]
    return environment
