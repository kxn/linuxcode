#!/usr/bin/env python3
"""Stage a private native /private/tmp filesystem without changing old launchers."""
from pathlib import Path
import argparse,hashlib,json
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tag',required=True);a=p.parse_args();assert a.tag.replace('-','').isalnum();source=r/'runtime/dyld-bootstrap-fcntl-launcher-v5';folder=r/('runtime/native-temporary-launcher-'+a.tag);folder.mkdir(exist_ok=False);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
launcher=(source/'darling').read_text();old=str(source.relative_to(r));new=str(folder.relative_to(r));assert launcher.count(old+'/runtime-ns.sh')==1;(folder/'darling').write_text(launcher.replace(old+'/runtime-ns.sh',new+'/runtime-ns.sh'))
namespace=(source/'runtime-ns.sh').read_text();conditional='if [[ -n ${account_database_relative:-} || -n ${developer_overlay_relative:-} || -n ${apple_overlay_relative:-} ]]; then';assert namespace.count(conditional)==1;namespace=namespace.replace(conditional,'if true; then',1)
needle='    [[ $account_server_pid =~ ^[0-9]+$ && $(cat "/proc/$account_server_pid/comm") == darlingserver ]] || exit 2\n';assert namespace.count(needle)==1
addition='''    # Keep Darwin temporary-directory operations off the prefix overlay. This
    # filesystem lives only in this session and preserves the backing contents.
    /usr/bin/nsenter --target "$account_server_pid" --mount \\
        /usr/bin/mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs /state/prefix/private/tmp
''';(folder/'runtime-ns.sh').write_text(namespace.replace(needle,needle+addition))
for f in folder.iterdir():f.chmod(0o755)
record=dict(parent_launcher=str((source/'darling').relative_to(r)),launcher=str((folder/'darling').relative_to(r)),private_temporary_tmpfs=True,prefix_backing_contents_preserved=True,installed=False,files={str(p.relative_to(r)):sha(p) for p in [source/'darling',source/'runtime-ns.sh',folder/'darling',folder/'runtime-ns.sh',Path(__file__),r/'scripts/native-temporary-runtime-profile.py']})
out=r/('artifacts/native-temporary-launcher-'+a.tag+'-stage.json');assert not out.exists();out.write_text(json.dumps(record,indent=2)+'\n');print(out.relative_to(r))
