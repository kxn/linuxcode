# 原始 GOT 身份、Swift 媒体桥接与 dispatch 类型

本附件继续运行原版 Intel actool / ibtool，保存六个原版候选：ProDisplayLibrary、WatchdogClient、libswiftVideoToolbox、libswiftCoreMedia、libswiftCoreAudio、CoreAudio。可执行节、VM 相对位置和序列化绑定均经独立检查，六个候选的可执行指令与原始输入一致。各候选还通过原版 Xcode dyld_info 校验及其损坏副本对照；API 的整体行为尚未验证。

## 通过原始 GOT 确认数学函数身份

ProDisplayLibrary 剩余地址对应四个同地址数学函数名。只按地址无法判断应使用哪一个；原始共享缓存 GOT 记录明确写的是 `_scalbn`。新校验器同时要求：原始 x86 跳转桩指向所选单元、原始指针与 patch 表一致、零 addend / 非弱导入，以及原始依赖的真实转导出链最终到达该名称。

verify-original-pooled-import.py 跟随原始显式符号转导出或 LC_REEXPORT_DYLIB 整库转导出，记录每一步来源 SHA。审计器和候选准备器分别回读原始输入；准备器重新计算证明，拒绝同地址别名、伪造跳转桩、修改后的 patch 名称、来源 SHA 或普通依赖冒充转导出。不会按最近符号推断函数，也不增加通用别名回退。

```bash
python3 scripts/test-original-pooled-import.py
python3 scripts/test-pooled-import-preparation.py
python3 scripts/audit-resource-image-imports.py \
  --target prodisplaylibrary-patch-got-v1 \
  --original-got-import _scalbn=/usr/lib/libSystem.B.dylib \
  --output artifacts/my-prodisplay-import-audit.json
```

前两个测试分别使用独立打包的 cache 二进制夹具和真实原始 cache 输入；共 20 项。准备器的八项篡改负例均在 pin、历史和报告发布之前拒绝。原有准备与转导出测试另有 12 项通过。ProDisplayLibrary 的 406 项引用现已全部审计，新候选不再缺这一个 GOT 身份。

CoreAudio 在 Intel 原始输入中有缺席的 RemoteProcessingBlock 弱依赖。候选仅保留经原始加载命令、undefined weak 标记及零值确认的缺席语义，没有构造替代框架或实现。

## 使用苹果开源的 dispatch 类型定义

Darling 原有 libdispatch 缺少 `_dispatch_source_type_exclaves_notification`。从苹果 libdispatch 提交 2361ffb78a76f7ee488cd052eb0bc5c767118bf9 移植真实初始化器，使用当前源码的创建、合并回调和 refs 布局。初始化器正文与上游字节一致；filter 标识为 XNU 的 -18。

完整重编译 32 个源码单元，保留 654 个原有直接导出，只增加所需类型。原生进程核对原版标量字段、80 字节 refs 大小、真实回调所在映像、无效输入拒绝、实际分配/取消和异步调度；另完成 1024 次 workloop FIFO/串行任务及嵌套上下文回归。旧库中不存在此类型的负例也通过。

Linux libkqueue 没有 exclaves 事件后端，原生测试确认该 filter 返回 EINVAL；没有伪造通知或声称支持事件投递。这是类型定义和 ABI 补齐，不是完整的 exclaves 子系统。

源码已推送到原有 [kxn/darling-libdispatch 分支的 19bbe6e](https://github.com/kxn/darling-libdispatch/commit/19bbe6eaa822f10bd82fdd4a350277a5978896cc)。沿用 linuxcode/xcode-x86_64，作者与提交者均为 Comman Kang，未创建新分支或账号。source-fork.json 记录经核对的 127 个源码/头文件与构建输入关系。

## 防止构建目录中的旧库被一起选入

完整 libdispatch 构建目录还带有较早的 libxpc、libdyld 等运行组件。第一次把整个目录加入资源进程的搜索路径，原版 SwiftXPC 实际暴露了缺失的 peer-error 导出。这个失败保留在 reference 中。

现将字节完全相同的新 libdispatch 单独放入 dispatch-exclaves-resource-v1/libraries，该目录仅允许存在 libdispatch.dylib。七项关键 provider 路径在新旧原生对照中保持一致，包含 peer-error 对象、XPC 连接、Mach 消息、pthread、malloc、dlopen、objc_msgSend；类型及两个真实回调则明确来自新映像。

配置只在 actool / ibtool 子进程选用新库，普通构建调用方继续使用原有运行根。旧 workloop profile 也改为解析精确历史源码 SHA，允许验证旧二进制对应的已保存源码，而不要求工作目录仍停留在旧源码版本。

```bash
python3 scripts/build-dispatch-workloop-source.py \
  --output-dir runtime/my-dispatch-build --report artifacts/my-dispatch-build.json
```

在本地建立仅含所选库的独立 stage 后，可用 probe-dispatch-exclaves-type.py 运行完整原生对照。其 bootstrap configuration 应使用尚未选入新 dispatch 的环境，例如本附件 v62；它要同时验证旧库缺席和新库存在。最终选择新 dispatch 的示例为 v64/v65，不应用于 bootstrap 缺席对照。

## 仍需完成的编译链

最终原版工具及真实 Unity/CocoaPods workspace 结果见 evidence.json。当前缺口已推进到 caulk 所需的 C++17 `std::pmr::memory_resource` RTTI。现有 libc++ 只有旧实验命名空间，不能直接别名化这两个不同的 C++ 类型。本地 LLVM 源码已有标准命名空间的真实 key function；下一步应生成并验证正确的类型信息、虚表与生命周期行为。

尚未完成实际资源编译、完整 Unity/UE App 链接和签名，也未验证 provisioning、设备运行或 archive/export。默认安装环境没有提升。原版执行文件、工程和命令流程保持不变，Darling 会话串行运行，并清除 DISPLAY / WAYLAND_DISPLAY / XAUTHORITY。

payload 相对于完整开发工作区，需与前序研究附件审阅合并，保留源文件 SHA 历史，并使用本地锁定的 Intel 系统 cache、Xcode/SDK、Darling 运行基线和 LLVM。输出、stage、日志均使用新名称，不能覆盖已映射库。不是干净机器的一键安装成果。

reference 中的日志以 JSON 的 text 字段保存精确 UTF-8 字节，original-file-map.json 提供原始 SHA；source-history.json 映射精确旧源码。summary 下明确标记的文件只是完整本地报告的摘要，不是可加载的完整 stage。公开包只包含源码、文档和元数据，不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。上游文件保留各自许可证头。
