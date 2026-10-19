#!/usr/bin/env python3
"""Expose original native rootless token logic without replacing its result."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--base-stage', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root / ('runtime/native-system-resource-exports-' + args.tag)
output = root / ('artifacts/native-system-resource-exports-' + args.tag + '-stage.json')
assert not folder.exists() and not output.exists()
sha = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
base = json.loads((root / args.base_stage).read_text())
for p, expected in base['files'].items():
    assert sha(p) == expected, p
native = 'runtime/foundation-native-library-stage/libDarlingNativeSandbox.dylib'
reconstruction = 'runtime/rebuilt-sandbox-native/reconstruction.json'
assert sha(native) == json.loads((root/reconstruction).read_text())['staged_image_sha256']
library = folder / 'libraries/libSystem.B.dylib'
library.parent.mkdir(parents=True)
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = 'scripts/rootless-token-native-loader.c'
obj = folder/'loader.o'
helper = folder/'libraries/libDarlingRootlessToken.dylib'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-install_name','/usr/lib/libDarlingRootlessToken.dylib',str(obj),'-o',str(helper)],check=True)
payload, changes = runpy.run_path(str(root/'scripts/macho-named-reexport.py'))['add'](
    (root/base['library']).read_bytes(), '/usr/lib/libDarlingRootlessToken.dylib',
    ['_rootless_trusted_by_self_token', '_rootless_verify_trusted_by_self_token',
     '_sandbox_extension_release_file'])
library.write_bytes(payload)
files = {**base['files'], args.base_stage:sha(args.base_stage), native:sha(native), reconstruction:sha(reconstruction), str(library.relative_to(root)):sha(str(library.relative_to(root)))}
files.update({p:sha(p) for p in [source,str(helper.relative_to(root))]})
record = dict(library=str(library.relative_to(root)), helper=base['helper'], files=files,
              additional_libraries=[str(helper.relative_to(root))],
              export_changes=changes, original_token_logic_preserved=True,
              original_provider=native, installed=False, runtime_execution_verified=False,
              platform_trust_enforcement_verified=False)
output.write_text(json.dumps(record, indent=2)+'\n')
print(output.relative_to(root))
