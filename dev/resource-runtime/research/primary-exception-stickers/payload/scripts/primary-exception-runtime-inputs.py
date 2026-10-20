#!/usr/bin/env python3
"""Validate the complete libcxxabi candidate and its actual native evidence."""
from pathlib import Path
import hashlib
import json
import runpy


def validate(root, build_path, probe_path, backend):
    root = Path(root)
    sha = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
    read = lambda p: json.loads((root / p).read_text())
    resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
    build, probe = read(build_path), read(probe_path)
    assert build['linked'] and not build['installed'] and not build['runtime_execution_verified']
    assert build['complete_source_units'] == len(build['compilation']) == 18
    assert len({row['source'] for row in build['compilation']}) == 18
    assert not build['missing_baseline_exports']
    assert build['added_exports'] == ['___cxa_init_primary_exception']
    assert build['primary_initializer_exported']
    assert build['baseline_library'] == backend['ABI_library']
    assert build['baseline_library_sha256'] == backend['ABI_library_sha256'] == sha(build['baseline_library'])
    assert sha(build['library']) == build['library_sha256']
    directory = (root / build['library']).parent.resolve()
    assert directory.is_relative_to(root / 'runtime')
    assert {p.name for p in directory.iterdir()} == {'libc++abi.dylib'}
    assert Path(build['library']).name == 'libc++abi.dylib'
    for row in build['compilation']:
        assert row['returncode'] == 0 and sha(row['object']) == row['object_sha256']
        assert sha(row['log']) == row['log_sha256']
        resolve(row['source'], row['source_sha256'])
    for field in ['cmake', 'builder']:
        resolve(build[field], build[field + '_sha256'])
    for name, digest in build['sources'].items():
        resolve(name, digest)
    assert probe['verified'] and probe['build'] == build_path and probe['build_sha256'] == sha(build_path)
    assert probe['library'] == build['library'] and probe['library_sha256'] == build['library_sha256']
    assert sha(probe['fixture']) == probe['fixture_sha256']
    assert sha(probe['program']) == probe['program_sha256']
    assert [row['mode'] for row in probe['cases']] == ['missing', 'primary', 'pmr', 'expected', 'format']
    for row in probe['cases']:
        assert row['verified'] and sha(row['log']) == row['log_sha256']
        text = (root / row['log']).read_text()
        if row['mode'] == 'missing':
            assert row['outer_status'] != 0 and 'Symbol not found' in text and '__cxa_init_primary_exception' in text
        else:
            assert row['outer_status'] == 0 and row['native_status'] == ['0']
        if row['mode'] == 'primary':
            assert 'PRIMARY_EXCEPTION_ABI_REFCOUNT_CROSS_DSO_RETHROW_CLEANUP_AND_4_THREADS_OK' in text
            assert build['library'] in text
    for name, digest in probe['sources'].items():
        resolve(name, digest)
    assert sha(probe['original_regression_probe']) == probe['original_regression_probe_sha256']
    old = read(probe['original_regression_probe'])
    previous = {row['mode']: row for row in old['cases']}
    for row in probe['cases'][2:]:
        prior = previous[row['mode']]
        assert prior['verified'] and sha(prior['program']) == prior['program_sha256']
        expected = list(prior['command'])
        index = next(i for i, arg in enumerate(expected) if arg.startswith('DYLD_LIBRARY_PATH='))
        expected[index] = ('DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/' +
                           str(Path(build['library']).parent) + ':' + expected[index].partition('=')[2])
        expected[3] = '150'
        assert row['command'] == expected
    return directory
