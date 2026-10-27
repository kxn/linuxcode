#!/usr/bin/env python3
"""Prepare a fresh native Linux Unity project, preserving existing Xcode evidence."""
from pathlib import Path
import hashlib,json,shutil,tempfile
r=Path(__file__).resolve().parent.parent;source=r/'fixtures/UnityExportSmoke';folder=Path(tempfile.mkdtemp(prefix='unity-editor-e2e-',dir=r/'runtime'));project=folder/'project';shutil.copytree(source,project)
(project/'Packages').mkdir();(project/'Packages/manifest.json').write_text(json.dumps({'dependencies':{}},indent=2)+'\n')
(project/'ProjectSettings').mkdir();(project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.27f1\nm_EditorVersionWithRevision: 6000.3.27f1 (672d562a42a7)\n')
editor=r/'runtime/unity-editor-linux-6000.3.27f1/Editor/Unity';output=folder/'ios';command=[str(editor),'-batchmode','-nographics','-quit','-projectPath',str(project),'-buildTarget','iOS','-executeMethod','Linuxcode.CI.IOSExport.Run','-logFile',str(folder/'Unity-export.log')]
record=dict(project=str(project.relative_to(r)),export=str(output.relative_to(r)),editor=str(editor.relative_to(r)),editor_version='6000.3.27f1',command=command,environment={'LINUXCODE_UNITY_EXPORT_PATH':str(output)},source_files={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()},Unity_export_verified=False,CocoaPods_verified=False,original_xcodebuild_verified=False,provisioned_device_install_verified=False)
(folder/'prepared.json').write_text(json.dumps(record,indent=2)+'\n');(folder/'command.json').write_text(json.dumps(command,indent=2)+'\n');print(folder.relative_to(r))
