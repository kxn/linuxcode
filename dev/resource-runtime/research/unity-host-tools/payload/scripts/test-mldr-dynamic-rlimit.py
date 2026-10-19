#!/usr/bin/env python3
"""Prove the loader regression and fix using real Linux sockets and rlimits."""
from pathlib import Path
import argparse
import hashlib
import json
import resource
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True)
parser.add_argument('--baseline', default='runtime/source-input-history/de07d3198792372c19a3a85b41fdd7b683ff25c3131a464a60a6cdd7bbaf7a26/mldr.c')
args = parser.parse_args()
build = json.loads((root / args.build).read_text())
folder = Path(tempfile.mkdtemp(prefix='mldr-dynamic-rlimit-test-', dir=root / 'runtime'))
source = root / 'fixtures/hello/mldr-dynamic-rlimit.c'
mldr = root / 'vendor/darling/src/startup/mldr/mldr.c'
old = root / args.baseline
common = build['commands'][0]
common = common[:common.index('-c')]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(old) == 'de07d3198792372c19a3a85b41fdd7b683ff25c3131a464a60a6cdd7bbaf7a26'
assert sha(mldr) == build['files'][str(mldr.relative_to(root))]
cases = []
for tag, input in [('original-regression', old), ('fixed', mldr)]:
    executable = folder / tag
    command = [*common, '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
        '-DMLDR_SOURCE_FILE="' + str(input) + '"', str(source), '-o', str(executable)]
    with (folder / (tag + '-build.log')).open('w') as stream:
        subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT, check=True)
    def nocore():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = subprocess.run([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        preexec_fn=nocore, timeout=30)
    (folder / (tag + '.log')).write_bytes(result.stdout)
    print(tag, result.returncode, result.stdout.decode(), flush=True)
    cases.append(dict(tag=tag, status=result.returncode, command=command))
verified = cases[0]['status'] != 0 and cases[1]['status'] == 0 and \
    b'concurrent_roundtrips=256' in result.stdout
record = dict(verified=verified, cases=cases, build=args.build,
    files={str(p.relative_to(root)) if p.is_relative_to(root) else str(p): sha(p)
        for p in [Path(__file__), source, mldr, old, *folder.iterdir()] if p.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
