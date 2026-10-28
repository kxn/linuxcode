#!/usr/bin/env python3
"""Prepare a real LocalMath Pod for our ordinary UE fixture, without engine edits.

--check is read-only. Actual preparation requires a nonblocking exclusive native
session lock, and archives existing source inputs before changing the fixture.
It does not run Darling, CocoaPods, Xcode, UBT, or project generation.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_project(project, target, xml):
    matches = []

    def walk(node, base):
        for child in node:
            if child.tag not in ('Group', 'FileRef'):
                continue
            kind, separator, value = child.attrib.get('location', '').partition(':')
            check(separator and kind in ('group', 'container', 'absolute', 'self'), 'Unsupported workspace location')
            resolved = ((base if kind == 'group' else project) / value).resolve()
            if child.tag == 'Group':
                walk(child, resolved)
            elif resolved.name == target + ' (IOS).xcodeproj':
                matches.append(resolved)

    walk(xml.getroot(), project)
    check(len(matches) == 1, 'Original workspace must identify exactly one UE game project')
    check(matches[0].is_relative_to(project), 'Workspace game project escapes fixture root')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--target', default='LinuxcodeUESmoke')
    parser.add_argument('--check', action='store_true', help='Read-only fixture/project preflight')
    args = parser.parse_args()
    check(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', args.target), 'Invalid UE target name')
    project = (root / args.project).resolve()
    check(project.is_relative_to(root / 'runtime') and project.is_dir(), 'Project must exist inside runtime/')
    check((project / (args.target + '.uproject')).is_file(), 'UE project descriptor missing')
    module = project / 'Source' / args.target
    build_cs = module / (args.target + '.Build.cs')
    game_cpp = module / (args.target + '.cpp')
    workspace = project / (args.target + ' (IOS).xcworkspace/contents.xcworkspacedata')
    check(workspace.is_file(), 'Run original UE iOS workspace generation first')
    workspace_xml = ET.parse(workspace)
    xcode_project = workspace_project(project, args.target, workspace_xml)
    pbx = xcode_project / 'project.pbxproj'
    template = root / 'fixtures/UECocoaPodsSmoke/Podfile.template'
    inspector = root / 'scripts/inspect-unreal-pods-project.rb'
    descriptor = json.loads((project / (args.target + '.uproject')).read_text())
    prepared = json.loads((project / 'prepared.json').read_text())
    # Historical metadata called our authored fixture an "original UE project".
    # Accept it only after checking the actual fixture identity and empty module.
    expected_cpp = ('#include "Modules/ModuleManager.h"\n'
                    f'IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, {args.target}, "{args.target}");\n')
    check(game_cpp.read_text() == expected_cpp, 'Only our unchanged ordinary empty-game fixture is supported')
    check(prepared.get('fixture_authored_by_linuxcode') or
          (prepared.get('original_UE_project') and prepared.get('name') == args.target and
           descriptor.get('Description') == 'Minimal iOS game fixture for original UBT and Xcode on Linux/Darling'),
          'Fixture authorship is not established')
    check('PublicAdditionalLibraries' not in build_cs.read_text(), 'Fixture already contains external libraries')
    check(pbx.is_file() and workspace.is_file(), 'Run original UE iOS project generation first')
    references = [node.attrib['location'] for node in workspace_xml.iter('FileRef')]
    check(len(references) >= 4, 'Expected original UE workspace with its engine and game references')
    for relative in ('Podfile', 'Podfile.lock', 'Pods', 'Dependencies/LocalMath', 'unreal-pods-preparation.json'):
        check(not (project / relative).exists(), 'Already prepared or installed: ' + relative)
    if args.check:
        print(json.dumps(dict(preflight_verified=True, project=str(project.relative_to(root)),
                              ordinary_UE_project_fixture=True, fixture_authored_by_linuxcode=True,
                              ue_xcode_project=str(xcode_project.relative_to(project)),
                              workspace_original_references=references, project_modified=False,
                              native_process_started=False), indent=2))
        return

    initial_inputs = {path: sha(path) for path in
                      (build_cs, game_cpp, pbx, workspace, project / 'prepared.json')}
    with (root / 'runtime/session.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Native session is busy; preparation did not modify the project') from None
        check(all(sha(path) == digest for path, digest in initial_inputs.items()),
              'Project changed during preflight; rerun preparation')
        # This is the repository's required source history, in addition to the
        # complete per-run snapshot below. The native lock remains held.
        originals_to_save = [build_cs, game_cpp, pbx, workspace, project / 'prepared.json',
                             *sorted((pbx.parent.parent / 'XcconfigsIOS').glob('*.xcconfig')),
                             *sorted((pbx.parent / 'xcshareddata/xcschemes').glob('*.xcscheme'))]
        subprocess.run([sys.executable, str(root / 'scripts/archive-source-inputs.py'),
                        *[str(path.relative_to(root)) for path in originals_to_save]], check=True, cwd=root)
        archive = Path(tempfile.mkdtemp(prefix='unreal-before-pods-', dir=root / 'runtime'))
        originals = {}
        for path in originals_to_save:
            saved = archive / 'inputs' / path.relative_to(project)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
            originals[str(path.relative_to(root))] = dict(sha256=sha(path), snapshot=str(saved.relative_to(root)))
        dependency = project / 'Dependencies/LocalMath'
        dependency.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root / 'fixtures/iOSCocoaPodsSmoke/LocalMath', dependency)
        podfile = template.read_text().replace('@TARGET@', args.target).replace(
            '@PROJECT@', str(xcode_project.relative_to(project))).replace(
            '@INSPECTOR@', '/Volumes/SystemRoot/workspace/scripts/inspect-unreal-pods-project.rb')
        check(not re.search(r'@[A-Z_]+@', podfile), 'Unexpanded Podfile template')
        (project / 'Podfile').write_text(podfile)
        build_cs.write_text('''using System;
using System.IO;
using UnrealBuildTool;

public class @TARGET@ : ModuleRules
{
    public @TARGET@(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        if (Target.Platform == UnrealTargetPlatform.IOS)
        {
            string library = Environment.GetEnvironmentVariable("LINUXCODE_POD_LIBRARY_DIR");
            if (String.IsNullOrEmpty(library))
                throw new BuildException("Build the CocoaPods workspace so the legacy target receives LINUXCODE_POD_LIBRARY_DIR.");
            PrivateIncludePaths.Add(Path.GetFullPath(Path.Combine(ModuleDirectory, "../../Dependencies/LocalMath")));
            PublicAdditionalLibraries.Add(Path.Combine(library, "libLocalMath.a"));
        }
    }
}
'''.replace('@TARGET@', args.target))
        game_cpp.write_text('''#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"
#if PLATFORM_IOS
extern "C" {
#include "LocalMath.h"
}
#endif

class F@TARGET@Module : public FDefaultGameModuleImpl
{
    virtual void StartupModule() override
    {
        FDefaultGameModuleImpl::StartupModule();
#if PLATFORM_IOS
        const int Sum = local_add(40, 2);
        UE_LOG(LogTemp, Display, TEXT("Linuxcode CocoaPods local_add: %d"), Sum);
#endif
    }
};
IMPLEMENT_PRIMARY_GAME_MODULE(F@TARGET@Module, @TARGET@, "@TARGET@");
'''.replace('@TARGET@', args.target))
        # Correct the old provenance label without claiming an Epic-authored game.
        prepared.pop('original_UE_project', None)
        prepared.update(ordinary_UE_project_fixture=True, fixture_authored_by_linuxcode=True,
                        cocoapods_prepared=True, engine_source_modified=False)
        (project / 'prepared.json').write_text(json.dumps(prepared, indent=2) + '\n')
        check(sha(pbx) == originals[str(pbx.relative_to(root))]['sha256'], 'UE-generated pbx changed during preparation')
        check(sha(workspace) == originals[str(workspace.relative_to(root))]['sha256'], 'UE-generated workspace changed during preparation')
        report = dict(project=str(project.relative_to(root)), target=args.target,
                      ue_xcode_project=str(xcode_project.relative_to(project)),
                      ordinary_UE_project_fixture=True, fixture_authored_by_linuxcode=True,
                      original_inputs=originals, original_workspace_references=references,
                      existing_LocalMath_fixture_reused=True,
                      project_format_writer='Original CocoaPods/xcodeproj post_integrate hook (not run yet)',
                      engine_source_modified=False, native_process_started=False,
                      pod_install_verified=False, pod_compile_verified=False, full_app_build_verified=False,
                      required_native_session_lock='runtime/session.lock',
                      install_entrypoint='scripts/install-unreal-ios-cocoapods.py',
                      files={str(path.relative_to(root)): sha(path) for path in
                             (Path(__file__), template, inspector, project / 'Podfile', build_cs, game_cpp,
                              project / 'prepared.json', *sorted(path for path in dependency.rglob('*') if path.is_file()))})
        (archive / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
        (project / 'unreal-pods-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PREPARED', archive / 'prepared.json')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
