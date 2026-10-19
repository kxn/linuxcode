#!/usr/bin/env python3
"""Expose selected original SIMD routines without replacing existing libm APIs."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--base-stage', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root / ('runtime/native-simd-math-' + args.tag)
output = root / ('artifacts/native-simd-math-' + args.tag + '-stage.json')
assert not folder.exists() and not output.exists()
sha = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
base = json.loads((root/args.base_stage).read_text())
for path, expected in base['files'].items():
    if path.startswith(('scripts/', 'config/', 'vendor/')):
        resolve(path, expected)
    else:
        assert sha(path) == expected, path
manifest = 'config/coregraphics-image-pins.json'
pin = json.loads((root/manifest).read_text())['simd-math-resource-native']
original = 'runtime/fullsystem-libraries' + pin['path']
source = 'runtime/rebuilt-simd-math-resource-native/libsystem_m.dylib'
reconstruction = 'runtime/rebuilt-simd-math-resource-native/reconstruction.json'
report = json.loads((root/reconstruction).read_text())
assert sha(original) == pin['sha256'] == report['original_image_sha256']
assert sha(source) == report['staged_image_sha256']
assert not report['modern_adapter'] and not report['redirected_imports'] and not report['backend_call_overrides']
names = ['___invert_f3', '__simd_exp2_f4', '__simd_exp_f4',
         '__simd_log2_f4', '__simd_log_f4', '__simd_pow_f4', '__simd_sin_f4']
exports = subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(root/source)],text=True)
assert set(names) <= {line.split()[-1] for line in exports.splitlines() if line.split()}
library = folder/'libraries/libSystem.B.dylib'
library.parent.mkdir(parents=True)
helper = folder/'libraries/libDarlingNativeSIMDMath.dylib'
shutil.copy2(root/source, helper)
payload, changes = runpy.run_path(str(root/'scripts/macho-named-reexport.py'))['add'](
    (root/base['library']).read_bytes(), pin['standalone_install_name'], names)
library.write_bytes(payload)
files = {**base['files'], **{p:sha(p) for p in [args.base_stage,manifest,
    original,source,reconstruction,str(helper.relative_to(root)),str(library.relative_to(root)),
    'scripts/stage-native-simd-math.py','scripts/rebuild-c-cache-image.py']}}
record = dict(library=str(library.relative_to(root)), helper=base['helper'], files=files,
    additional_libraries=[*base.get('additional_libraries',[]),str(helper.relative_to(root))],
    export_changes=changes, original_math_image=source, original_math_sha256=sha(original),
    original_routines_preserved=True, installed=False, runtime_execution_verified=False)
output.write_text(json.dumps(record,indent=2)+'\n')
print(output.relative_to(root))
