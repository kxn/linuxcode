# x86_64 普通 Mach 消息寄存器 ABI

新增配套 Darling server / libsystem_kernel 的 mach_msg2_internal 普通消息路径。寄存器消息头与 descriptor count 为权威输入，只从用户内存复制消息体；因此支持只读发送缓冲区和与内存中不同的消息头。最终消息进入真实的 ipc_kmsg/port 队列、内核 MIG 和接收路径，保留端口权利、错误和超时；既有 mach_msg 通过无捕获参数走原路径。

115 项原生检查通过：16 组新发送/旧接收、只读数据、真实端口描述符、捕获的计数覆盖、向内核 host_info 的组合请求/回复并与旧调用比较、新接收、超时、坏地址、大小、目的端口和选项。旧配置缺少接口返回 12，错误检查计数返回 15。新的后端再次完成旧会话测试的 537 项检查。保留此前 1,365 个导出，仅增加 mach_msg2_internal；私有 RPC helper 隐藏。旧 87 个 RPC 签名和编号顺序不变，新接口编号 88。wire-call-numbers-v2 使用从已发布旧提交精确恢复的不可变基线，v1 的工作树路径后来更新，已补历史映射。

源码参考锁定 Apple XNU f6217f891ac0bb64f3d375211650a4c1ff8ca1ea。源码已保存在 [darlingserver](https://github.com/kxn/darlingserver/commit/73042f0ac9679acde643693527fe28a199be984d) 和 [darling-xnu](https://github.com/kxn/darling-xnu/commit/218940df15180cb655887bb8c8d434a8cc5bb954)，沿用既有分支和 Comman Kang 提交身份。

## 明确的兼容范围

首版仅实现普通消息。向量、auxiliary、DriverKit 和不支持的低位选项在消耗消息权利之前明确返回无效选项。完整新内核 hardened policy 和 guard exception 投递尚未移植；返回错误的对照测试不等于这些语义已实现。中断重试遵循苹果用户态逻辑，尚无原生信号覆盖。

另补 host_get_io_main 的 SDK 新名称，转给同一个旧 Mach 205 接口，70 项兼容检查通过。当前新旧名称均返回成功和空 I/O 主端口，后端服务可用性为 false；未将此宣称为真实 I/O 服务实现。早期对非空端口的失败假设亦保留。

原版工具已经越过缺失的两个 Mach 导出，随后 actool/ibtool 均 SIGSEGV 139。完整工程、最新定位与产品状态见 reference，不能把接口检查当作资源编译、最终 Unity/UE App 或签名成功。默认安装候选未提升。

## 复现

需要完整 Linux x86_64 开发工作区与用户自行提供的 Xcode、SDK 和匹配系统缓存。stage 摘要只有本地原报告路径与 SHA，不可直接拿来当完整 stage；重新构建必须重新计算报告 SHA。payload 相对工作区；reference 的 UTF-8 JSON text 和 original-file-map 可恢复逐字节原始源码/日志，含尾部空格的源码也通过这种方式保存。source history 应合并，不能覆盖其他修订。不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。

```bash
python3 scripts/build-shared-remap-server.py
python3 scripts/build-libsystem-kernel-source.py --output-dir runtime/mach-msg2-kernel-v1 --variant-base runtime/audit-session-runtime-5/darling-root --report artifacts/mach-msg2-kernel-v1-build.json
python3 scripts/stage-audit-session-runtime.py --parent-stage artifacts/private-procfs-auditsession5-stage.json --server-build runtime/shared-remap-server-96t446yt/stage.json --kernel-build artifacts/mach-msg2-kernel-v1-build.json --tag 6
python3 scripts/probe-mach-msg2-scalar.py --configuration config/direct-resource-tool-environment-v122.json --baseline-stage artifacts/private-procfs-auditsession5-stage.json --stage artifacts/private-procfs-auditsession6-stage.json
```

使用实际新生成的 server 报告路径。原生运行及内核库原生链接必须串行；旧报告/候选保持不变。
