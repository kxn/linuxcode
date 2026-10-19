#!/usr/bin/env python3
"""Build real rich-error objects over the pinned existing libxpc backend."""
from pathlib import Path
import hashlib
import json
import runpy
import subprocess
import argparse

project=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--test-bad-connection-guard',action='store_true')
parser.add_argument('--source-peer-error', help='Verified full source libxpc build report supplying the singleton')
parser.add_argument('--output-dir', help='Fresh output directory for a source-peer variant')
parser.add_argument('--report', help='Fresh report path for a source-peer variant')
args=parser.parse_args()
assert bool(args.source_peer_error) == bool(args.output_dir) == bool(args.report)
if args.source_peer_error:
    assert not args.test_bad_connection_guard
    source_peer=json.loads((project/args.source_peer_error).read_text())
    assert source_peer['full_libxpc_source_build']
    source_library=project/source_peer['variant_root']/'usr/lib/system/libxpc.dylib'
    assert hashlib.sha256(source_library.read_bytes()).hexdigest()==source_peer['library_sha256']
    exported=subprocess.check_output(['llvm-nm-19','-g',str(source_library)],text=True)
    assert '__xpc_error_peer_code_signing_requirement' in exported
    assert not (project/args.output_dir).exists() and not (project/args.report).exists()
config=json.loads((project/'config/xpc-rich-error.json').read_text())
backend=project/'vendor/darling/src/external/libxpc'
if subprocess.check_output(['git','-C',str(backend),'rev-parse','HEAD'],text=True).strip()!=config['backend_source_commit']:
    raise ValueError('Changed backend source revision')
for relative,digest in config['backend_files'].items():
    # These pins describe the packaged fallback, not the independently built
    # source libxpc working tree. Its binary hash and runtime code/UUID guard
    # still protect raw layout access; modern backends use their own public SPI.
    baseline=subprocess.check_output(['git','-C',str(backend),'show',config['backend_source_commit']+':'+relative])
    if hashlib.sha256(baseline).hexdigest()!=digest:
        raise ValueError('Changed packaged-backend reference layout: '+relative)
    # Rich-error and immutable peer-error objects still share these layouts
    # with source libxpc. Only connection layout/code is delegated to its SPI.
    if relative not in ('src/connection.m','internal-include/xpc/objects/connection.h'):
        if hashlib.sha256((backend/relative).read_bytes()).hexdigest()!=digest:
            raise ValueError('Changed shared XPC object layout: '+relative)
if hashlib.sha256((project/config['backend_library']).read_bytes()).hexdigest()!=config['backend_sha256']:
    raise ValueError('Changed backend binary')
native=config['native_reference']
if hashlib.sha256((project/'runtime/fullsystem-libraries'/native['path'].lstrip('/')).read_bytes()).hexdigest()!=native['sha256']:
    raise ValueError('Changed native reference')
ns=runpy.run_path(str(project/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':project/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':project/'runtime/fullsystem-libraries'})
for name,routine in native['routines'].items():
    payload=bytes.fromhex(routine['bytes'])
    address=ns['resolve'](native['path'],name)
    if address!=int(routine['address'],0) or ns['read'](address,len(payload))!=payload:
        raise ValueError('Changed native API routine: '+name)
peer=native['peer_error'];address=ns['resolve'](native['path'],'__xpc_error_peer_code_signing_requirement')
entry=ns['pointer'](address+peer['entry_pointer_offset'])
string=ns['pointer'](entry+peer['entry_string_offset'])
text=ns['pointer'](string+peer['string_text_offset'])
expected=peer['text'].encode()+b'\0'
if address!=int(peer['export_address'],0) or text!=int(peer['text_address'],0) or ns['read'](text,len(expected))!=expected:
    raise ValueError('Changed native peer-requirement error description')
sdk=project/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
for relative,digest in config['sdk_files'].items():
    if hashlib.sha256((sdk/relative).read_bytes()).hexdigest()!=digest:raise ValueError('Changed SDK contract')
build=project/'runtime/xpc-rich-error';build.mkdir(exist_ok=True)
if args.source_peer_error:
    build=project/args.output_dir;build.mkdir()
if args.test_bad_connection_guard:
    build=build/'bad-connection-guard';build.mkdir(exist_ok=True)
connection=config['connection_backend']
uuid=bytearray.fromhex(connection['uuid'])
if args.test_bad_connection_guard:uuid[0]^=1
header='static const unsigned char connection_backend_uuid[]={'+','.join(hex(b) for b in uuid)+'};\n'
header+='static const unsigned char connection_cancel_event_bytes[]={'+','.join(hex(b) for b in bytes.fromhex(connection['cancel_event_code_bytes']))+'};\n'
header+='static const uintptr_t connection_cancel_event_offset='+connection['cancel_event_code_address']+';\n'
header+='enum { connection_backend_size='+str(connection['instance_size'])+', connection_cancelled_offset='+str(connection['cancelled_offset'])+' };\n'
(build/'connection-backend.h').write_text(header)
obj=build/'rich-error.o'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),
    *(['-DLINUXCODE_XPC_PEER_ERROR_FROM_BACKEND=1'] if args.source_peer_error else []),
    '-I',str(build),'-fblocks','-O2','-c',str(project/'scripts/xpc-rich-error-compat.m'),'-o',str(obj)],check=True)
guest=project/'runtime/rootfs/usr/libexec/darling'
output=project/'runtime/native-library-stage/libDarlingXPCRichError.dylib'
if args.source_peer_error:output=build/output.name
if args.test_bad_connection_guard:output=build/output.name
temporary=output.with_name(output.name+'.pending')
subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11',
    '-syslibroot',str(guest),'-L',str(guest/'usr/lib'),'-L',str(guest/'usr/lib/system'),
    '-lSystem','-lobjc','-lxpc','-install_name','/usr/lib/libDarlingXPCRichError.dylib',
    str(obj),'-o',str(temporary)],check=True)
temporary.replace(output)
if args.source_peer_error:
    reexport=runpy.run_path(str(project/'scripts/macho-existing-reexport.py'))
    payload,preservation=reexport['add'](output.read_bytes(),'/usr/lib/system/libxpc.dylib',
        ['__xpc_error_peer_code_signing_requirement'])
    output.write_bytes(payload)
report={'installed':False,'execution_verified':False,'full_compatibility':False,
    'library_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
    'packaged_backend_reference_files_verified_from_pinned_commit':True,
    'shared_object_worktree_layout_files_verified':True,
    'source_compatibility_sha256':hashlib.sha256((project/'scripts/xpc-rich-error-compat.m').read_bytes()).hexdigest(),
    'scope':'Actual owned rich-error objects, description/retry APIs and legacy-XPC peer-error singleton. Connection APIs delegate only to symbols owned by the actual connection backend; packaged fallback retains its UUID/code/layout guard. Descriptions reflect actual cancellation state, not detailed modern causes. Peer-signing enforcement is unsupported with no success claim or connection mutation. No modern sessions or peer verification implementation.'}
if not args.test_bad_connection_guard:
    if args.source_peer_error:
        report.update(source_peer_error_build=args.source_peer_error,source_peer_error_sha256=source_peer['library_sha256'],
            existing_provider_reexport=preservation,source_peer_singleton_owned_by_adapter=False,
            output=str(output.relative_to(project)))
    (project/(args.report or 'artifacts/xpc-rich-error-compat.json')).write_text(json.dumps(report,indent=2)+'\n')
print('Built',output.relative_to(project))
