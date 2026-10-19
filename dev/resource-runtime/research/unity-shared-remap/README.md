# Unity 6 的原版 IL2CPP：共享内存重映射

已在 Linux x86_64/Darling 中运行 iPhoneOS/arm64 导出工程自带、未经修改的 macOS x86_64 IL2CPP（.NET 7.0.13）和 Bee：原生与外层状态均为 0，分别约 5.5 秒、3.8 秒。沿用[上一份 Unity 宿主工具附件](../unity-host-tools/README.md)的固定工程提交，没有关闭运行时的双映射能力，没有换用 Linux IL2CPP。**帮助命令成功不等于完成游戏编译、链接或签名。**

## 实际修复

1. 在原版请求的断点中，实际重映射长度为 8192 字节，已共享源区域只有 4096 字节。新的实现保留每个现有 backing file 和文件偏移，只转换剩余私有区域，再先预留完整目标地址区间、逐段建立共享映射。旧别名继续共享相同数据，不能通过复制整块数据来冒充共享。
2. 新路径暴露了接收循环的问题：一次不带 FD 的服务器调用将 `recvmsg` 的 `msg_controllen` 改成零，后续映射消息的 FD 因缓冲区容量未恢复而丢失。内核兼容库现在逐次恢复接收容量；原有描述符类型/数量校验保留。完整 879 个源码单元重新构建，隔离运行根同时选择配套 server、kernel 和 mldr。
3. 第一个功能候选能输出 IL2CPP 帮助，但在 90 秒内没有返回；实际 GameAssembly 尝试也超时。现场堆栈位于正则表达式扫描，进程约 2341 个映射区域、177 个 remap 区域。现在每次共享记录校验只读取一份 `/proc/<pid>/maps`，按地址索引查找，保留设备号、inode、文件偏移及保护属性核对；没有长期缓存进程映射表。

