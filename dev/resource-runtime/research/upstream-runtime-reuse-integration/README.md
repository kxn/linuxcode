# 复用现有完整运行时实现的整合源码检查点

本检查点保存同一轮兼容性收敛的构建、定位和回归源码。以 [当前推进计划](../../../compatibility-plan.md) 与 validation 中的实际结果为准；这些源码不是可直接叠加到任意旧 stage 的安装包。

本轮采用的原则是先核对实际加载的组件，再修正现有实现或接入完整上游代码：

- libm：Darling 已有 Apple `log.S`，通过构建配置替换近似版 `log2`，保留 `system_m_extra` 中的 log/log1p/log10、原同族接口和别名。整库构建器读取现有 CMake 源清单，避免单独新增一个数学 shim。SIMD 常量源是更早的工作树内容，整库快照保留其来源；本次 fork 提交只有 log2 接线。
- Objective-C：复用 Apple objc4-951.1 的 Intel ARC claim，适配旧 TLS helper，不用空返回替代所有权操作。
- Mach-O：在既有 cache-introspection 组件中复用 Apple dyld-1378 的真实 LC_SOURCE_VERSION 读取实现。
- dyld 文件名：启用现有 vchroot 大小写查找；Bootstrap 使用无 locale 依赖的 ASCII 比较，原有 Unicode 分解语义不扩大。
- 线程/RPC：保留已完成的 XNU 等待结果；接收并消费 S2C 请求后，到执行和回复结束前避免信号处理器重入 RPC，空闲等待仍可被中断。

macOS Unity 输入工具下载并检查同版本的官方 Intel Editor/iOS 模块，将原始包解到新的私有目录。启动检查分别记录版本、真实 batchmode 托管方法和 iOS 导出，不能互相代替。Apple/Epic/Unity 二进制、授权材料及原始运行日志不随本源码包发布。

行为修复优先发布到原有组件 fork，整合和开发工具留在 linuxcode 独立仓库。本目录的 payload 是工作区源码快照；使用前通过 `dev/research-sources.py inspect` 比较自己的版本，不能把全部文件直接覆盖到旧 checkout。构建器仍依赖显式锁定的 SDK、既有组件输入和运行配置，尚未实现完整环境冷装配。

已有源码和测试无变化时不重复运行旧矩阵。共享 Darling 会话使用既有锁；宿主构建、源码审查和输入准备可以并行。

后续审查修正了诊断用旧 profile 合并：`scope=all` 同时补入 caller 与 resource 覆盖路径，`resource-tools` 仅补 resource；六项 host 控制通过。完整 Xcode 使用新生成 profile，不受旧诊断合并缺口影响。原始 UBT/数学库证据保持原摘要；旧脚本由源码历史保留。完整 UE build、签名与独立校验已通过，见 reference 中新增的 signed-app 验证摘要。

本次增量仍为源码检查点，继续更新同一 payload、reference 和源码历史。v5/v6 改为整个 run 共用公开库路径：在首个 Mach-O、launchd 和后台服务启动前，物化完整 root/prefix 中的 loader、框架及库；upper/workdir 从同一父目录挂载，并有界等待首次服务就绪。统一模式禁止重新套用旧证书客户端/daemon 分组。新增源码还保存真实 AF_UNIX 地址长度修复、宿主 ASan/UBSan fixture、完整 kernel 增量构建入口，以及使用同一 Security 对象工厂的公共 identity store。

公开 bootstrap 摘要仅验证启动及被观测进程使用同一环境。前述完整 UE/签名结果属于此前的运行配置，不能代替 v5/v6 验收：统一环境下 identity 查询成功，但本次原 codesign 尝试在 120 秒超时；完整签名、原 Xcode 全构建和 macOS Unity 导出仍未完成。本目录不包含安装好的镜像、原 Apple 二进制、credentials、cores 或私有原始日志。

stage112/v9 的公共网络修复已发布到同一 XNU fork 分支：接口枚举复用 Linux libc，Darwin IFLIST/IFLIST2 使用真实 index、地址和统计，NET_RT_DUMP 输出真实 IPv4/IPv6 路由；accept/sendmsg/sendto 支持可选地址参数。61 项 socket 和 553 项 routing 宿主检查及旧源负控通过，4 个编译单元更新、903 个对象复用后，原版 ld 在整个公共 v6 环境中完成链接。相同 managed fixture 在 v9 的原版 CoreCLR 中枚举接口成功。

完整 macOS Unity v9 仍未通过：Editor 已连接 UPM，本轮没有观察到旧的 UPM 退出 11，但 package resolution 未完成；LicensingClient 曾启动 named-pipe server，随后出现原生 SIGSEGV/SIGABRT，未完成 managed 方法、许可验证或 iOS 导出。不能根据旧异常字符串消失推断授权流程已修复。

后续 v10/v11 源码候选接入了已有 raw Linux mounts 读取实现、从新 prefix 克隆排除历史 core，并按原优先级聚合共享库搜索。共享搜索层在宿主选择同一组 187 个 Intel dylib，将库目录从 71 个收敛到 2 个，并保留 framework fallback。v11 实际仍在 90 秒 bootstrap 等待后退出，未进入 codesign；这些源码准备和宿主等价检查不构成原生启动或性能验收。对应精选结果见 reference 中的 shared-network-runtime-source-checkpoint 摘要。

