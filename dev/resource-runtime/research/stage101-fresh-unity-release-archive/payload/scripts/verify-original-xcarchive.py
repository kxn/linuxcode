#!/usr/bin/env python3
"""Inspect a real original-xcodebuild archive and separately report symbol coverage."""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import re
import struct
import subprocess
import tempfile
import uuid

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--archive',required=True)
evidence=p.add_mutually_exclusive_group(required=True);evidence.add_argument('--build-report');evidence.add_argument('--cli-invocation')
p.add_argument('--independent-products',required=True);p.add_argument('--report',required=True)
p.add_argument('--dwarf-verifier',help='Native LLVM dwarfdump executable used for a complete --verify pass on each dSYM')
p.add_argument('--require-dsyms',action='store_true');a=p.parse_args()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
archive=(r/a.archive).resolve(strict=True);assert archive.is_relative_to(r/'runtime')
if a.build_report:
    build=json.loads((r/a.build_report).read_text());native_evidence=a.build_report;plan=None
else:
    invocation=r/a.cli_invocation;result=json.loads((invocation/'result.json').read_text());plan=json.loads((invocation/'plan.json').read_text())
    assert result['native_exit_status']==result['outer_exit_status']==result['exit_status']==0
    build=dict(exit_status=result['exit_status'],native_xcode_status=['0'],xcode_arguments=plan['mapped_argv'],
               log=str((invocation/'output.log').relative_to(r)),log_sha256=result['log_sha256'])
    native_evidence=str((invocation/'result.json').relative_to(r))
independent=json.loads((r/a.independent_products).read_text())
assert build['exit_status']==0 and build['native_xcode_status']==['0']
assert sha(r/build['log'])==build['log_sha256'];log=(r/build['log']).read_text()
assert '** ARCHIVE SUCCEEDED **' in log and 'archive' in build['xcode_arguments']
guest='/Volumes/SystemRoot/workspace/';arg=build['xcode_arguments'][build['xcode_arguments'].index('-archivePath')+1]
expected=r/arg[len(guest):] if arg.startswith(guest) else Path(arg);assert expected.resolve()==archive
info=plistlib.loads((archive/'Info.plist').read_bytes());assert info['ArchiveVersion']==2
assert info['SchemeName']==build['xcode_arguments'][build['xcode_arguments'].index('-scheme')+1]
name=Path(info['ApplicationProperties']['ApplicationPath']);assert not name.is_absolute() and '..' not in name.parts
app=archive/'Products'/name;assert app.is_dir()
metadata=plistlib.loads((app/'Info.plist').read_bytes());assert metadata['CFBundleIdentifier']==info['ApplicationProperties']['CFBundleIdentifier']
assert independent['verified'] and str(app.relative_to(r)) in independent['checks']
assert independent['checks'][str(app.relative_to(r))]['verified']

def macho(data):
    if data[:4]==bytes.fromhex('cafebabe'):
        count=struct.unpack_from('>I',data,4)[0];assert 0<count<=64 and 8+20*count<=len(data)
        rows=[]
        for i in range(count):
            cpu,subtype,offset,size,align=struct.unpack_from('>5I',data,8+20*i)
            assert offset+size<=len(data)
            slices=macho(data[offset:offset+size]);assert all(row['cpu']==cpu for row in slices);rows+=slices
        return rows
    assert data[:4] in [bytes.fromhex('cffaedfe'),bytes.fromhex('cefaedfe')]
    magic,cpu,subtype,filetype,ncmds,size=struct.unpack_from('<6I',data)
    at=32 if magic==0xfeedfacf else 28;end=at+size;assert end<=len(data)
    result=dict(cpu=cpu,subtype=subtype,filetype=filetype,UUID=None,platform=None,DWARF_debug_info_bytes=0,DWARF_version=None)
    for _ in range(ncmds):
        cmd,length=struct.unpack_from('<2I',data,at);assert length>=8 and at+length<=end
        if cmd==0x1b:
            assert length==24 and result['UUID'] is None;result['UUID']=str(uuid.UUID(bytes=data[at+8:at+24])).upper()
        if cmd==0x32:
            assert length>=24;result['platform']=struct.unpack_from('<I',data,at+8)[0]
        if cmd==0x25:result['platform']=2
        if cmd==0x19:
            assert length>=72
            sections=struct.unpack_from('<I',data,at+64)[0];assert 72+80*sections<=length
            for index in range(sections):
                section=at+72+80*index
                section_name=data[section:section+16].split(b'\0')[0]
                segment_name=data[section+16:section+32].split(b'\0')[0]
                if segment_name==b'__DWARF' and section_name==b'__debug_info':
                    size=struct.unpack_from('<Q',data,section+40)[0];offset=struct.unpack_from('<I',data,section+48)[0]
                    assert offset+size<=len(data);result['DWARF_debug_info_bytes']=size
                    if size:
                        initial=struct.unpack_from('<I',data,offset)[0];header=12 if initial==0xffffffff else 4
                        assert size>=header+4;version=struct.unpack_from('<H',data,offset+header)[0]
                        assert 2<=version<=5;result['DWARF_version']=version
        at+=length
    assert at==end and result['UUID'];return [result]

