# 原版 Xcode 与游戏引擎兼容性推进计划

更新：2026-10-28。目标是在 Linux/Darling 中执行 Intel macOS 原版工具，保留工程和 CI 的 xcodebuild 命令。macOS Unity Editor 的导出也是目标的一部分；Linux Editor 导出成功不能代替它。

## 当前事实

| 流程 | 已确认 | 尚未完成 |
| --- | --- | --- |
| Unity Linux Editor → iOS 工程 → CocoaPods → 原版 Xcode | stage101 的全新 Debug App、Release xcarchive 通过；stage108 隔离增量构建、实际签名及独立 CMS/内容检查也通过 | 这次回归复用 IL2CPP 缓存；没有 Apple 设备信任或 App Store 交付结论 |
| 原版 macOS UE 工具 → iOS workspace → CocoaPods → 原版 Xcode | UBT、UHT、实际 Pod 静态库和全部游戏 C++ 编译已执行；stage108 v10 已进入最终链接 | 最终链接、完整 App、签名 |
| 原版 macOS Unity Editor → iOS 工程 | 已安装同版本原始输入；Intel 6000.3.27f1 在 Darling 中原生 `-version` 通过 | 真实 batchmode 初始化、原版授权客户端及实际导出 |
| 独立安装及开发者工程 | 公共源码可在新目录重建 darlingserver；有 XIP/Recovery 输入处理及源码包 | 从干净 Linux 输入装配完整已验证运行环境，仍未自动化完成 |

UE 当前已使用 stage110 越过原版 MSBuild/UBT 的两处信号交接死锁，进入 UBA → Clang → ld 的真实最终链接。新的 ld 段对齐断言可用四行独立 C 源同时在直接链接与原版 UBA 链接中复现：当前 legacy libm 将 `log2(16384)` 算成略小于 14，ld 截断后得到 13。Darling 源码已经包含完整 Apple `log.S`，但 CMake 禁用了它并选择了近似实现；已修正完整数学库的源码选择，没有修改 UE 参数或另写数学特判。2098 个可表示二次幂的对照中，旧实现 364 个不精确，已有原 Apple 库全部正确。完整 126 单元 libm 候选保留所有旧导出；修复后的数值检查和原版 direct/UBA 最小链接通过。原始 UBT 四个后续构建动作已全部成功，最终 arm64 可执行文件包含真实 CocoaPods `_local_add` 符号。完整原 Xcode App 打包和签名正在执行；尚未验证设备运行。

macOS Unity 复用了既有资源工具的完整框架闭包，补入原始 GameController 及其依赖；加载器恢复既有大小写查询，解决包内 `libPcre2` 与加载名称大小写不同的问题。ARC claim 直接移植 Apple objc4-951.1 的 Intel 所有权语义，21 项真实运行检查通过；`macho_source_version` 复用 Apple dyld-1378 及既有组件，20 项真实 Mach-O 检查通过。原版 Editor `-version` 返回正确版本且退出 0；这不代表初始化、授权或导出已通过。源码 fork 和精确证据摘要见[本轮进展](../validation/runtime-source-reuse-progress-2026-10-28.json)。

2026-10-28 对官方远端 HEAD 的一次性核对表明，本地基础提交与上游一致：Darling 为 60ba801decee7a00782f74f6be4c8ffb013f79ff，darlingserver 为 89751e64bc6c2082f7725061824ee0e33395b0de。基础版本与后来叠加的修改、实际装载的二进制是不同概念。已有的上游复用审查只覆盖少数接口，不代表所有历史补丁都已审查。

## 本次审查发现的收敛工作

[提供库审查](../validation/compatibility-provider-review-2026-10-28.json) 记录了源文件行号、摘要、现有进程映射及 LLVM 符号检查。确认的四类问题如下；没有把它们都归因于当前 UE 链接故障。

| 发现 | 改进方式与边界 |
| --- | --- |
| 至少两处分别嵌入 libkqueue；进一步核对发现上游 libc 也包含第三份 | 上游原有 libSystem/libc 双嵌入；direct-kernel 构建又增加一份。先核对真实绑定和调用，不能用符号数量推断三份状态都在活跃工作 |
| 完整 31 单元 CoreTLS 后端和匹配 crypto 已有，但当前 UE 选择链未接入 | 需要 TLS 的工作负载先复用现有 selector，并确认实际映射；不因链接错误而无关地替换 TLS |
| Security 远程签名适配入口返回未实现，较新上游已有实际源码 | 明确能力范围；按实际需求集成完整依赖和 ABI。保留已通过的真实本地签名后端，不增加假成功接口 |
| 活跃运行选择依赖历史 probe 日志和链接对象 | 将源码/构建审计与运行时提供库清单分开；启动仍验证实际二进制身份、依赖及使用范围，历史记录保留 |

三份原有二进制的 `kqueue_impl`、`kevent_impl` 和 `kqueue_atfork` 均为强导出；各自的 `kq_mtx`、once 状态和 `kqmap` 为非外部或私有符号。libc 的 weak-bind 流中有 strong-definition 标记，用于覆盖弱使用者，不会把这些私有状态合并。上游 kernel 原本提供弱 fallback，实际使用哪个强后端仍须结合绑定与真实调用判断。

