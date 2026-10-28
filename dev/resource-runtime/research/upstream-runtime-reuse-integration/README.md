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
