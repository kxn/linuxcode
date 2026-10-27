# 修复归档进程启动时继承的队列锁

原版 Unity archive 的首次运行在 `llbuild::basic::spawnProcess` 子进程中停住。对实际映射文件做 SHA-256 比对后，调用栈确定为 stage84 的 `sys_posix_spawn → sys_dup2 → kqueue_dup → pthread_mutex`；子进程只有一条线程，继承的锁无法由已经消失的父进程线程释放。最初仅按 file offset 注释的符号不准确，判断使用的是保留 nlist、正确虚拟地址和实际映射库的后续记录。

直接事件 workqueue 模式在 libsystem_kernel 中内嵌了自己的 libkqueue。原来的 libSystem fork 回调只重置其自身那一份。修复在 libSystem 完成 pthread/malloc 的 child 回调之后、任何 posix_spawn 文件动作之前，再重置内核库所属的 backend。仅对 `DARLING_DIRECT_KEVENT_WORKQUEUE` 生效，保留原回调与 spawn 参数；没有修改原版 Xcode 二进制。

源码已推送现有 [darling-xnu 分支提交 0d24e08](https://github.com/kxn/darling-xnu/commit/0d24e0824a66dd795517b11b6f4457c5f24afef1)。本次完整 kernel 只重编译一个源文件，复用其余 906 个对象，保留原有 1,434 项公开导出。stage85 克隆 stage84，仅更换这份内核库。

## 定向验证

同一个原生测试程序让另一条父线程持有实际 backend 的队列锁，然后 `posix_spawn` 自身并执行 stdout 的 dup2 文件动作。测试从精确内核文件的 nlist 求私有锁与公开函数的偏移，不更改程序指令。

- stage84：在 spawn 中卡住，8 秒的测试 alarm 触发，状态 142。
- stage85：子进程成功 exec，stdout 内容正确，状态 0；父进程自己的队列仍可正常关闭，没有被 child 清理。

```bash
python3 scripts/probe-kqueue-spawn-fork-reset.py \
  --stage artifacts/private-procfs-auditsession84-stage.json --expect-blocked
python3 scripts/probe-kqueue-spawn-fork-reset.py \
  --stage artifacts/private-procfs-auditsession85-stage.json
```

证据在 `artifacts/kqueue-spawn-fork-reset-milestone-v1.json` 及其引用的两份测试报告、源码构建和调用栈记录。第一次归档在确认死锁后主动结束，日志和编译缓存保留；归档重跑使用另一个缓存副本。

这里证明的是定位到的 spawn 问题和定向回归；完整 archive 重跑尚待结果，不代表 archive/export 或所有 fork/kqueue 行为已经验证。`config/native-certificate-candidate-v5.json` 是 stage85 研究配置，尚无可供 adopt 的完整成功回执；已发布的可复用入口仍采用验证过的 v4。
