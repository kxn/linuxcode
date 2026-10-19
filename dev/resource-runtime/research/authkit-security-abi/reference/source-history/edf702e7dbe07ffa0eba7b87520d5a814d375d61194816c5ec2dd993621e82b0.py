#!/usr/bin/env python3
"""Select a separately verified original Security image for resource tools."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', required=True)
parser.add_argument('--inspection', required=True)
parser.add_argument('--tag', required=True)
parser.add_argument('--reexport-session-types', action='store_true',
    help='Resolve the five old session compatibility classes through original Security')
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
pins = json.loads((root/'config/coregraphics-image-pins.json').read_text())
pin = pins[args.target]
assert pin['path'] == '/System/Library/Frameworks/Security.framework/Versions/A/Security'
source = 'runtime/rebuilt-'+args.target+'/Security'
reconstruction = 'runtime/rebuilt-'+args.target+'/reconstruction.json'
report = json.loads((root/reconstruction).read_text())
inspection = json.loads((root/args.inspection).read_text())
assert inspection['verified'] and inspection['original_code_bytes_equal']
assert inspection['optimized_TLV_descriptors_verified'] == len(report.get('optimized_tlv_restoration', []))
assert inspection['files'][source] == sha(source) == report['staged_image_sha256']
assert inspection['files'][reconstruction] == sha(reconstruction)
original = 'runtime/fullsystem-libraries'+pin['path']
assert sha(original) == pin['sha256'] == report['original_image_sha256']
assert report['rip_instructions_patched'] == 0 and not report['backend_call_overrides']
symbols = set(subprocess.check_output(['llvm-nm-19', '-gj', str(root/source)], text=True).splitlines())
required = {'_OBJC_CLASS_$_OTControlArguments', '_kSecAttrSharingGroup'}
assert required <= symbols
folder = root/('runtime/security-resource-original-'+args.tag)
output = root/('artifacts/security-resource-original-'+args.tag+'-stage.json')
assert not folder.exists() and not output.exists()
framework = folder/'frameworks/Security.framework'
destination = framework/'Versions/A/Security'
destination.parent.mkdir(parents=True)
(folder/'libraries').mkdir()
shutil.copy2(root/source, destination)
(framework/'Versions/Current').symlink_to('A')
(framework/'Security').symlink_to('Versions/Current/Security')
inputs = ['config/coregraphics-image-pins.json', source, reconstruction, original,
          args.inspection, str(Path(__file__).relative_to(root))]
session_reexports = None
if args.reexport_session_types:
    previous = 'runtime/native-library-stage/libDarlingSecuritySessionValues.dylib'
    names = subprocess.check_output(['llvm-nm-19', '--defined-only', '--extern-only', '-j',
                                    str(root/previous)], text=True).splitlines()
    classes = {'SecSessionInfo', 'SecExternalPreSharedKey', 'ExternalPreSharedKey', 'SecOfferedEPSK', 'OfferedEPSK'}
    required_names = {prefix+name for prefix in ('_OBJC_CLASS_$_', '_OBJC_METACLASS_$_') for name in classes}
    assert len(names) == 10 and set(names) == required_names and required_names <= symbols
    # Give the header-only facade space for a named load command. The hidden
    # padding is data, with no exported function or Objective-C definition.
    padding = folder/'layout-padding.c'
    padding.write_text('__attribute__((used, visibility("hidden"))) const char linuxcode_reexport_layout_pad[256] = {0};\n')
    sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
    obj = folder/'layout-padding.o'
    subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
                    '-c', str(padding), '-o', str(obj)], check=True)
    facade = folder/'libraries/libDarlingSecuritySessionValues.dylib'
    subprocess.run(['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
        '-syslibroot', str(root/'runtime/rootfs/usr/libexec/darling'), '-lSystem',
        '-install_name', '/usr/lib/libDarlingSecuritySessionValues.dylib', str(obj), '-o', str(facade)], check=True)
    helper = runpy.run_path(str(root/'scripts/macho-named-reexport.py'))
    payload, session_reexports = helper['add'](facade.read_bytes(), pin['path'], sorted(required_names))
    facade.write_bytes(payload)
    inputs += [previous, 'scripts/macho-named-reexport.py']
files = {name: sha(name) for name in inputs}
files.update({str(p.relative_to(root)): sha(str(p.relative_to(root)))
              for p in folder.rglob('*') if p.is_file() and not p.is_symlink()})
links = {str(p.relative_to(root)): os.readlink(p) for p in folder.rglob('*') if p.is_symlink()}
output.write_text(json.dumps(dict(installed=False, frameworks=str((folder/'frameworks').relative_to(root)),
    libraries=str((folder/'libraries').relative_to(root)), files=files, links=links,
    original_security_target=args.target, original_executable_bytes_preserved=True,
    required_exports=sorted(required), exported_symbols=len(symbols),
    original_session_class_reexports=session_reexports,
    runtime_execution_verified=False, signing_with_original_security_verified=False), indent=2)+'\n')
print(output.relative_to(root))
