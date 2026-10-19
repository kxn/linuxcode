using System;
using Mono.Cecil;

public static class InspectManagedMethods
{
    static int Count;
    static void Inspect(TypeDefinition type, string typeFilter, string methodFilter)
    {
        if (type.FullName.IndexOf(typeFilter, StringComparison.Ordinal) >= 0)
            foreach (MethodDefinition method in type.Methods)
                if (method.Name.IndexOf(methodFilter, StringComparison.Ordinal) >= 0 && method.HasBody)
                {
                    Count++;
                    Console.WriteLine("METHOD {0}", method.FullName);
                    foreach (var instruction in method.Body.Instructions)
                        Console.WriteLine("{0:x4}: {1} {2}", instruction.Offset, instruction.OpCode, instruction.Operand);
                }
        foreach (TypeDefinition nested in type.NestedTypes) Inspect(nested, typeFilter, methodFilter);
    }

    public static int Main(string[] args)
    {
        if (args.Length != 3) return 2;
        // Read metadata and IL only; never load or invoke the inspected assembly.
        using (AssemblyDefinition assembly = AssemblyDefinition.ReadAssembly(args[0]))
            foreach (TypeDefinition type in assembly.MainModule.Types) Inspect(type, args[1], args[2]);
        return Count == 0 ? 1 : 0;
    }
}
