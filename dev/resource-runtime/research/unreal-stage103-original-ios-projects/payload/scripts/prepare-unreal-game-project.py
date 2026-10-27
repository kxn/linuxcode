#!/usr/bin/env python3
"""Create a fresh, ordinary UE C++ game fixture without modifying engine source."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import tempfile
import uuid

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--name', default='LinuxcodeUESmoke')
parser.add_argument('--output-dir')
args = parser.parse_args()
name = args.name
assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name)
if args.output_dir:
    folder = (root / args.output_dir).resolve()
    assert folder.is_relative_to(root / 'runtime') and not folder.exists()
    folder.mkdir(parents=True)
else:
    folder = Path(tempfile.mkdtemp(prefix='unreal-game-project-', dir=root / 'runtime'))
(folder / 'Source' / name).mkdir(parents=True)
(folder / 'Config').mkdir()
files = {
    name + '.uproject': json.dumps(dict(
        FileVersion=3, EngineAssociation='', Category='Compatibility tests',
        Description='Minimal iOS game fixture for original UBT and Xcode on Linux/Darling',
        Modules=[dict(Name=name, Type='Runtime', LoadingPhase='Default')],
        TargetPlatforms=['IOS']), indent=2) + '\n',
    'Source/' + name + '.Target.cs':
        'using UnrealBuildTool;\npublic class ' + name + 'Target : TargetRules { public ' + name +
        'Target(TargetInfo Target) : base(Target) { Type = TargetType.Game; DefaultBuildSettings = BuildSettingsVersion.Latest; IncludeOrderVersion = EngineIncludeOrderVersion.Latest; ExtraModuleNames.Add("' + name + '"); } }\n',
    'Source/' + name + 'Editor.Target.cs':
        'using UnrealBuildTool;\npublic class ' + name + 'EditorTarget : TargetRules { public ' + name +
        'EditorTarget(TargetInfo Target) : base(Target) { Type = TargetType.Editor; DefaultBuildSettings = BuildSettingsVersion.Latest; IncludeOrderVersion = EngineIncludeOrderVersion.Latest; ExtraModuleNames.Add("' + name + '"); } }\n',
    'Source/' + name + '/' + name + '.Build.cs':
        'using UnrealBuildTool;\npublic class ' + name + ' : ModuleRules { public ' + name +
        '(ReadOnlyTargetRules Target) : base(Target) { PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs; PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" }); } }\n',
    'Source/' + name + '/' + name + '.cpp':
        '#include "Modules/ModuleManager.h"\nIMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, ' + name + ', "' + name + '");\n',
    'Config/DefaultGame.ini':
        '[/Script/EngineSettings.GeneralProjectSettings]\nProjectID=' + uuid.uuid4().hex.upper() + '\nProjectName=' + name + '\n',
    'Config/DefaultEngine.ini':
        '[/Script/IOSRuntimeSettings.IOSRuntimeSettings]\nBundleIdentifier=com.kxn.linuxcodeuesmoke\n',
}
for relative, data in files.items():
    (folder / relative).write_text(data)
record = dict(name=name, directory=str(folder.relative_to(root)),
              ordinary_UE_project_fixture=True, fixture_authored_by_linuxcode=True,
              engine_source_modified=False,
              project_generation_verified=False,
              files={relative: hashlib.sha256((folder / relative).read_bytes()).hexdigest()
                     for relative in files},
              preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(folder / 'prepared.json').write_text(json.dumps(record, indent=2) + '\n')
print('PREPARED', folder.relative_to(root))
