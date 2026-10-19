using System;
using System.IO;
using System.Reflection;

public static class ManagedBeeHostPlatform
{
    static object Property(Type type, string name)
    {
        return type.GetProperty(name, BindingFlags.Static | BindingFlags.Public).GetValue(null, null);
    }

    public static int Main(string[] args)
    {
        string deploy = Environment.GetEnvironmentVariable("LINUXCODE_BEE_DEPLOY");
        if (String.IsNullOrEmpty(deploy)) return 2;
        bool guestProc = Directory.Exists("/proc");
        bool internalProc = Directory.Exists("/private/var/db/darling/proc");
        bool hostProc = Directory.Exists("/Volumes/SystemRoot/proc");
        Console.WriteLine("MANAGED_PROCFS guest={0} internal={1} host={2}", guestProc, internalProc, hostProc);
        Assembly original = Assembly.LoadFrom(Path.Combine(deploy, "Bee.Tools.dll"));
        Type platform = original.GetType("Bee.Tools.HostPlatform", true);
        bool linux = (bool)Property(platform, "IsLinux");
        bool mac = (bool)Property(platform, "IsOSX");
        bool windows = (bool)Property(platform, "IsWindows");
        string architecture = Property(platform, "HostArchitecture").ToString();
        Console.WriteLine("ORIGINAL_BEE_HOST_PLATFORM assembly={0} linux={1} mac={2} windows={3} architecture={4}",
            original.Location, linux, mac, windows, architecture);
        if (guestProc || !internalProc || !hostProc || linux || !mac || windows || architecture != "X64") return 1;
        Console.WriteLine("ORIGINAL_BEE_MACOS_HOST_PLATFORM_AND_X64_ARCHITECTURE_OK");
        return 0;
    }
}
