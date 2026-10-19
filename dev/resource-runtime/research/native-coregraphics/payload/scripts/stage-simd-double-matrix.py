#!/usr/bin/env python3
"""Build the double SIMD identity and compare its actual bytes to the Intel cache."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root / ('runtime/simd-double-matrix-' + args.tag)
output = root / ('artifacts/simd-double-matrix-' + args.tag + '-stage.json')
assert not folder.exists() and not output.exists()
sha = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
cache = runpy.run_path(str(root / 'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root / 'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root / 'runtime/fullsystem-libraries'})
provider = '/usr/lib/system/libsystem_m.dylib'
address = cache['resolve'](provider, '_matrix_identity_double3x3')
assert address
original = cache['read'](address, 96)
assert struct.unpack('<12d', original) == (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.)
source = 'vendor/darling/src/libm/Source/simd_double_constants.c'
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
(folder / 'libraries').mkdir(parents=True)
obj = folder / 'constants.o'
helper = folder / 'libraries/libDarlingSIMDDoubleMatrix.dylib'
subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O2', '-c', str(root/source), '-o', str(obj)], check=True)
subprocess.run(['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(sdk), '-lSystem', '-install_name', '/usr/lib/libDarlingSIMDDoubleMatrix.dylib', str(obj), '-o', str(helper)], check=True)
actual = helper.read_bytes()
nm = subprocess.check_output(['llvm-nm-19', str(helper)], text=True)
symbol = int(next(row.split()[0] for row in nm.splitlines() if row.endswith(' _matrix_identity_double3x3')), 16)
at = 32
value = None
for _ in range(struct.unpack_from('<I', actual, 16)[0]):
    cmd, length = struct.unpack_from('<II', actual, at)
    if cmd == 0x19:
        vm, size, off, filesz = struct.unpack_from('<QQQQ', actual, at + 24)
        if vm <= symbol and symbol + 96 <= vm + filesz:
            value = actual[off+symbol-vm:off+symbol-vm+96]
    at += length
assert value == original and symbol % 16 == 0
base = 'runtime/simd-matrix-source/libraries/libSystem.B.dylib'
expected = json.loads((root/'artifacts/simd-matrix-source-stage.json').read_text())
assert sha(base) == expected['library_sha256']
payload, changes = runpy.run_path(str(root/'scripts/macho-named-reexport.py'))['add'](
    (root/base).read_bytes(), '/usr/lib/libDarlingSIMDDoubleMatrix.dylib', ['_matrix_identity_double3x3'])
library = folder / 'libraries/libSystem.B.dylib'
library.write_bytes(payload)
files = [source, base, str(helper.relative_to(root)), str(library.relative_to(root))]
record = dict(library=str(library.relative_to(root)), helper=str(helper.relative_to(root)),
              files={p:sha(p) for p in files}, provider=provider,
              provider_sha256=sha('runtime/fullsystem-libraries'+provider),
              original_address=hex(address), original_bytes=original.hex(),
              source_bytes_equal_original=True, source_alignment=16,
              export_changes=changes, installed=False, runtime_execution_verified=False)
output.write_text(json.dumps(record, indent=2)+'\n')
print(output.relative_to(root))