共享搜索工具另增加了未来输入的重名保护：NFD 分解和 ASCII 大小写折叠后发生冲突的库保留整组原目录顺序，framework 冲突组保留原 fallback，不生成快速别名；原有 `@loader_path` 处理保留。两目录小型宿主样例的 28 项检查覆盖旧工具误选后一个 provider、大小写/NFD 冲突及普通输入。当前 v11 名称集合没有这类冲突，此保护不改变既有 v11 索引或其启动失败结论。

v11 的确定启动阻断随后由真实 job 表定位：新建 LaunchDaemons/Agents 目录为 `0775`，原 launchctl 权限检查过滤整个服务目录，只剩 bootstrapper。v12 让新建目录继承对应 lower 目录权限，lower 不存在时用 `0755`，保留已有目录和原权限检查。实际 v12 已成功 bootstrap、进入原版 codesign，identity 查询返回 0、匹配 1 项；之后达到 120 秒限时，签名及 verify 仍未完成。相同共享搜索层参与这次成功启动，但没有单独验证性能提速；此前搜索和历史 core 的开销不能代替这次已确认的目录权限根因。精选结果见 shared-runtime-directory-mode 摘要。

公共 v13/stage113 接入服务端 x86 Mach debug-state get/set。该 server 是在逐字节一致的 stage112 基线重链接上更新 2 个编译单元的已验证增量，保持 `full_server_source_build=false`；kernel112、公共库、账号和目录权限保持原配置。117 项真实 Linux 子线程控制与生产 Mach marshaller 检查已通过；复用入口随包保存，没有为发布重复运行原控制。公共 Mach API 读写随后在真实 v13 中通过，外层/原生状态均为 0，含启动共 3.95 秒，无外部 GDB。

同 v13 的原版 Client 单次无 GDB 运行仍失败：named-pipe 已启动，本次未观察到旧的 debug-state MachExceptionInfo unsupported/SIGABRT，随后自然 SIGSEGV/139 退出。Mach API 已通过不表示 Client、许可验证或 Unity 导出已完成。本轮没有接入猜测性的 libunwind 替换。源码已发布到原有 darlingserver 分支，精选结果见 thread-debug-common-runtime 摘要。

v14–v16 继续使用整个 run 的同一镜像。v14 在首个 Mach-O 前预装四个完整原服务、五个原 plist 和两个完整依赖；v15 将宿主当前 resolver 配置快照同时提供给 Linux 与 Darwin，并可选转发现成 libtrace 的 stderr 开关。该开关默认不设置，不能用于选择不同程序的库。原服务实际均在 named sandbox profile 尚未实现处退出 1；codesign 仍未完成。

原版 CoreCLR 的事件序列明确定位了下一处公共缺口：v15 HTTPS 尝试在 DNS 阶段失败，没有进入 TCP 或 TLS。v16 直接复用此前已完成、已发布的完整 27 单元 libresolv，通过只转换元数据的 adapter 接入全部进程，并预装 canonical 库和别名；没有重新实现 resolver 或重编 27 单元。相同原版 CoreCLR 随后完成 DNS 与 TCP，进入 TLS HandshakeStart，之后正常 managed timeout，HTTPS 尚未成功。自有 main/ThreadPool 隐式 null fixture 则已由原版 CoreCLR 捕获 NullReferenceException、保留 ReadField 栈，并正常退出 0。

v17 源码准备支持从已物化镜像精确替换四个服务，保留其余公共库、搜索索引、账号、原 plist 和 resolver。兼容服务经过本地真实 ad-hoc 签名，独立验证全部代码页、特殊槽、entitlement 语义及签名前后非签名内容；八个输入架构 slice、240 个 section 的静态核验不代表新增 ARM 运行支持。这些副本明确不保留 Apple 原签名，也不声称 Apple 平台身份；原始失效签名的中间副本不会安装。同一公共 v17 的实际尝试中，trustd 已越过启动 sandbox 分支并读取 Admin/TrustSettings，FileHelper 也已启动；随后真实 SecTaskLoadEntitlements 错误 78 使请求被拒，securityd 则因 UnixError 22 中止。原版 codesign 达到限时，未出现 sign/verify 完成标记。同一 v17 的原版 CoreCLR HTTPS 再次完成 DNS/TCP、进入 TLS，随后 16.63 秒正常 managed timeout，无原生崩溃；日志仍指向 FileHelper 的 entitlement 元数据拒绝。下一项缺口是复用完整文件签名解析补齐通用 csops 元数据，而非伪造权限。此结果不能视为证书签名、HTTPS、Unity 授权或导出已通过。镜像、Apple 文件、entitlement payload、宿主 DNS 内容和私有日志均不包含在源码检查点中。


后续通用 clone 路径会替换继承的 resolver 挂载块，避免每代重复累加相同 bind；实际函数的四代宿主控制和已有三重复块输入均收敛为一块，未修改已运行的 v17 image，也未新增原生检查。
