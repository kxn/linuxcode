#!/usr/bin/env python3
"""Isolate the source TLS library's legacy CoreCrypto ABI from modern consumers."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-report',required=True);p.add_argument('--tag',required=True);p.add_argument('--corecrypto-build');a=p.parse_args();assert a.tag.replace('-','').isalnum()
base=json.loads((r/a.build_report).read_text());sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for key in ['backend','umbrella','corecrypto']:assert sha(r/base[key])==base[key+'_sha256']
selected_crypto=base['corecrypto']
if a.corecrypto_build:
    crypto_build=json.loads((r/a.corecrypto_build).read_text());assert crypto_build['full_CoreCrypto_source_build'] and crypto_build['complete_source_files']==56
    assert sha(r/crypto_build['library'])==crypto_build['library_sha256'];selected_crypto=crypto_build['library']
folder=r/('runtime/coretls-private-crypto-'+a.tag);folder.mkdir();libraries=folder/'libraries';libraries.mkdir()
def replace(data,kind,old,new):
    assert data[:4]==bytes.fromhex('cffaedfe');out=bytearray(data);cursor=32;matches=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,cursor)
        if cmd==kind:
            start=cursor+struct.unpack_from('<I',data,cursor+8)[0];end=data.index(0,start)
            if data[start:end].decode()==old:
                assert len(new.encode())+1<=cursor+size-start
                out[start:cursor+size]=new.encode().ljust(cursor+size-start,b'\0');matches.append([start,cursor+size])
        cursor+=size
    assert len(matches)==1
    first,last=matches[0];assert out[:first]==data[:first] and out[last:]==data[last:]
    return bytes(out),matches
name='/usr/lib/libTLSCrypto.dylib';old='/usr/lib/system/libcorecrypto.dylib'
backend,backend_changes=replace((r/base['backend']).read_bytes(),12,old,name)
crypto,crypto_changes=replace((r/selected_crypto).read_bytes(),13,old,name)
b=libraries/'libsystem_coretls.dylib';b.write_bytes(backend);c=libraries/'libTLSCrypto.dylib';c.write_bytes(crypto);u=libraries/'libcoretls.dylib'
original=(r/base['original_umbrella']).read_bytes()
if original[:4]==b'\xca\xfe\xba\xbe':
    arches=[struct.unpack_from('>5I',original,8+20*i) for i in range(struct.unpack_from('>I',original,4)[0])];chosen=[x for x in arches if x[0]==0x1000007];assert len(chosen)==1;off,size=chosen[0][2:4];original=original[off:off+size]
exports=sorted(set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(b)],text=True),re.M)));assert '_tls_cache_create' in exports and '_tls_handshake_create_for_caller' in exports
front,changes=runpy.run_path(str(r/'scripts/macho-named-reexport.py'))['add'](original,'/usr/lib/system/libsystem_coretls.dylib',exports);assert changes['original_instructions_and_other_bytes_preserved'];u.write_bytes(front)
record={**base,'parent_build_report':a.build_report,'parent_build_report_sha256':sha(r/a.build_report),'backend':str(b.relative_to(r)),'backend_sha256':sha(b),'umbrella':str(u.relative_to(r)),'umbrella_sha256':sha(u),'private_corecrypto':str(c.relative_to(r)),'private_corecrypto_sha256':sha(c),'private_corecrypto_install_name':name,'backend_load_command_changed_ranges':backend_changes,'crypto_ID_command_changed_ranges':crypto_changes,'all_other_original_bytes_preserved':True,'global_CoreCrypto_replaced':False,'runtime_execution_verified':False,'actual_TLS_handshake_verified':False,'tool_sha256':sha(Path(__file__))}
record.update(original_umbrella_reexport=changes,umbrella_namespace_exports=len(exports),corecrypto=selected_crypto,corecrypto_sha256=sha(r/selected_crypto),corecrypto_delta_build=a.corecrypto_build,corecrypto_delta_build_sha256=sha(r/a.corecrypto_build) if a.corecrypto_build else None)
(folder/'build.json').write_text(json.dumps(record,indent=2)+'\n');print('PRIVATE_TLS_CRYPTO_BUILD',folder/'build.json')
