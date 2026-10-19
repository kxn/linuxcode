#!/usr/bin/env python3
"""Independently inspect the real iOS product and linked CocoaPod archive."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, plistlib, struct, subprocess

root = Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--products',type=Path,default=Path('runtime/ios-cocoapods-build/DerivedData/Build/Products/Debug-iphoneos'))
parser.add_argument('--report',type=Path,default=Path('artifacts/ios-cocoapods-product.json'))
args=parser.parse_args()
products = root / args.products
app = products / 'iOSCocoaPodsSmoke.app'
binary = app / 'iOSCocoaPodsSmoke'
archive = products / 'LocalMath/libLocalMath.a'
data = binary.read_bytes()
magic, cpu, subtype, kind, commands, size, flags, reserved = struct.unpack_from('<8I', data)
assert magic == 0xfeedfacf and cpu == 0x0100000c and kind == 2, 'Expected real arm64 Mach-O executable'
cursor = 32
build_version = None
for _ in range(commands):
    cmd, length = struct.unpack_from('<II', data, cursor)
    assert length >= 8 and cursor + length <= len(data)
    if cmd == 0x32: build_version = struct.unpack_from('<III', data, cursor + 8)
    cursor += length
assert build_version and build_version[0] == 2, 'Expected iPhoneOS platform'
plist = plistlib.loads((app / 'Info.plist').read_bytes())
assert plist['CFBundleSupportedPlatforms'] == ['iPhoneOS']
assert plist['CFBundleIdentifier'] == 'org.linuxcode.iOSCocoaPodsSmoke'
symbols = subprocess.check_output(['llvm-nm-19', str(binary)], text=True)
assert any(line.endswith(' T _local_add') for line in symbols.splitlines())
assert any(line.strip() == 'U _UIApplicationMain' for line in symbols.splitlines())
members = subprocess.check_output(['llvm-ar-19', 't', str(archive)], text=True).splitlines()
assert 'LocalMath.o' in members
files = [binary, archive, app / 'Info.plist', app / 'PkgInfo', root / 'fixtures/iOSCocoaPodsSmoke/main.m',
         root / 'fixtures/iOSCocoaPodsSmoke/LocalMath/LocalMath.c']
record = dict(checked_at=datetime.now(timezone.utc).isoformat(), verified=True,
              platform='iPhoneOS', architecture='arm64', bundle_identifier=plist['CFBundleIdentifier'],
              minimum_OS=plist['MinimumOSVersion'], build_version=build_version,
              real_Pod_archive_member='LocalMath.o', real_Pod_symbol_linked='_local_add',
              UIKit_entry_import='_UIApplicationMain',
              files={str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
              device_execution_verified=False, signing_verified=False, engine_generated_project=False)
output=root/args.report
output.parent.mkdir(parents=True,exist_ok=True)
if output.exists():
    old=output.read_bytes();sha=hashlib.sha256(old).hexdigest();archive=root/'artifacts/ios-product-verification-history'/sha;archive.mkdir(parents=True,exist_ok=True);(archive/output.name).write_bytes(old)
output.write_text(json.dumps(record, indent=2) + '\n')
print('REAL_IOS_ARM64_APP_AND_LINKED_COCOAPOD_PRODUCT_VERIFIED')
