#!/usr/bin/env python3
"""Run original actool and ibtool serially; require native tool success markers."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, runpy, subprocess
root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', default='artifacts/ios-resource-coretheme-stage.json')
parser.add_argument('--tag', default='coretheme')
parser.add_argument('--runtime-profile', default='scripts/ios-resource-closure-profile.py')
parser.add_argument('--graphics-stage')
args = parser.parse_args()
assert re.fullmatch(r'[a-z0-9-]+', args.tag)
module = runpy.run_path(str(root / args.runtime_profile))
p = module['profile'](stage=args.stage,**({'graphics_stage':args.graphics_stage} if args.graphics_stage else {}))
output = root / ('artifacts/ios-resource-' + args.tag + '-version-probes.json')
assert not output.exists(), 'Keep previous probe evidence immutable'
digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
cases = []
gui_variables = ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY')
host_environment = module['environment'](p)
for name in gui_variables:
    host_environment.pop(name, None)
for tool in ('actool', 'ibtool'):
    script = 'runtime/ios-resource-probe/' + tool + '.sh'
    command = p['command'][:-2] + ['/usr/bin/env',
        *[argument for name in gui_variables for argument in ('-u', name)],
        '/bin/bash', '/Volumes/SystemRoot/workspace/' + script]
    command[3] = '90'
    log = 'logs/ios-resource-' + args.tag + '-' + tool + '-version.log'
    assert not (root / log).exists()
    with (root / log).open('w') as stream:
        result = subprocess.run(command, env=host_environment, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
    text = (root / log).read_text()
    status = re.findall(r'^ORIGINAL_RESOURCE_TOOL_STATUS (\d+)$', text, re.M)
    cases.append(dict(tool=tool, command=command, wrapper_exit_status=result.returncode,
        script=script, script_sha256=digest(script), log=log, log_sha256=digest(log),
        native_status=status, native_success_marker=result.returncode == 0 and status == ['0']))
    print(tool, 'native status:', status, '\n', text[-2500:], flush=True)
record = dict(checked_at=datetime.now(timezone.utc).isoformat(), stage=args.stage, stage_sha256=digest(args.stage),
    gui_environment_removed=list(gui_variables), runtime_profile=args.runtime_profile, runtime_profile_sha256=digest(args.runtime_profile),
    selected_cg_colorspace_names=p.get('source_cg_colorspace_names'),
    source_ios_resource_frameworks=p['source_ios_resource_frameworks'], cases=cases,
    tool_version_checks_passed=all(c['native_success_marker'] for c in cases), full_resource_compilation_verified=False)
output.write_text(json.dumps(record, indent=2) + '\n')
raise SystemExit(0 if record['tool_version_checks_passed'] else 1)
