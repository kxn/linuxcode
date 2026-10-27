#!/usr/bin/env python3
"""Restore dependencies on a private licensed UE source copy using a host Linux SDK."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', default='vendor/unreal-engine')
parser.add_argument('--sdk-root', default='runtime/unreal-dotnet-linux-x64-v1')
parser.add_argument('--configuration', default='Development')
parser.add_argument('--seed-packages', help='Optional existing complete host cache to copy; it is never modified')
args = parser.parse_args()
source = (root / args.source).resolve(strict=True)
sdk = (root / args.sdk_root).resolve(strict=True)
executable = sdk / 'dotnet'
assert executable.read_bytes()[:4] == b'\x7fELF', 'The dependency-preparation SDK must be a native Linux build'
assert (source / 'Engine/Source/Programs/UnrealBuildTool/UnrealBuildTool.csproj').is_file()
pin = json.loads((root / 'config/unreal-dotnet-linux-sdk-10.0.203.json').read_text())
assert subprocess.check_output([str(executable), '--version'], text=True).strip() == pin['version']
folder = Path(tempfile.mkdtemp(prefix='unreal-nuget-prefetch-', dir=root / 'runtime')); folder.chmod(0o700)
copied = folder / 'source'; (copied / 'Engine/Source').mkdir(parents=True)
for name in ['Directory.Build.props', 'Directory.Build.targets', 'global.json', 'NuGet.Config', 'NuGet.config']:
    if (source / name).is_file(): subprocess.run(['cp', '-a', '--reflink=auto', str(source / name), str(copied / name)], check=True)
for name in ['Engine/Build', 'Engine/Config', 'Engine/Platforms', 'Engine/Source/Programs']:
    if (source / name).exists(): subprocess.run(['cp', '-a', '--reflink=auto', str(source / name), str(copied / name)], check=True)
home = folder / 'home'; home.mkdir()
if args.seed_packages:
    seed = (root / args.seed_packages).resolve(strict=True)
    assert seed.is_dir()
    subprocess.run(['cp', '-a', '--reflink=auto', str(seed), str(folder / 'packages')], check=True)
else: (folder / 'packages').mkdir()
environment = dict(os.environ)
environment.update(HOME=str(home), DOTNET_CLI_HOME=str(home), NUGET_PACKAGES=str(folder / 'packages'),
                   DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='1',
                   DOTNET_GENERATE_ASPNET_CERTIFICATE='false')
command = [str(executable), 'restore', 'Programs/UnrealBuildTool/UnrealBuildTool.csproj',
           '--packages', str(folder / 'packages'), '-p:Configuration=' + args.configuration, '--verbosity', 'minimal']
log = folder / 'restore.log'; print('RESTORING', folder.relative_to(root), flush=True)
with log.open('w') as stream: result = subprocess.run(command, cwd=copied / 'Engine/Source', env=environment, stdout=stream, stderr=subprocess.STDOUT)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
record = dict(status=result.returncode, command=command, log=str(log.relative_to(root)), log_sha256=sha(log),
              source=str(source), private_source_copy=True, licensed_Epic_source_not_for_publication=True,
              configuration=args.configuration, SDK_pin_sha256=sha(root / 'config/unreal-dotnet-linux-sdk-10.0.203.json'),
              dependency_restore_only=True, original_macOS_UBT_build_proof=False,
              packages_ready=result.returncode == 0, driver_sha256=sha(Path(__file__)))
(folder / 'restore-result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder.relative_to(root) / 'restore-result.json')
raise SystemExit(result.returncode)
