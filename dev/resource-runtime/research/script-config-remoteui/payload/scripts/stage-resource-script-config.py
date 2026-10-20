#!/usr/bin/env python3
"""Add real page-isolated script-config storage to an immutable libSystem stage."""
from pathlib import Path
import argparse, hashlib, json, runpy, shutil, struct, subprocess, sys

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--configuration', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root / ('runtime/resource-script-config-' + args.tag)
assert not folder.exists()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
config = json.loads((root / args.configuration).read_text())
base_path = config['resource_system_build']
assert sha(root / base_path) == config['resource_system_build_sha256']
base = json.loads((root / base_path).read_text())
assert base['full_initializer_and_queue_source_build'] and base['complete_source_files'] == 20
assert base['original_source_instructions_preserved']
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
for name, digest in base['files'].items(): resolve(name, digest)
for name, digest in base['link_inputs'].items(): assert sha(root / name) == digest
original = root / base['output']
assert sha(original) == base['output_sha256']
contract_path = root / 'artifacts/script-config-storage-original-contract-v1.json'
contract = json.loads(contract_path.read_text())
assert contract['verified'] and contract['storage_bytes'] == 16384
assert contract['original_zero_initialized'] and contract['required_x86_page_alignment'] == 4096
assert sha(root / ('runtime/fullsystem-libraries' + contract['provider'])) == contract['provider_sha256']
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = root / 'vendor/darling/src/external/libplatform/src/os/script_config.c'
(folder / 'libraries').mkdir(parents=True)
inherited_helpers = []
for sibling in original.parent.glob('*.dylib'):
    if sibling == original: continue
    destination = folder / 'libraries' / sibling.name
    shutil.copy2(sibling, destination)
    assert sha(destination) == sha(sibling)
    inherited_helpers.append(destination)
obj = folder / 'storage.o'
name = 'libDarlingScriptConfig.dylib'
helper = folder / 'libraries' / name
commands = [
    ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O2', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
     '-no_fixup_chains', '-no_adhoc_codesign', '-install_name', '/usr/lib/' + name,
     '-exported_symbol', '_os_script_config_storage', str(obj), '-o', str(helper)]]
for command in commands: subprocess.run(command, check=True)
data = helper.read_bytes()
symbols = subprocess.check_output(['llvm-nm-19', '--defined-only', '--extern-only', str(helper)], text=True).splitlines()
symbols = [s.split() for s in symbols if s.strip()]
assert len(symbols) == 1 and symbols[0][-1] == '_os_script_config_storage'
address = int(symbols[0][0], 16)
at = 32; found = []; executable_bytes = 0
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    kind, size = struct.unpack_from('<II', data, at)
    if kind == 0x19:
        for j in range(struct.unpack_from('<I', data, at + 64)[0]):
            s = at + 72 + 80 * j
            section = data[s:s+16].split(b'\0')[0]
            va, length, offset, align = struct.unpack_from('<QQII', data, s+32)
            flags = struct.unpack_from('<I', data, s+64)[0]
            if flags & 0x80000400: executable_bytes += length
            if section == b'__script_config':
                assert va == address and va % 4096 == 0 and length == 16384 and align >= 12
                assert not any(data[offset:offset+length]) and offset + length <= len(data)
                found.append(dict(address=hex(va), bytes=length, alignment=1 << align, file_offset=offset))
    at += size
assert len(found) == 1 and executable_bytes == 0
payload, changes = runpy.run_path(str(root / 'scripts/macho-named-reexport.py'))['add'](
    original.read_bytes(), '/usr/lib/' + name, ['_os_script_config_storage'])
assert changes['original_instructions_and_other_bytes_preserved']
library = folder / 'libraries/libSystem.B.dylib'; library.write_bytes(payload)
inputs = [Path(__file__), source, helper, library, *inherited_helpers, root/base_path, root/args.configuration,
          contract_path, root/'scripts/macho-named-reexport.py',
          root/'vendor/darling/src/external/libplatform/CMakeLists.txt']
report = {**base, 'parent_source_build': base_path, 'parent_source_build_sha256': sha(root/base_path),
    'parent_link_command': base['command'], 'command': [sys.executable, *sys.argv],
    'output': str(library.relative_to(root)), 'output_sha256': sha(library),
    'files': {**base['files'], **{str(p.relative_to(root)): sha(p) for p in inputs}},
    'link_inputs': {**base['link_inputs'], **{str(p.relative_to(root)):sha(p) for p in [helper, *inherited_helpers]}},
    'inherited_helper_bytes_preserved': {str(p.relative_to(root)):sha(p) for p in inherited_helpers},
    'script_storage_helper': str(helper.relative_to(root)), 'script_storage_helper_sha256': sha(helper),
    'storage_section': found[0], 'storage_helper_executable_bytes': executable_bytes,
    'storage_build_commands': commands, 'added_script_storage_reexport': changes,
    'runtime_execution_verified': False, 'full_Unity_build_verified': False}
(folder/'build.json').write_text(json.dumps(report, indent=2)+'\n')
print('BUILD_REPORT', folder/'build.json')
