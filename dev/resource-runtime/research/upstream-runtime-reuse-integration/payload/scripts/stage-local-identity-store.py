#!/usr/bin/env python3
"""Build an opt-in native Security identity query facade without changing defaults."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, struct, subprocess, runpy, plistlib

ROOT = Path(__file__).resolve().parent.parent
HELPER = runpy.run_path(str(ROOT / 'scripts/macho-named-reexport.py'))
NAMES = ['_SecItemCopyMatching', '_SecIdentityCopyPreference',
         '_SecItemCopyParentCertificates_osx', '_SecIdentityCreateWithCertificate']
INSTALL_NAME = '/System/Library/Frameworks/Security.framework/Versions/A/Security'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def layout(binary):
    assert binary[:8] == bytes.fromhex('cffaedfe07000001')
    at = 32
    export = linkedit = None
    sections = []
    for _ in range(struct.unpack_from('<I', binary, 16)[0]):
        command, size = struct.unpack_from('<II', binary, at)
        if command == 0x19:
            if binary[at + 8:at + 24].split(b'\0')[0] == b'__LINKEDIT':
                linkedit = at
            for i in range(struct.unpack_from('<I', binary, at + 64)[0]):
                section = at + 72 + 80 * i
                flags = struct.unpack_from('<I', binary, section + 64)[0]
                if flags & 255 not in (1, 12, 18):  # skip zero-fill sections
                    offset = struct.unpack_from('<I', binary, section + 48)[0]
                    length = struct.unpack_from('<Q', binary, section + 40)[0]
                    if offset and length:
                        sections.append((offset, length))
        elif command in (0x22, 0x80000022, 0x80000033):
            export = at + (8 if command == 0x80000033 else 40)
        elif command == 0x1d:
            raise ValueError('Refuse a stale code signature')
        at += size
    assert export is not None and linkedit is not None
    offset, size = struct.unpack_from('<II', binary, export)
    return export, linkedit, HELPER['entries'](binary[offset:offset + size]), sections


def preserve_original_entries(binary):
    export, linkedit, old, _ = layout(binary)
    new = dict(old)
    for name in NAMES:
        original = old[name.encode()]
        assert original[0] == 0, (name, 'expected a direct function export')
        alias = ('_linuxcode_original_' + name[1:]).encode()
        assert alias not in new
        new[alias] = original
    fresh = HELPER['trie'](new)
    result = bytearray(binary)
    result.extend(bytes(-len(result) % 8))
    offset = len(result)
    result.extend(fresh)
    struct.pack_into('<II', result, export, offset, len(fresh))
    fileoff = struct.unpack_from('<Q', binary, linkedit + 40)[0]
    size = len(result) - fileoff
    struct.pack_into('<Q', result, linkedit + 48, size)
    struct.pack_into('<Q', result, linkedit + 32, (size + 4095) & ~4095)
    allowed = (set(range(export, export + 8)) | set(range(linkedit + 32, linkedit + 40))
               | set(range(linkedit + 48, linkedit + 56)))
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(binary, result)))
    assert layout(result)[2] == new
    return bytes(result)



def build_common_owner(args):
    base = (ROOT / args.common_owner_base).resolve(strict=True)
    assert base.is_relative_to(ROOT / 'runtime')
    folder = ROOT / ('runtime/local-identity-store-' + args.tag)
    folder.mkdir()
    framework = folder / 'frameworks/Security.framework'
    output = framework / 'Versions/A/Security'
    output.parent.mkdir(parents=True)
    (framework / 'Versions/Current').symlink_to('A')
    (framework / 'Security').symlink_to('Versions/Current/Security')
    original = base.read_bytes()
    initial_exports = layout(original)[2]
    assert len(initial_exports) >= 4594
    output.write_bytes(preserve_original_entries(original))
    sdk = ROOT / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
    source = ROOT / 'vendor/darling/src/external/security/OSX/sec/Security/SecLocalIdentityStore.c'
    obj = folder / 'store.o'
    library = folder / 'libraries/libDarlingCommonIdentityStore.dylib'
    library.parent.mkdir()
    exports = folder / 'store.exports'
    selected_names = list(NAMES)
    objects = [obj]
    extra_inputs = []
    trust_sources = None
    commands = []

    def run(command):
        result = subprocess.run([str(v) for v in command], capture_output=True, text=True)
        commands.append(dict(command=[str(v) for v in command], returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        assert result.returncode == 0, result.stderr
        return result.stdout

    run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', sdk, '-O2',
         '-Wno-deprecated-declarations', '-DLINUXCODE_IDENTITY_COMMON_OWNER=1',
         '-c', source, '-o', obj])
    if args.trust_service_source:
        security = ROOT / 'vendor/darling/src/external/security'
        template = ROOT / 'runtime/trustd-source-nnzdc_2n/compile-state.json'
        state = json.loads(template.read_text())
        reference = next(value for key, value in state.items() if key.endswith('/SecPolicyServer.c'))
        command = reference['command']
        command = command[:command.index('-MMD')]
        include = folder / 'include/os'
        include.mkdir(parents=True)
        # The Darling header replaces feature decisions with zero. The actual
        # shared runtime already provides Apple's feature-flag ABI via libSystem.
        # Preserve the source macro's domain/name arguments and default value.
        feature_header = include / 'feature_private.h'
        feature_header.write_text(
            '#pragma once\n#include <stdbool.h>\n'
            'bool _os_feature_enabled_impl(const char *, const char *);\n'
            'bool _os_feature_enabled_simple_impl(const char *, const char *, bool);\n'
            '#define os_feature_enabled(domain,name) _os_feature_enabled_impl(#domain,#name)\n'
            '#define os_feature_enabled_simple(domain,name,value) _os_feature_enabled_simple_impl(#domain,#name,value)\n')
        ot_source = security / 'keychain/ot/OTConstants.m'
        ot_obj = folder / 'OTConstants.o'
        dep = folder / 'OTConstants.d'
        run([command[0], '-I' + str(folder / 'include'), *command[1:], '-fobjc-arc',
             '-MMD', '-MF', dep, '-c', ot_source, '-o', ot_obj])
        # Use the complete upstream list and its exact definition macro, so
        # policy spelling and CFString representation have one source of truth.
        policy_source = security / 'OSX/sec/Security/SecPolicy.c'
        policy_list = security / 'OSX/sec/Security/SecPolicyChecks.list'
        text = policy_source.read_text()
        start = text.index('#undef POLICYCHECKMACRO')
        end = text.index('#include "SecPolicyChecks.list"', start)
        policy_constants = folder / 'SecPolicyCheckConstants.c'
        policy_constants.write_text('#include <CoreFoundation/CoreFoundation.h>\n' +
                                    text[start:end] + '#include "' + str(policy_list) + '"\n')
        policy_obj = folder / 'SecPolicyCheckConstants.o'
        run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', sdk, '-O2',
             '-c', policy_constants, '-o', policy_obj])
        additions = ['_SecErrorIsNestedErrorCappingEnabled',
                     '_SecErrorSetOverrideNestedErrorCappingIsEnabled',
                     '_kSecPolicyCheckKeyUsageReportOnly']
        assert not any(name.encode() in initial_exports for name in additions)
        selected_names += additions
        objects += [ot_obj, policy_obj]
        import shlex
        dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
        extra_inputs += [template, feature_header, ot_source, ot_obj, policy_source,
                         policy_list, policy_constants, policy_obj, dep]
        extra_inputs += [Path(name) for name in dependencies if Path(name).is_file()]
        trust_sources = dict(complete_OTConstants_source=True, complete_policy_check_list=True,
                             feature_flag_backend='existing original FeatureFlags through libSystem',
                             override_setter_preserved=True, added_exports=additions,
                             compile_template=str(template.relative_to(ROOT)))
    exports.write_text('\n'.join(selected_names) + '\n')
    run(['ld64.lld-19', '-dylib', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
         '-syslibroot', sdk, '-F', framework.parent, '-framework', 'Security',
         '-framework', 'CoreFoundation', '-lobjc',
         *(['-L', ROOT / 'runtime/resource-plain-fork-system-v1/libraries'] if args.trust_service_source else []),
         '-lSystem', '-install_name', '/usr/lib/' + library.name,
         '-dead_strip', '-exported_symbols_list', exports, *objects, '-o', library])
    payload, redirects = HELPER['add'](output.read_bytes(), '/usr/lib/' + library.name,
                                      selected_names, replace_existing=True)
    output.write_bytes(payload)
    final_exports = layout(payload)[2]
    assert set(initial_exports) <= set(final_exports)
    assert all(final_exports[name] == terminal for name, terminal in initial_exports.items()
               if name.decode() not in NAMES)
    for name in NAMES:
        assert final_exports[('_linuxcode_original_' + name[1:]).encode()] == initial_exports[name.encode()]
    assert all(original[offset:offset + size] == payload[offset:offset + size]
               for offset, size in layout(original)[3])
    assert set(layout(library.read_bytes())[2]) == {name.encode() for name in selected_names}
    binds = run(['llvm-objdump-19', '--macho', '--bind', '--lazy-bind', library])
    assert 'libDarlingLocalIdentitySecurityBackend' not in binds
    for name in NAMES:
        assert '_linuxcode_original_' + name[1:] in binds
    factory_names = ['_SecIdentityCreate', '_SecCertificateCreateWithData', '_SecKeyCreateWithData']
    for name in factory_names:
        assert any('Security' in line and name in line for line in binds.splitlines()), name
    if args.trust_service_source:
        assert any('libSystem' in line and '__os_feature_enabled_impl' in line for line in binds.splitlines())
    loads = run(['llvm-objdump-19', '--macho', '--dylibs-used', library])
    assert INSTALL_NAME in loads and 'LocalIdentitySecurityBackend' not in loads
    assert '/System/Library/Frameworks/Foundation.framework/' not in loads, 'Preserve original Security upward Foundation edge'
    assert b'libDarlingLocalIdentitySecurityBackend' not in library.read_bytes()
    assert b'libDarlingSecurityCodeSignerCompatibility' not in library.read_bytes()
    files = [base, source, Path(__file__), ROOT / 'scripts/macho-named-reexport.py', obj,
             output, library, exports, *extra_inputs]
    report = dict(host_verified=True, native_verified=False, installed=False,
                  base=str(base.relative_to(ROOT)), framework=str(output.relative_to(ROOT)),
                  library=str(library.relative_to(ROOT)), original_exports=len(initial_exports),
                  candidate_exports=len(final_exports), replaced_queries=NAMES,
                  original_entry_aliases_preserved=True, original_section_bytes_preserved=True,
                  unchanged_export_payloads=len(initial_exports) - len(NAMES),
                  object_factories_owner=INSTALL_NAME, old_security_backend_loaded=False,
                  trust_service_source=trust_sources, component_direct_Foundation_dependency=False,
                  fallback='direct references to the four original common-owner aliases',
                  namespace_cycle='Security -> store component -> same Security; no component constructors',
                  limits=['No native lifecycle or signing test yet.',
                          'Internal direct calls in original Security retain their original implementation.',
                          'securityd/trustd integration remains unverified with this owner.'],
                  files={str(p.relative_to(ROOT)): digest(p) for p in files if p.is_relative_to(ROOT)},
                  toolchain_headers={str(p): digest(p) for p in files if not p.is_relative_to(ROOT)},
                  redirects=redirects, commands=commands)
    report_path = folder / 'build.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(report_path.relative_to(ROOT))


r=Path(__file__).resolve().parent.parent
a=argparse.ArgumentParser();a.add_argument('--tag',required=True);a.add_argument('--export-overlay-base');a.add_argument('--backend-base');a.add_argument('--csparser-build');a.add_argument('--common-owner-base', help='Complete modern Security image: preserve original queries as aliases; never load a second Security owner');a.add_argument('--trust-service-source',action='store_true',help='Modern owner: compile the complete upstream OTConstants unit and policy-check macro list');args=a.parse_args()
assert re.fullmatch('[a-z0-9-]+',args.tag)
if args.common_owner_base:
    assert not any([args.export_overlay_base, args.backend_base, args.csparser_build])
    build_common_owner(args)
    raise SystemExit(0)
assert not args.trust_service_source, '--trust-service-source requires --common-owner-base'
w=r/('runtime/local-identity-store-'+args.tag);assert not w.exists();w.mkdir()
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
base=r/(args.backend_base or 'runtime/security-cryptokit-constants/frameworks/Security.framework/Versions/A/Security')
source=r/'vendor/darling/src/external/security/OSX/sec/Security/SecLocalIdentityStore.c'
backend=w/'libraries/libDarlingLocalIdentitySecurityBackend.dylib';backend.parent.mkdir();shutil.copyfile(base,backend)
payload=bytearray(backend.read_bytes());assert struct.unpack_from('<I',payload)[0]==0xfeedfacf
offset=32;changed=0
for _ in range(struct.unpack_from('<I',payload,16)[0]):
    cmd,size=struct.unpack_from('<II',payload,offset)
    if cmd==0xd:
        start=offset+struct.unpack_from('<I',payload,offset+8)[0];end=offset+size
        name=('/usr/lib/'+backend.name).encode()+b'\0';assert len(name)<=end-start
        payload[start:end]=name+b'\0'*(end-start-len(name));changed+=1
    offset+=size
assert changed==1;backend.write_bytes(payload)
obj=w/'store.o'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-Wno-deprecated-declarations','-c',str(source),'-o',str(obj)],check=True)
library=w/'frameworks/Security.framework/Versions/A/Security';library.parent.mkdir(parents=True)
subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreFoundation','-lSystem','-install_name','/System/Library/Frameworks/Security.framework/Versions/A/Security','-compatibility_version','1.0.0','-current_version','60157.40.30','-headerpad','0x1000','-reexport_library',str(backend),str(obj),'-o',str(library)],check=True)
framework=library.parents[2];(framework/'Versions/Current').symlink_to('A');(framework/'Security').symlink_to('Versions/Current/Security')
overlay_inputs=[]
if args.export_overlay_base:
    facade=w/'libraries/libDarlingLocalIdentityStore.dylib'
    subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreFoundation','-lSystem','-install_name','/usr/lib/'+facade.name,'-reexport_library',str(backend),str(obj),'-o',str(facade)],check=True)
    overlay_base=r/args.export_overlay_base
    payload,_=runpy.run_path(str(r/'scripts/macho-named-reexport.py'))['add'](overlay_base.read_bytes(),'/usr/lib/'+facade.name,['_SecItemCopyMatching','_SecIdentityCopyPreference','_SecItemCopyParentCertificates_osx','_SecIdentityCreateWithCertificate'],replace_existing=True)
    library.write_bytes(payload);overlay_inputs=[overlay_base,facade]
if args.csparser_build:
    parser=json.loads((r/args.csparser_build).read_text());parser_binary=r/parser['binary'];assert hashlib.sha256(parser_binary.read_bytes()).hexdigest()==parser['binary_sha256']
    bundle=library.parent/'PlugIns/csparser.bundle';shutil.copytree(r/parser['bundle'],bundle)
    resources=library.parent/'Resources';resources.mkdir()
    original_resources=r/'runtime/rootfs/usr/libexec/darling/System/Library/Frameworks/Security.framework/Versions/A/Resources'
    for resource in original_resources.iterdir():
        if resource.is_file() and resource.suffix in ('.mds','.mdsinfo'):
            target=resources/resource.name;shutil.copy2(resource,target);overlay_inputs += [resource,target]
    (resources/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='com.apple.security',CFBundleExecutable='Security',CFBundleName='Security compatibility',CFBundlePackageType='FMWK',CFBundleVersion='59306.61.1')))
    (framework/'Resources').symlink_to('Versions/Current/Resources');(framework/'PlugIns').symlink_to('Versions/Current/PlugIns')
    overlay_inputs += [parser_binary,*[p for p in bundle.rglob('*') if p.is_file()],resources/'Info.plist']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(source=str(source.relative_to(r)),framework=str(library.relative_to(r)),root=str(w.relative_to(r)),files={str(p.relative_to(r)):sha(p) for p in [source,base,backend,library,*overlay_inputs]},read_only=True,encrypted_store=False,certificate_trust_evaluated=False,supported_key_types=['RSA PKCS1 DER'],installed=False)
report=r/('artifacts/local-identity-store-'+args.tag+'-stage.json');assert not report.exists();report.write_text(json.dumps(record,indent=2)+'\n');print(report)
