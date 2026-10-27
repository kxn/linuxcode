"""Adopt the proven certificate runtime independently of historical test keys."""
import json
import runpy


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def candidate(workspace, native, digest):
    config_path = workspace / native['certificate_candidate']
    require(digest(config_path) == native['candidate_sha256'], 'Certificate candidate changed; inspect and adopt again.')
    config = json.loads(config_path.read_text())
    proof = config['verified_build']
    documents = {}
    for key in ['milestone', 'build_report', 'native_product_report', 'independent_product_report']:
        row = proof[key]; path = workspace / row['path']
        require(path.resolve().is_relative_to(workspace), 'Certificate evidence must be inside the workspace.')
        require(digest(path) == row['sha256'], 'Certificate success evidence changed: ' + row['path'])
        documents[key] = json.loads(path.read_text())
    milestone = documents['milestone']; build = documents['build_report']
    strict = documents['native_product_report']; independent = documents['independent_product_report']
    require(milestone['verified'] and milestone['full_Unity_CocoaPods_certificate_CI_verified']
            and milestone['original_xcodebuild_invoked'] and milestone['original_codesign']
            and not milestone['zsign_used'] and not milestone['ad_hoc_only']
            and milestone['real_CMS_certificate_signature'], 'Certificate milestone is not a verified original signed build.')
    for key in ['build_report', 'native_product_report', 'independent_product_report']:
        row = proof[key]
        require(milestone['references'].get(row['path']) == row['sha256'], 'Certificate proof does not belong to this milestone: ' + key)
    require(native['build_report'] == proof['build_report']['path'], 'Certificate build report differs from the selected proof.')
    require(strict['verified'] and strict['outer_status'] == 0
            and strict['native_statuses'] == [[str(i), '0'] for i in range(7)]
            and independent['verified'] and len(independent['checks']) == 7
            and sorted(strict['products']) == sorted(independent['checks'])
            and all(row['verified'] for row in independent['checks'].values()),
            'Certificate product verification is incomplete.')
    require(independent['public_certificate_SHA256'] == milestone['public_certificate_SHA256'],
            'Certificate verification used a different leaf certificate.')
    for record in [strict, build]:
        require(digest(workspace / record['log']) == record['log_sha256'], 'Certificate success log changed.')
    recorded = build['native_certificate_runtime']
    require(digest(workspace / recorded['candidate']) == recorded['candidate_sha256'], 'Original certificate runtime proof changed.')
    actual_config = json.loads((workspace / recorded['candidate']).read_text())
    require(config['inputs'] == actual_config['inputs'], 'Selected certificate components differ from the proven build.')
    require(build['exit_status'] == 0 and build['native_xcode_status'] == ['0'], 'Certificate build did not return success.')
    require(native['stage'] == build['native_codesign_stage'], 'Certificate native signing stage differs from the proven build.')
    require(digest(workspace / native['prebuild_file']) == native['prebuild_sha256'], 'Certificate service prelude changed.')
    module = runpy.run_path(str(workspace / 'scripts/direct-resource-tool-runtime-profile.py'))
    profile = module['profile'](stage=config['inputs']['stage']['path'],
                                configuration=config['inputs']['configuration']['path'])
    require(profile['source_runtime'] == build['source_runtime'], 'Certificate proof and selected source components differ.')
    signer = runpy.run_path(str(workspace / 'scripts/native-certificate-runtime.py'))
    profile = signer['select'](profile, native['certificate_candidate'], native['identity_store'], prepare=False)
    if config.get('workspace_bind_stage'):
        row = config['workspace_bind_stage']
        require(digest(workspace / row['path']) == row['sha256'], 'Workspace mapping launcher changed.')
        require(build.get('workspace_bind_stage') == row['path'], 'Workspace mapping launcher differs from the proven build.')
        stage = json.loads((workspace / row['path']).read_text())
        for name, expected in stage['files'].items():
            require(digest(workspace / name) == expected, 'Workspace mapping input changed: ' + name)
        command = list(profile['command'])
        require(command.count(stage['parent_launcher']) == 1, 'Workspace mapping parent launcher differs.')
        command[command.index(stage['parent_launcher'])] = stage['launcher']
        profile = {**profile, 'command': command, 'workspace_bind_stage': row['path']}
    return module, profile, build
