#!/usr/bin/env python3
"""Prepare an explicit original-image list serially, retaining every failed attempt."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--configuration', required=True)
parser.add_argument('--report', required=True)
parser.add_argument('--keep-going', action='store_true',
                    help='Collect independent preparation failures; incomplete batches still exit nonzero')
args = parser.parse_args()
configuration = json.loads((root/args.configuration).read_text())
preparation_options = configuration.get('preparation_options', [])
allowed_options = {'--preserve-code-with-patch-got', '--patch-got-renamed-reexports',
    '--preserve-original-uuid', '--read-only-data-const', '--align-linkedit-streams',
    '--omit-lazy-helper-section', '--omit-leading-padding-sections'}
assert isinstance(preparation_options, list) and len(preparation_options) == len(set(preparation_options))
assert all(option in allowed_options for option in preparation_options)
output = root/args.report
assert not output.exists()
sha = lambda name: hashlib.sha256((root/name).read_bytes()).hexdigest()
record = dict(complete=False, image_runtime_verified=False, configuration=args.configuration,
    configuration_sha256=sha(args.configuration), source=str(Path(__file__).relative_to(root)),
    source_sha256=sha(str(Path(__file__).relative_to(root))), images=[])

def save():
    output.write_text(json.dumps(record, indent=2)+'\n')

def checked_target(target, image):
    data = json.loads((root/('runtime/rebuilt-'+target+'/reconstruction.json')).read_text())
    original = 'runtime/fullsystem-libraries'+image
    assert sha(original) == data['original_image_sha256']
    assert sha('runtime/rebuilt-'+target+'/'+Path(image).name) == data['staged_image_sha256']
    assert not data['installed'] and not data['execution_verified'] and not data['backend_call_overrides']
    if '--preserve-code-with-patch-got' in preparation_options:
        assert data['rip_instructions_patched'] == 0
        proof = data['byte_preserving_patch_got']
        assert not proof['original_instruction_rewriting'] and proof['executable_sections_byte_equal']

def prepare(item, row):
    image, stem = item['image'], item['stem']
    assert stem and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in stem)
    audit_options = item.get('audit_options', [])
    assert isinstance(audit_options, list)
    cursor = 0
    while cursor < len(audit_options):
        option = audit_options[cursor]
        assert option in {'--follow-explicit-reexports', '--coalesce-equivalent-reexports',
                          '--whole-library-reexport-provider'}
        cursor += 1
        if option == '--whole-library-reexport-provider':
            assert cursor < len(audit_options)
            provider = audit_options[cursor]
            assert isinstance(provider, str) and provider.startswith('/') and '..' not in Path(provider).parts
            cursor += 1
    if item.get('existing_target'):
        checked_target(item['existing_target'], image)
        row['prepared_target'] = item['existing_target']
        save()
        return
    audit, options = None, list(preparation_options)
    for index in range(1, 5):
        target = stem+'-resource-v'+str(index)
        command = [sys.executable, 'scripts/prepare-resource-image-candidate.py']
        command += (['--from-target', stem+'-resource-v1', '--exact-import-audit', audit]
                    if audit else ['--image', image])
        command += [*options, '--target', target, '--build']
        log = 'logs/'+target+'-batch-preparation.log'
        assert not (root/log).exists()
        with (root/log).open('w') as stream:
            result = subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
        preparation = 'artifacts/'+target+'-input.json'
        row['attempts'].append(dict(target=target, returncode=result.returncode, command=command,
            log=log, log_sha256=sha(log), preparation=preparation if (root/preparation).exists() else None))
        save()
        if result.returncode == 0:
            checked_target(target, image)
            row['prepared_target'] = target
            save()
            print('PREPARED', target, flush=True)
            break
        if not (root/preparation).is_file():
            raise RuntimeError('Preparation failed before a report: '+log)
        prepared = json.loads((root/preparation).read_text())
        failure = (root/prepared['log']).read_text()
        if any(message in failure for message in ['unresolved cache targets',
                'An original symbol stub lacks a verified GOT relocation']) and audit is None:
            audit = 'artifacts/'+stem+'-original-import-audit-v1.json'
            subprocess.run([sys.executable, 'scripts/audit-resource-image-imports.py',
                '--target', target, '--output', audit, *audit_options], cwd=root, check=True)
        elif 'original header capacity' in failure and '--omit-lazy-helper-section' not in options:
            options.append('--omit-lazy-helper-section')
        elif 'original header capacity' in failure and '--omit-leading-padding-sections' not in options:
            options.append('--omit-leading-padding-sections')
        else:
            raise RuntimeError('Unresolved reconstruction failure: '+prepared['log'])
    if row['prepared_target'] is None:
        raise RuntimeError('No successful candidate for '+image)
for item in configuration['images']:
    row = dict(image=item['image'], attempts=[], prepared_target=None)
    record['images'].append(row)
    save()
    try:
        prepare(item,row)
    except Exception as error:
        row['failure'] = dict(type=type(error).__name__,message=str(error))
        save()
        if not args.keep_going:
            raise
        print('FAILED',item['image'],str(error),flush=True)
record['complete'] = all(row['prepared_target'] is not None for row in record['images'])
save()
print('EVIDENCE', args.report)
raise SystemExit(0 if record['complete'] else 1)