当前 v2 是独立可选的 **libSystem → kernel 路由收敛** 候选：保留 direct kernel 和上游 libc，省去 libSystem 内的队列对象，通过现有 kernel 导出与 reexport 依赖复用实现。host 已完成三个源对象的重链，确认十个队列导出转到 kernel，初始化器的 `kqueue_atfork` 导入也指向 kernel。五项 native 小测试通过：baseline/candidate 的真实 `dlsym`/`dladdr` 身份、持锁 fork、持锁 spawn、receipt/error/readiness；候选的 default/libSystem 查询均落到 kernel，libc 仍独立。它没有实现全进程物理去重，也没有改变默认组合或 immutable stage108。当前仅验证 normal 模板的队列路径，resource-tools 另有 23 个 helper reexport 及依赖尚未纳入候选；不能据此用于完整 UE 流程。原版 Apple libSystem 仍需要 direct backend，不能全局删除。

另一条可选路线是为 Darling libSystem 保留上游 kernel 弱 fallback 与 libSystem/libc 强实现的既有组合，将原版 Apple libSystem 的 direct-kernel 组合单独保留。这能避免再加入第三个强后端，但需要匹配的 kernel 构建和 close、dup、fork、kevent_qos 绑定验证；目前没有构建或采纳这条路线，也不计划为物理删副本重编整个 libc。两条路线都应先复用现有导出与修复机制。

已验证的 XNU 等待交接、S2C 回复和 exec/checkin 修复本身复用了既有队列、锁与 monitor，不等于需要另写调度器。

## 修复归属与复用顺序

每个正在阻塞实际工作负载的问题，应记录实际进程、装载的提供库、调用失败点及源文件，再按下表处理。框架文件存在、导出符号存在、真正实现可用分别检查。

| 缺口类别 | 优先处理位置 | 完成标准 |
| --- | --- | --- |
| 上游已有实现但未构建、未导出或未加载 | CMake、安装目录、依赖与运行时库选择 | 实际进程调用上游实现；移除重复提供者需先验证该调用链 |
| 已有实现的 ABI、版本或行为错误 | 对应 Darling 组件的原接口 | 最小源码差异；故障用例修复；受影响的引擎流程通过 |
| Mach、线程、进程、共享内存与文件语义 | darlingserver / libsystem_kernel / mldr | 复用现有协议、队列与锁，修正共有语义；不在各工具外围重复补丁 |
| 本机输入遗漏或环境装配错误 | 独立 linuxcode 安装/开发者工程 | 补齐原始输入或统一路径；不修改引擎来掩盖环境问题 |
| 确认没有可复用实现的接口 | 所属组件，明确支持范围 | 有实际消费者和可验证行为；不能仅以返回成功作为实现 |

历史 research 附件保留为证据，不再作为用户选择当前运行时的目录。后续装配应由一个明确的候选配置选定每个组件的版本、构建输入和安装位置。已被替代的候选不进入新的默认运行闭包。整合工程保持独立；Darling 的行为修复留在对应 fork 源码中。

## 执行顺序

1. **UE 链接。** 修正 libm 构建配置以选用源码中已有的完整 Apple log2 算法，验证整库导出、特殊值和原版直接/UBA 最小链接，再执行复用现有对象的真实 UBT 链接。通过后回到原 workspace 的完整 Xcode 构建与签名。
2. **UE App 与签名。** 原版 xcodebuild 完成 App，验证 iPhoneOS arm64、真实 Pod 调用已进入最终可执行文件，再由原版 codesign 签名 App 与嵌入框架并独立检查。测试证书与 Apple 开发者签名范围明确区分。
3. **底层修复跨引擎验证。** 影响进程、线程、VM 或加载器的修改，通过隔离的 Unity 工程/DerivedData 副本验证；不得覆盖 stage101 已验证产物。只影响某个工具配置的修改不触发全矩阵重跑。
4. **macOS Unity 原版导出。** 并行准备 Intel Editor 和同版本 iOS 模块；按可执行文件加载、版本查询、batchmode/nographics 空项目、原版授权客户端、iOS 导出逐级验证。以实际导出的 Xcode 工程接回 CocoaPods/原版 xcodebuild，最终形成全程 Linux、执行 macOS 原版 Editor 的端到端记录。无显示不等于没有 AppKit/图形库依赖，按真实调用审查。
5. **收敛与交付。** 每个通过的行为修复连同源码归属进入 fork；独立 linuxcode 工程记录同一候选的构建与装配依赖。用新工作区验证完整安装和开发者重建后才称为可复现整包。源码构建成功、单个符号补齐或检查脚本通过都不是完整流程里程碑。

## 缩短反馈周期

- 源码审查、输入下载、Linux 上的源码构建和文档整合并行；共享前缀上的 Darling 会话继续使用既有互斥锁。
- 同一失败先用最短真实调用链复现，避免每个猜测都重跑完整 Xcode/UBT。源码未变化的旧矩阵不重复运行。
- 保留编译缓存和已完成的 UBT actions；同时记录它们的来源，不把增量通过写成全新构建。
- 发布源码改动以可追踪的行为修复或完整流程进展为单位。避免每条调试日志都派生新的公共附件、入口脚本和候选版本。
- 运行配置校验当前实际输入；历史负对照和证据恢复用于审查及复现。已有摘要缓存继续复用，不以删除校验来掩盖选错二进制。

当前公开源码重建入口见 [public-server-build.md](public-server-build.md)，历史补丁定位入口见 [research-sources.md](research-sources.md)。这些入口不会自动证明完整候选环境已经从零装配成功。
