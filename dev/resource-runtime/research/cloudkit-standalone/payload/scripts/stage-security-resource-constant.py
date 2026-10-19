#!/usr/bin/env python3
"""Stage one verified CFString identifier through the existing Security facade."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import shutil
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reference', required=True)
parser.add_argument('--base', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag.isalnum()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
r = json.loads((root/args.reference).read_text())
assert r['symbol'] == '_kSecAttrSharingGroup' and r['value'] == 'ggrp'
assert sha('runtime/fullsystem-libraries'+r['provider']) == r['provider_sha256']
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
slot = ns['resolve'](r['provider'], r['symbol'])
obj = ns['pointer'](slot)
isa = ns['resolve']('/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation',
                    '___CFConstantStringClassReference')
assert slot == int(r['slot'], 16) and obj == int(r['object'], 16) and ns['pointer'](obj) == isa
assert struct.unpack('<Q', ns['read'](obj+8, 8))[0] == int(r['object_flags'], 16)
assert struct.unpack('<Q', ns['read'](obj+24, 8))[0] == len(r['value'])
assert ns['read'](ns['pointer'](obj+16), len(r['value'])) == r['value'].encode()
source = 'vendor/darling/src/external/security/OSX/sec/Security/SecResourceConstants.c'
assert 'const CFStringRef kSecAttrSharingGroup = CFSTR("ggrp");' in (root/source).read_text()
folder = root/('runtime/security-resource-constant-'+args.tag)
report = root/('artifacts/security-resource-constant-'+args.tag+'-stage.json')
assert not folder.exists() and not report.exists()
folder.mkdir()
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
objfile = folder/'constant.o'
subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
    '-c', str(root/source), '-o', str(objfile)], check=True)
libraries = folder/'libraries'
libraries.mkdir()
library = libraries/'libDarlingSecurityResourceConstants.dylib'
subprocess.run(['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-syslibroot', str(root/'runtime/rootfs/usr/libexec/darling'), '-lSystem', '-framework', 'CoreFoundation',
    '-install_name', '/usr/lib/'+library.name, str(objfile), '-o', str(library)], check=True)
framework = folder/'frameworks/Security.framework'
framework.parent.mkdir()
shutil.copytree((root/args.base).parents[2], framework, symlinks=True)
output = framework/'Versions/A/Security'
helper = runpy.run_path(str(root/'scripts/macho-named-reexport.py'))
payload, preservation = helper['add']((root/args.base).read_bytes(), '/usr/lib/'+library.name, [r['symbol']])
output.write_bytes(payload)
files = {name: sha(name) for name in [source, args.reference, args.base,
    'scripts/stage-security-resource-constant.py', 'scripts/macho-named-reexport.py']}
files.update({str(p.relative_to(root)): sha(str(p.relative_to(root))) for p in folder.rglob('*')
              if p.is_file() and not p.is_symlink()})
links = {str(p.relative_to(root)): os.readlink(p) for p in folder.rglob('*') if p.is_symlink()}
data = dict(installed=False, frameworks=str((folder/'frameworks').relative_to(root)),
    libraries=str(libraries.relative_to(root)), files=files, links=links,
    reference=args.reference, preservation=preservation, identifier_only=True,
    sharing_operations_implemented=False, runtime_execution_verified=False)
report.write_text(json.dumps(data, indent=2)+'\n')
print(report.relative_to(root))
