# Preserve an in-flight S2C transaction across interrupted reply waits

The original UE Xcode build on stage106 compiled the real LocalMath iOS Pod, then a later attempt lost its Darling server. A passive fault capture found a real `SIGABRT` at `Call::callFromMessage`: an S2C reply was already pending. The saved reply was a successful 40-byte `mmap` reply, while the incoming reply was the 28-byte `munmap` reply for the same live thread. Its interrupted-call state was active. Selected metadata is included; the process core, original Xcode logs and engine files remain private.

The existing `_s2cPerform` code serialized requests with a semaphore, but returned that semaphore immediately when a signal interrupted the reply wait. The request had already been sent and could still complete in the client. A later transaction could therefore receive the earlier reply or collide with it. The S2C protocol has no transaction identifiers.

The fix keeps the existing perform semaphore across interrupted reply waits while the target remains alive, then consumes the actual reply and follows the existing deferred-reply and interrupt-exit completion paths. It adds no replacement transport, scheduler or protocol. A dead target still takes the existing cancellation path; death/exec semaphore ownership remains a separate unresolved issue.

## Evidence and limits

The host regression compiles the actual `Thread::_s2cPerform`, `_mmap`, `_munmap`, reply handler, Message, Registry, ucontext and StackPool. Only transport and semaphore boundaries are controlled to deliver deterministic interruption windows. Five cases pass: normal transactions, interruption before/after reply arrival, repeated interruption, and cancellation before a request is sent. Exact archived stage106 Thread source is the negative control: three reply-interruption cases reproduce duplicate pending replies or reply-size mismatch, while both control cases pass.

The fixture exercises the existing deferred-reply flag branch with an active target call, but does not send a deferred message or execute the real signal-enter/exit handshake. It does not test actual XNU semaphore blocking, process death, exec generation changes, or a full server event loop. Non-thread objects are read-only copies from the current build; the negative control is not a historical whole-server binary.

A fresh stage107 server was built and staged separately. The original UE Xcode command is running against it with the already compiled Pod and existing failed DerivedData. There is no complete UE App or signing claim here. The frozen successful Unity stage101 candidate is unchanged. See the selected artifact for the source fork commit, exact source/build hashes and private-attempt references.
