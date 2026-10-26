# 真实 Mach eventlink 创建、等待与线程交接

继续在纯 Linux x86_64 / Darling 中运行原版 Xcode 资源工具，工程和 CI 参数保持。原版 iOS libdispatch 因 mach_eventlink_associate 缺失而不能加载；没有最终 Unity App 或 Storyboard 产物，默认安装候选未提升。

Darling 服务已经编译了 XNU 的 ipc_eventlink 实现及 MIG 服务，但客户端未生成四个 MIG 入口，三种信号/等待的64位 BSD 系统调用也没有接线。这次同时补齐 create/destroy/associate/disassociate，及 signal/wait/signal_wait；新 RPC 将56位计数与内核错误的完整64位值放在独立回复字段中，避免被传输层32位状态码截断。实际对象、端口、计数、等待队列、定时器及唤醒均来自既有 XNU 后端，没有预设成功返回。

首次原生测试触发分配区空指针，定位到 XNU 的 ZONE_DECLARE 依赖自动启动注册，而 Darling 使用显式初始化；现已加入 eventlink 对象分配区初始化。第二次测试在 associate-on-wait 的合法空线程参数处崩溃：MIG 无条件销毁该引用，Darling 的 thread_deallocate 却未处理空值。现已补空线程释放语义。两份崩溃的源码栈与失败记录保留，本地 core 不包含在附件中。

通过的原生测试包含：错误时保留超过32位的计数、无效端口/创建参数、两个真实端口、未关联拒绝、明确线程与首次等待关联、重复关联拒绝、预先发出两次信号、非阻塞超时、实际时间流逝的阻塞超时、两个真实线程的信号等待和交接、解除关联、销毁以及销毁后错误。成功标记为 MACH_EVENTLINK_MIG_64BIT_COUNT_REAL_WAIT_SIGNAL_AND_LIFECYCLE_NATIVE_OK，报告为 runtime/mach-eventlink-vhwb23m7/result.json。

完整内核库仍从上游源清单和 MIG 定义构建，新模块使翻译单元从879增加到881。整合脚本检查清单与实际数量一致并保留最低完整性要求，不再把879写死。后两次服务端修复复用了未变化的内核构建，没有重新编译881个单元，也未重跑旧 Swift、Unity 编译和签名测试。

原版 Storyboard 以新后端重跑后已越过 eventlink，下一处为原版 iOS libdispatch 所需的 work_interval_instance_set_complexity。最新记录是 runtime/original-storyboard-h0v8iy3v/result.json，仍以255退出。资源编译、模拟器完整功能及最终 App 均未宣称完成。

源码已发布到 kxn/darlingserver 与 kxn/darling-xnu 的原有 linuxcode/xcode-x86_64 分支，提交身份为 Comman Kang <kangxn@gmail.com>。开发脚本需要此前研究基线、原版 Xcode/SDK/运行时及已经生成的 MIG 头；测试只选择新增 eventlink 私有头，避免用旧生成头覆盖现代 SDK 的其他 Mach 接口。附件仅含 UTF-8 源码、日志、报告及摘要，没有 Apple/Unity 二进制、SDK、XIP、core、CMS 输入或私钥。
