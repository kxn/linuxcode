#!/usr/bin/env python3
"""Freeze a private codesign adapter and namespace; leave the shared prefix intact."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,shutil
r=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag',required=True);parser.add_argument('--dispatch-stage',required=True);parser.add_argument('--zsign-build',required=True);a=parser.parse_args();assert re.fullmatch('[a-z0-9-]+',a.tag)
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
m=runpy.run_path(str(r/'scripts/resource-tool-dispatch-profile.py'));p=m['profile'](dispatch_stage=a.dispatch_stage);assert p['system_version_binding']
build=json.loads((r/a.zsign_build).read_text());backend=r/build['binary'];assert build['static_ELF_verified'] and sha(backend)==build['binary_sha256'];assert build['source']==json.loads((r/'config/zsign-source.json').read_text())
folder=r/('runtime/codesign-zsign-'+a.tag);descriptor=r/('artifacts/codesign-zsign-'+a.tag+'-stage.json');assert not folder.exists() and not descriptor.exists();folder.mkdir()
relative=str(folder.relative_to(r));guest='/Volumes/SystemRoot/workspace/';ruby_source=r/'scripts/codesign-zsign.rb';ruby=folder/'codesign-zsign.rb';shutil.copy2(ruby_source,ruby)
gems=['CFPropertyList-3.0.6','rexml-3.3.9'];gem_files={}
for gem in gems:
 base=r/'runtime/state/prefix/Library/Ruby/Gems/2.6.0/gems'/gem/'lib';assert base.is_dir()
 gem_files.update({str(path.relative_to(r)):sha(path) for path in base.rglob('*') if path.is_file()})
wrapper=folder/'codesign';values=['/usr/bin/env','-u','DYLD_LIBRARY_PATH','-u','DYLD_FRAMEWORK_PATH','LINUXCODE_ZSIGN_ELF='+guest+build['binary'],'/usr/bin/ruby','--disable-gems']
for gem in gems:values+=['-I','/Library/Ruby/Gems/2.6.0/gems/'+gem+'/lib']
values += [guest+str(ruby.relative_to(r))]
wrapper.write_text('#!/bin/sh\nexec '+shlex.join(values)+' "$@"\n');wrapper.chmod(0o755)
namespace_source=r/'scripts/runtime-system-version-ns.sh';namespace=folder/'runtime-ns.sh';text=namespace_source.read_text();needle='        /usr/bin/mount --bind "/workspace/$system_version_relative" /state/prefix/System/Library/CoreServices/SystemVersion.plist\n';assert text.count(needle)==1
binding='    /usr/bin/nsenter --target "$metadata_server_pid" --mount \\\n        /usr/bin/mount --bind '+shlex.quote('/workspace/'+str(wrapper.relative_to(r)))+' /state/prefix/usr/bin/codesign\n'
namespace.write_text(text.replace(needle,needle+binding));namespace.chmod(0o755)
launcher_source=r/'bin/darling-system-version';launcher=folder/'darling';text=launcher_source.read_text();needle='/.." && pwd -P)';assert text.count(needle)==1;text=text.replace(needle,'/../.." && pwd -P)');needle='"$project/scripts/runtime-system-version-ns.sh"';assert text.count(needle)==1;text=text.replace(needle,'"$project/'+str(namespace.relative_to(r))+'"');launcher.write_text(text);launcher.chmod(0o755)
entry=r/'runtime/state/prefix/usr/bin/codesign';record=dict(dispatch_stage=a.dispatch_stage,dispatch_stage_sha256=sha(r/a.dispatch_stage),zsign_build=a.zsign_build,zsign_build_sha256=sha(r/a.zsign_build),ruby_gem_files=gem_files,files={str(path.relative_to(r)):sha(path) for path in [ruby,wrapper,namespace,launcher,backend]},source_inputs={str(path.relative_to(r)):sha(path) for path in [ruby_source,namespace_source,launcher_source]},launcher=str(launcher.relative_to(r)),original_persistent_codesign=str(entry.relative_to(r)),original_persistent_codesign_sha256=sha(entry),persistent_prefix_modified=False,default_entry_promoted=False,original_codesign_frontend_used=False,certificate_signing_implemented=False,nested_code_signing_implemented=False)
descriptor.write_text(json.dumps(record,indent=2)+'\n');print(descriptor.relative_to(r))