binary=app/metadata['CFBundleExecutable'];main=macho(binary.read_bytes())
assert all(row['cpu']==0x100000c and row['platform']==2 for row in main)
assert info['ApplicationProperties']['Architectures']==['arm64']
products={metadata['CFBundleExecutable']:main}
for framework in sorted((app/'Frameworks').glob('*.framework')):
    fi=plistlib.loads((framework/'Info.plist').read_bytes());products[fi['CFBundleExecutable']]=macho((framework/fi['CFBundleExecutable']).read_bytes())
symbols={};dwarf_folder=Path(tempfile.mkdtemp(prefix='xcarchive-dwarf-verification-',dir=r/'runtime')) if a.dwarf_verifier else None
for path in sorted((archive/'dSYMs').glob('*.dSYM/Contents/Resources/DWARF/*')):
    assert path.is_file();rows=macho(path.read_bytes())
    assert all(row['filetype']==0xa and row['DWARF_debug_info_bytes']>0 for row in rows), 'standalone symbol file has no actual DWARF debug data'
    assert path.name in products, 'symbol file has no matching product: '+path.name
    actual={(row['cpu'],row['UUID']) for row in rows};expected={(row['cpu'],row['UUID']) for row in products[path.name]}
    assert actual==expected, 'dSYM UUID does not match archived executable: '+path.name
    symbols[path.name]=dict(path=str(path.relative_to(r)),sha256=sha(path),slices=rows)
    if dwarf_folder:
        command=[a.dwarf_verifier,'--verify',str(path)];log_path=dwarf_folder/(str(len(symbols))+'.log')
        with log_path.open('w') as out:verified=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
        assert verified.returncode==0, 'LLVM DWARF verification failed: '+str(log_path.relative_to(r))
        symbols[path.name]['LLVM_DWARF_verification']=dict(command=command,exit_status=verified.returncode,
                                                        private_log=str(log_path.relative_to(r)),private_log_sha256=sha(log_path))
if a.require_dsyms:
    assert metadata['CFBundleExecutable'] in symbols and 'UnityFramework' in symbols, 'app and UnityFramework standalone symbols are required'
record=dict(verified=True,archive=a.archive,archive_info_sha256=sha(archive/'Info.plist'),archive_version=info['ArchiveVersion'],
            scheme=info['SchemeName'],application=str(app.relative_to(r)),identifier=metadata['CFBundleIdentifier'],
            products=products,standalone_symbols=symbols,standalone_symbol_products=len(symbols),
            LLVM_DWARF_verification=bool(symbols) and bool(a.dwarf_verifier),
            standalone_symbols_required=a.require_dsyms,standalone_symbol_generation_verified=bool(symbols),
            embedded_provisioning_profile_present=(app/'embedded.mobileprovision').is_file(),
            build_report=a.build_report,build_report_sha256=sha(r/a.build_report) if a.build_report else None,
            cli_invocation=a.cli_invocation,native_evidence=native_evidence,native_evidence_sha256=sha(r/native_evidence),
            cli_plan_sha256=sha(r/a.cli_invocation/'plan.json') if plan else None,
            independent_products=a.independent_products,independent_products_sha256=sha(r/a.independent_products),
            native_archive_status=0,outer_status=0,CompileC_tasks=len(re.findall(r'^CompileC ',log,re.M)),
            CodeSign_tasks=len(re.findall(r'^CodeSign ',log,re.M)),developer_provisioning_or_device_trust_verified=False,
            verifier_sha256=sha(Path(__file__)),full_goal_complete=False)
out=r/a.report;assert not out.exists();out.write_text(json.dumps(record,indent=2)+'\n');print(out)
