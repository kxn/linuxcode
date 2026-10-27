#!/usr/bin/env python3
"""Bind a resolver configuration into one private Darling mount namespace."""
from pathlib import Path
import argparse
import hashlib
import json

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--parent-stage', required=True)
parser.add_argument('--resolver-file', default='/etc/resolv.conf')
args = parser.parse_args()
assert args.tag.replace('-', '').isalnum()
parent = json.loads((root / args.parent_stage).read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name, expected in parent['files'].items():
    assert digest(root / name) == expected, name
source = root / parent['launcher']
folder = root / ('runtime/native-resolver-launcher-' + args.tag)
folder.mkdir(exist_ok=False)
resolver = Path(args.resolver_file).resolve(strict=True)
text = resolver.read_text()
assert any(line.split()[:1] == ['nameserver'] for line in text.splitlines())
snapshot = folder / 'resolv.conf'
snapshot.write_text(text)
namespace = (source.parent / 'runtime-ns.sh').read_text()
needle = '        /usr/bin/mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs /state/prefix/private/tmp\n'
assert namespace.count(needle) == 1
relative = str(snapshot.relative_to(root))
addition = ('    # Use the caller-selected DNS configuration only in this session.\n'
            '    /usr/bin/nsenter --target "$account_server_pid" --mount \\\n'
            '        /usr/bin/mount --bind "/workspace/' + relative + '" /state/prefix/private/etc/resolv.conf\n'
            '    /usr/bin/nsenter --target "$account_server_pid" --mount \\\n'
            '        /usr/bin/mount -o remount,bind,ro /state/prefix/private/etc/resolv.conf\n')
(folder / 'runtime-ns.sh').write_text(namespace.replace(needle, needle + addition))
old = str((source.parent / 'runtime-ns.sh').relative_to(root))
new = str((folder / 'runtime-ns.sh').relative_to(root))
launcher = source.read_text()
assert launcher.count(old) == 1
(folder / 'darling').write_text(launcher.replace(old, new))
for name in ['darling', 'runtime-ns.sh']:
    (folder / name).chmod(0o755)
report = dict(parent_stage=args.parent_stage, parent_stage_sha256=digest(root / args.parent_stage),
              parent_launcher=str(source.relative_to(root)), launcher=str((folder / 'darling').relative_to(root)),
              private_resolver_binding=True, host_and_prefix_resolver_contents_preserved=True,
              resolver_snapshot=str(snapshot.relative_to(root)), installed=False,
              files={str(p.relative_to(root)): digest(p) for p in
                     [source, source.parent / 'runtime-ns.sh', *folder.iterdir(), Path(__file__),
                      root / 'scripts/native-resolver-runtime-profile.py']})
output = root / ('artifacts/native-resolver-launcher-' + args.tag + '-stage.json')
assert not output.exists()
output.write_text(json.dumps(report, indent=2) + '\n')
print(output.relative_to(root))
