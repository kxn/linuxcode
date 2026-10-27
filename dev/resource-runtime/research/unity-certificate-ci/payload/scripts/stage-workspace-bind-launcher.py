#!/usr/bin/env python3
"""Add isolated workspace mappings to a new copy of a pinned native launcher."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy

r = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-stage', required=True)
p.add_argument('--tag', required=True)
a = p.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
parent = json.loads((r / a.parent_stage).read_text())
resolve = runpy.run_path(str(r / 'scripts/resolve-evidence-history.py'))['resolve']
launcher = r / parent['launcher']
namespace = launcher.with_name('runtime-ns.sh')
for path in [launcher, namespace]:
    assert sha(path) == parent['files'][str(path.relative_to(r))]
folder = r / 'runtime' / ('workspace-bind-launcher-' + a.tag)
folder.mkdir(exist_ok=False)
old = str(launcher.parent.relative_to(r))
new = str(folder.relative_to(r))
body = launcher.read_text()
assert body.count(old + '/runtime-ns.sh') == 1
(folder / 'darling').write_text(body.replace(old + '/runtime-ns.sh', new + '/runtime-ns.sh'))
body = namespace.read_text()
needle = 'mount --bind "$project" "$rootfs/workspace"\n'
assert body.count(needle) == 1
addition = ('if [[ -n ${LINUXCODE_WORKSPACE_BINDINGS:-} ]]; then\n'
            '    /usr/bin/python3 "$project/scripts/workspace-bindings.py" "$project" "$rootfs" "$LINUXCODE_WORKSPACE_BINDINGS"\n'
            'fi\n')
(folder / 'runtime-ns.sh').write_text(body.replace(needle, needle + addition))
for path in folder.iterdir(): path.chmod(0o755)
record = dict(parent_stage=a.parent_stage, parent_stage_sha256=sha(r / a.parent_stage),
              parent_launcher=parent['launcher'], launcher=new + '/darling',
              namespace_private=True, installed=False,
              files={str(path.relative_to(r)): sha(path) for path in
                     [launcher, namespace, folder / 'darling', folder / 'runtime-ns.sh',
                      Path(__file__), r / 'scripts/workspace-bindings.py']})
out = r / 'artifacts' / ('workspace-bind-launcher-' + a.tag + '-stage.json')
assert not out.exists()
out.write_text(json.dumps(record, indent=2) + '\n')
print(out)
