# Server-wide original Mach activity IDs

Original IBAgent reached main and UIKit resource initialization, then libdispatch trapped because mach_generate_activity_id_impl returned KERN_FAILURE. Darlingserver already compiled Apple’s original allocator in ipc_voucher.c. The new source initializes that global allocator once and appends an RPC route from the existing client trap. The original atomic allocation algorithm,count limit and copyout behavior remain intact.

A native test requests770 ranges from8 threads and2 independently executed children and verifies all6531 reserved IDs are nonzero and nonoverlapping. Counts0,-1 and17 are rejected and an invalid client output pointer produces a real copyout failure. IDs share the current Darling server lifetime; independent servers/restarts are separate namespaces.

Original IBAgent advances again: its first8 observed message-vector sends/receives succeed. The next precise unsupported call sends272 primary bytes and40 auxiliary bytes with options0x500100031. The previous empty-auxiliary implementation rejects it explicitly. That sidecar transport is the next module. Actual resource-tool status remains255 and no compiled Storyboard/App is claimed. Source,text and hashes only; default installer not promoted.
