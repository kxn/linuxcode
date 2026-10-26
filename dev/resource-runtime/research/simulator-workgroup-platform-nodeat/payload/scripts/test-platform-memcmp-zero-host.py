#!/usr/bin/env python3
"""Run the actual platform implementation with ASan/UBSan and guard pages."""
from pathlib import Path
import hashlib, json, subprocess, tempfile
root = Path(__file__).resolve().parent.parent
folder = Path(tempfile.mkdtemp(prefix='platform-memcmp-zero-host-', dir=root / 'runtime'))
source = root / 'vendor/darling/src/external/libplatform/src/string/generic/memcmp_zero.c'
fixture = root / 'fixtures/hello/platform-memcmp-zero.c'
headers = folder / 'include/platform'
headers.mkdir(parents=True)
header = headers / 'string.h'
header.write_text('#include <stddef.h>\n#include <stdint.h>\nunsigned long _platform_memcmp_zero_aligned8(const void *, size_t);\n')
exe = folder / 'probe'
command = ['gcc', '-O2', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
           '-I' + str(folder / 'include'), str(source), str(fixture), '-o', str(exe)]
subprocess.run(command, check=True)
log = folder / 'run.log'
with log.open('w') as out:
    r = subprocess.run([str(exe)], stdout=out, stderr=subprocess.STDOUT, timeout=60)
text = log.read_text()
verified = r.returncode == 0 and 'PLATFORM_MEMCMP_ZERO_ALIGNED8_BOUNDARIES_AND_ALL_BYTE_POSITIONS_OK' in text
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
report = dict(verified=verified, host_status=r.returncode, command=command,
              log=str(log.relative_to(root)), log_sha256=sha(log),
              files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), source, fixture, header]},
              scope='Exact production C implementation; minimal test-only header supplies types and prototype, no implementation.',
              full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(text[-3000:]); print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
