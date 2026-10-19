#!/usr/bin/env python3
"""Independently inspect the actual Unity iPhoneOS GameAssembly archive."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--xcode-report', required=True)
parser.add_argument('--archive', required=True)
parser.add_argument('--report', required=True)
parser.add_argument('--kind', choices=['gameassembly', 'runtime', 'baselib'], default='gameassembly')
args = parser.parse_args()
report = root / args.report
assert not report.exists()
archive = root / args.archive
xcode = json.loads((root / args.xcode_report).read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
log = root / xcode['log']
assert sha(log) == xcode['log_sha256']
text = log.read_text(errors='replace')
record = dict(verified=False, xcode_report=args.xcode_report,
    xcode_report_sha256=sha(root / args.xcode_report),
    native_status=xcode['native_xcode_status'], outer_status=xcode['exit_status'],
    expected_archive=args.archive, expected_archive_exists=archive.is_file(),
    build_success_banner='** BUILD SUCCEEDED **' in text,
    log=xcode['log'], log_sha256=sha(log),
    inspection_source_sha256=sha(Path(__file__)),
    full_Unity_App_verified=False, CocoaPods_integration_verified=False,
    signing_verified=False)
record['archive_kind'] = args.kind
try:
    data = archive.read_bytes()
    assert data[:8] == b'!<arch>\n', 'Not a regular Unix archive'
    at = 8
    objects = []
    while at < len(data):
        header = data[at:at+60]
        assert len(header) == 60 and header[58:] == b'`\n', 'Invalid member header'
        length = int(header[48:58])
        begin, end = at + 60, at + 60 + length
        assert end <= len(data), 'Truncated archive member'
        name = header[:16].decode().strip()
        if name.startswith('#1/'):
            namesize = int(name[3:])
            assert namesize <= length
            name = data[begin:begin+namesize].rstrip(b'\0').decode()
            begin += namesize
        else:
            name = name.rstrip('/')
        member = data[begin:end]
        at = end + (length & 1)
        if name.startswith('__.SYMDEF') or name in ('', '/', '//', '/SYM64'):
            continue
        assert member[:4] == bytes.fromhex('cffaedfe'), 'Not a Mach-O 64 object: ' + name
        cpu, subtype, kind, count, command_size = struct.unpack_from('<5I', member, 4)
        assert cpu == 0x100000c and kind == 1, 'Not an arm64 relocatable object: ' + name
        pos = 32
        platforms = []
        for _ in range(count):
            command, size = struct.unpack_from('<II', member, pos)
            assert size >= 8 and pos + size <= 32 + command_size <= len(member)
            if command == 0x32:
                assert size >= 24
                platform, minimum, sdk = struct.unpack_from('<3I', member, pos+8)
                assert platform == 2, 'Not iPhoneOS (platform=2): ' + name
                platforms.append(dict(platform=platform, minimum=minimum, sdk=sdk))
            elif command in (0x24, 0x25, 0x2f, 0x30):
                assert command == 0x25 and size >= 16, 'Wrong minimum OS command: ' + name
                minimum, sdk = struct.unpack_from('<2I', member, pos+8)
                platforms.append(dict(platform=2, minimum=minimum, sdk=sdk))
            pos += size
        assert pos == 32 + command_size and platforms, 'Missing iPhoneOS platform metadata: ' + name
        objects.append(dict(name=name, sha256=hashlib.sha256(member).hexdigest(),
            bytes=len(member), cpu=cpu, subtype=subtype, platforms=platforms))
    assert at == len(data) and len(objects) >= (1 if args.kind == 'baselib' else 100), 'Missing Unity generated/runtime objects'
    nm = subprocess.run(['llvm-nm-19', '--defined-only', '--extern-only', str(archive)],
        cwd=root, capture_output=True, text=True, check=True)
    symbols = set(re.findall(r'^\S+\s+[A-Za-z]\s+(\S+)$', nm.stdout, re.M))
    # Unity emits its runtime implementation separately in il2cpp.a.
    # GameAssembly contains the generated code and registration objects.
    required = {'gameassembly': ['_g_CodeRegistration', '_g_MetadataRegistration'],
        'runtime': ['_il2cpp_init', '_il2cpp_runtime_invoke'],
        'baselib': ['__ZN14il2cpp_baselib23Baselib_Memory_AllocateEm']}[args.kind]
    assert all(symbol in symbols for symbol in required), 'Missing IL2CPP registration symbols'
    symbols_log = report.with_suffix('.symbols.log')
    assert not symbols_log.exists()
    symbols_log.write_text(nm.stdout)
    record.update(verified=xcode['native_xcode_status'] == ['0'] and xcode['exit_status'] == 0
        and record['build_success_banner'], archive_sha256=sha(archive), archive_bytes=len(data),
        objects=objects, arm64_iPhoneOS_objects=len(objects), required_symbols=required,
        defined_external_symbols=len(symbols), symbols_log=str(symbols_log.relative_to(root)),
        symbols_log_sha256=sha(symbols_log))
except (AssertionError, OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
    record['inspection_error'] = str(error) or type(error).__name__
report.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: value for key, value in record.items() if key != 'objects'}, indent=2))
raise SystemExit(0 if record['verified'] else 1)
