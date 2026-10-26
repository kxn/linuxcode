import Foundation
import Dispatch
import Darwin
final class Completion: @unchecked Sendable {
 let lock=NSLock()
 var labels=Set<String>()
 func record(_ label:String) {
  lock.lock();defer { lock.unlock() }
  precondition(labels.insert(label).inserted)
  print("STARTUP_JOB \(label)");fflush(stdout)
  if labels.count==3 { print("SWIFT_DISPATCH_MAIN_ACTOR_AND_GLOBAL_STARTUP_OK");fflush(stdout);exit(0) }
 }
}
let done=Completion()
DispatchQueue.main.async { done.record("dispatch-main") }
Task { @MainActor in
 dispatchPrecondition(condition:.onQueue(.main))
 await Task.yield()
 done.record("main-actor")
}
Task.detached {
 let sum=await withTaskGroup(of:Int.self) { group in
  for i in 1...64 {group.addTask { await Task.yield();return i }}
  var total=0;for await i in group {total+=i};return total
 }
 precondition(sum==2080);done.record("global-64-tasks")
}
DispatchQueue.global().asyncAfter(deadline:.now()+15) { fputs("STARTUP_TIMEOUT\n",stderr);exit(1) }
dispatchMain()
