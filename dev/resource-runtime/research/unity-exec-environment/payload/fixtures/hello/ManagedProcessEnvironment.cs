using System;
using System.Collections;
using System.Diagnostics;

public static class ManagedProcessEnvironment
{
    public static int Main(string[] args)
    {
        string path = Environment.GetEnvironmentVariable("PATH");
        IDictionary environment = Environment.GetEnvironmentVariables();
        Console.WriteLine("MANAGED_ENVIRONMENT PATH={0} count={1} dictionary_PATH={2}", path, environment.Count, environment["PATH"]);
        if (String.IsNullOrEmpty(path) || path != (string)environment["PATH"]) return 1;
        ProcessStartInfo start = new ProcessStartInfo("uname", "-s");
        start.UseShellExecute = false;
        start.RedirectStandardOutput = true;
        start.RedirectStandardError = true;
        Console.WriteLine("MANAGED_CHILD_ENVIRONMENT count={0} PATH={1}", start.EnvironmentVariables.Count, start.EnvironmentVariables["PATH"]);
        using (Process child = Process.Start(start))
        {
            string output = child.StandardOutput.ReadToEnd();
            string error = child.StandardError.ReadToEnd();
            child.WaitForExit();
            Console.WriteLine("MANAGED_CHILD_RESULT status={0} output={1} error={2}", child.ExitCode, output.Trim(), error.Trim());
            if (child.ExitCode != 0 || output != "Darwin\n" || error != "") return 2;
        }
        Console.WriteLine("ORIGINAL_CORECLR_MANAGED_ENVIRONMENT_AND_PATH_CHILD_OK");
        return 0;
    }
}