源码已保存到原有分支：[darlingserver](https://github.com/kxn/darlingserver/commit/b45927717e7f1bb0dc695ba136e9c56bfb529945)、[darling-xnu](https://github.com/kxn/darling-xnu/commit/a193da59f339d283f46ff8f39e049352ad846620)。提交身份均为 Comman Kang，整合工程仍只在 main 维护。

## 验证范围

- 实际进程完成 11 次 remap：逐步扩大并拼接不同后端、非零及嵌套文件偏移、双向数据修改、释放源/其他别名后的存活、地址复用、逐段保护属性、不同的地址舍入规则，以及错误路径和后端 FD 回收。全部按实际字节和系统状态检查。
- 原有 memory-entry 回归通过：32 个生命周期、只读与权限提升拒绝、地址复用、32 次并发映射、真实进程间能力传递、双向共享、释放后的生命周期和 FD 回收。
- 新解析器与独立 sscanf 对照203 条实际进程映射记录，另以真实 memfd 的 fstat 核对设备号/inode/偏移，并验证保护属性变化；16 项非法输入均拒绝。
- 优化前的超时报告保留；仅打印帮助但没有成功退出的尝试始终记录为失败。优化后的原版 IL2CPP、Bee 均有独立原生退出标记。

当前仍不支持任意固定地址/复杂 mask 映射，也没有实现完整 VM 继承或最大执行权限策略；未跟踪的现成共享文件映射会明确拒绝。私有页首次转换仍有既有的“读取后替换”并发写入窗口，不能据此声称与 XNU 完全等价。真实 Unity App/CocoaPods/原版签名、actool/ibtool 资源产物和证书/provisioning 仍待完成。

## 已有开发工作区复现

需要已有研究工作区、前一份 mldr 附件、匹配的生成 RPC/头文件、LLVM 19、原版 Xcode/SDK 与运行基线。审阅并合并 payload 中的同名源码，保留已有开发修改。不是从 XIP 开始的完整冷安装，也不自动应用到固定 67 镜像 overlay。

```bash
clang++-19 -std=c++17 -O2 -Ivendor/darlingserver/internal-include \
  fixtures/hello/proc-maps.cpp -o /tmp/linuxcode-proc-maps-test
/tmp/linuxcode-proc-maps-test
python3 scripts/build-libsystem-kernel-source.py \
  --output-dir runtime/shared-remap-kernel-NEW \
  --variant-base runtime/mldr-dynamic-rlimit-v3/darling-root \
  --report artifacts/shared-remap-kernel-NEW-build.json
python3 scripts/build-shared-remap-server.py \
  --parent-stage artifacts/mldr-dynamic-rlimit-v3-stage.json
python3 scripts/stage-shared-remap-runtime.py \
  --server-stage runtime/shared-remap-server-NEW/stage.json \
  --kernel-build artifacts/shared-remap-kernel-NEW-build.json --tag v2
python3 scripts/test-shared-remap.py --stage artifacts/shared-remap-runtime-v2-stage.json
python3 scripts/probe-unity-export-host-tools.py --export device \
  --runtime-profile scripts/shared-remap-runtime-profile.py \
  --runtime-stage artifacts/shared-remap-runtime-v2-stage.json
```

NEW 换成构建器输出的实际目录；固定 tag 已存在时换新名称，不能覆盖旧证据。若使用这里记录的新 fork HEAD，kernel 构建器可另传 `--source-manifest /path/to/attachment/reference/source-revisions.json`，只接受精确记录且 base 对应的提交；干净 fork 的完整冷重建尚未实测。

原版构建子目标检查使用新的独立产物目录：

```bash
python3 scripts/probe-xcode-service-runtime.py build \
  --native-codesign-stage artifacts/native-codesign-ci-v3-stage.json \
  --identity-store runtime/local-identity-xcode-empty-v1/store.plist \
  --mldr-stage artifacts/mldr-dynamic-rlimit-v3-stage.json \
  --shared-remap-stage artifacts/shared-remap-runtime-v2-stage.json \
  --core-volume-diagnostic --cfprefsd-daemon --filecoordination \
  --xcode-arguments-file config/unity-device-gameassembly-v3-build-arguments.json \
  --timeout-seconds 600
```

GameAssembly 参数显式关闭该静态库子目标的签名，只用于编译验证，不代替最终 App 签名。所有 Darling 执行共享 session.lock 串行运行，并移除图形环境变量。这个附件只包含源码、配置和证据摘要，没有 Apple/Unity 二进制、SDK、引擎资产或签名凭据。

## 最新 GameAssembly 结果：成功横幅被拒绝

优化后的原版 xcodebuild 已读取 iPhoneOS/arm64 工程，并调用原版 IL2CPP 的 `--compile-cpp` 编译驱动。驱动在子进程 stdout/stderr 的异步 socket 注册中报 `System.Net.InternalException EAGAIN`。Unity 原始脚本随后执行清理命令并返回 0，Xcode 因此显示 BUILD SUCCEEDED；**预期的 libGameAssembly.a 不存在，所以该构建被记录为失败，没有发布编译成功里程碑。** 工程和脚本内容没有为绕过错误而修改。

独立探针实际加载同一原版 libSystem.Native.dylib：注册返回 PAL 错误 65542、Darwin errno 35；直接调用带 EV_RECEIPT 且无输出缓冲区的 kevent 返回 -1/errno 35，但后续队列确实收到 4 字节的数据。此探针当前预期失败，保留了调用结果与真实事件不一致的证据，下一步修复 libkqueue 的注册返回语义，不能把错误强改成成功。

```bash
python3 scripts/probe-original-dotnet-socket-events.py \
  --stage artifacts/shared-remap-runtime-v2-stage.json
```

原有签名构建基线仍单独保留；这个新候选尚未完成完整签名构建回归。失败路径与成功的内存/启动检查分别记录在 evidence.json 中。
