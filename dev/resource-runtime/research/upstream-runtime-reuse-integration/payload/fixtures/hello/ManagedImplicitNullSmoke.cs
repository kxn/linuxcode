using System;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;

// Self-contained JIT hardware-null-check coverage. It exercises CoreCLR's
// exception handling for this program without attaching to another process.
public static class ManagedImplicitNullSmoke
{
    sealed class Value { public int Number = 42; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static int ReadField(Value value) { return value.Number; }

    static void Exercise(string name, bool worker)
    {
        Console.WriteLine("IMPLICIT_NULL_BEGIN " + name);
        try
        {
            int ignored = worker ? Task.Run(() => ReadField(null)).GetAwaiter().GetResult() : ReadField(null);
            throw new Exception("expected null-reference exception; value=" + ignored);
        }
        catch (NullReferenceException error)
        {
            if (String.IsNullOrEmpty(error.StackTrace) || !error.StackTrace.Contains("ReadField"))
                throw new Exception("missing original JIT frame");
            Console.WriteLine("IMPLICIT_NULL_CAUGHT_WITH_JIT_STACK " + name);
        }
    }

    public static int Main()
    {
        Exercise("main-thread", false);
        Exercise("threadpool", true);
        Console.WriteLine("IMPLICIT_NULL_MACH_EXCEPTION_RESTORE_OK");
        return 0;
    }
}
