using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Linuxcode.CI
{
    public static class IOSExport
    {
        public static void Run()
        {
            string output = Environment.GetEnvironmentVariable("LINUXCODE_UNITY_EXPORT_PATH");
            if (string.IsNullOrWhiteSpace(output)) throw new ArgumentException("LINUXCODE_UNITY_EXPORT_PATH is required");
            if (Directory.Exists(output) && Directory.EnumerateFileSystemEntries(output).Any())
                throw new InvalidOperationException("Export directory must be empty");
            if (!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.iOS, BuildTarget.iOS))
                throw new InvalidOperationException("Matching iOS Build Support module is required");

            PlayerSettings.companyName = "Linuxcode";
            PlayerSettings.productName = "LinuxcodeExportSmoke";
            PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.iOS, "org.linuxcode.exportsmoke");
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.iOS, ScriptingImplementation.IL2CPP);
            PlayerSettings.iOS.sdkVersion = iOSSdkVersion.DeviceSDK;
            PlayerSettings.iOS.targetOSVersionString = "15.0";
            PlayerSettings.iOS.appleEnableAutomaticSigning = false;
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            new GameObject("NativePodSmoke").AddComponent<NativePodSmoke>();
            Directory.CreateDirectory("Assets/Scenes");
            const string scenePath = "Assets/Scenes/Smoke.unity";
            if (!EditorSceneManager.SaveScene(scene, scenePath)) throw new InvalidOperationException("Cannot save smoke scene");
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(scenePath, true) };
            AssetDatabase.SaveAssets();

            BuildReport report = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
                scenes = new[] { scenePath }, locationPathName = output,
                target = BuildTarget.iOS, options = BuildOptions.None
            });
            if (report.summary.result != BuildResult.Succeeded)
                throw new InvalidOperationException("Unity iOS export failed: " + report.summary.result);
            string pod = Path.Combine(output, "Dependencies", "LinuxcodeSmoke");
            Directory.CreateDirectory(pod);
            File.Copy("NativePod/Smoke.m", Path.Combine(pod, "Smoke.m"));
            File.WriteAllText(Path.Combine(pod, "LinuxcodeSmoke.podspec"),
                "Pod::Spec.new do |s|\n  s.name = 'LinuxcodeSmoke'\n  s.version = '1.0.0'\n" +
                "  s.summary = 'End-to-end native linking smoke fixture'\n  s.homepage = 'https://github.com/kxn/linuxcode'\n" +
                "  s.license = { :type => 'MIT', :text => 'Permission is granted to use, copy, modify and distribute this fixture without warranty.' }\n  s.author = 'Linuxcode contributors'\n" +
                "  s.source = { :git => 'https://example.invalid/LinuxcodeSmoke.git', :tag => s.version.to_s }\n  s.platform = :ios, '15.0'\n  s.source_files = 'Smoke.m'\nend\n");
            File.WriteAllText(Path.Combine(output, "Podfile"),
                "platform :ios, '15.0'\nproject 'Unity-iPhone.xcodeproj'\n" +
                "target 'UnityFramework' do\n  pod 'LinuxcodeSmoke', :path => 'Dependencies/LinuxcodeSmoke'\nend\n");
            Debug.Log("LINUXCODE_UNITY_IOS_EXPORT_SUCCEEDED " + Application.unityVersion + " " + output);
        }
    }
}
