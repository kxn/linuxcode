# Unity 6 原版 .NET 的事件注册修复

Linux x86_64/Darling 中，原版 Unity 6 IL2CPP 已越过子进程管道的 EAGAIN 错误，实际启动 Bee 与原版 il2cpp-compile。**GameAssembly 静态库和完整游戏 App 仍未生成。** 原版 Unity 脚本会用后续清理命令的退出码掩盖编译错误，因此依然独立检查产物，不接受 Xcode 的成功横幅作为编译完成证据。

## 修复及验证

Darling 的 libkqueue 已成功注册事件，但遇到 EV_RECEIPT 且没有回执输出槽时返回 -1，并保留之前的 EAGAIN。现在继续处理后续成功变更；真实失败且无回执槽时通过 errno 返回实际错误；有回执时保留输入 flags，并立即返回已生成的回执，避免因剩余输出空间而等待无关事件。这与当前工作区 Apple 开源 XNU 的 kevent_register 处理分支一致。

源码提交：[kxn/darling-libkqueue dfbc31b](https://github.com/kxn/darling-libkqueue/commit/dfbc31b775480ac90daf229094c2a4e423fdb132)，在 fork 的原默认分支 master 保存；提交身份 Comman Kang。整合与开发附件继续在本仓库 main。

- 同一份未经修改的 Unity .NET 7.0.13 libSystem.Native.dylib，修复前注册返回 PAL 65542 / Darwin errno 35，修复后返回 0。真实 socket 收到 4 字节数据；成功时不要求 errno 归零。
- 实际 kevent、kevent64 检查通过：无回执槽、批量注册、回执槽耗尽后继续应用变更、有额外槽且 NULL timeout 时立即返回、ENOENT/EINVAL、错误回执、用户数据、读写就绪及删除监听。
- 完整重建 20 个源码单元，包括 libSystem 初始化和全部本修订的 libkqueue。保留旧库的 46 个本地源码导出及 58 个显式重导出；没有将旧库的代码地址复制进新库。
- LLVM 19 链接结果还需处理两个已实测的问题：重导出生成重复依赖记录，及非排序的强定义标记使旧 dyld 在两份队列状态间错误绑定。构建器用实际导出生成仅供链接的 TBD，保留单一依赖记录并排序纯强定义标记。运行时使用的是真实源码库和原有依赖，没有用 TBD 代替实现。
- 新候选通过共享重映射、32 周期/32 并发 memory-entry、真实跨进程能力传递和双向共享回归。
- 新候选通过原版 codesign ad-hoc 签名、原版严格校验、独立签名检查、XML/DER entitlements 对照，以及代码页、Info.plist、封印资源、新增资源四类篡改拒绝；没有使用 zsign。

## 已有开发工作区复现

依赖[前一份共享内存附件](../unity-shared-remap/README.md)、完整研究基线、原版 Xcode/SDK、LLVM 19，以及已有的 RPC 生成头和参考运行库。这不是完整冷安装，也不会自动改变默认启动器或固定的 67 镜像 overlay。payload 的源码需审阅后合并到同名路径；以前报告引用的源码应先按哈希归档。

libSystem 源码固定为 `darlinghq/darling-Libsystem` 的 `08df454b6eb0df9400aa4c39839a7efd6efd2c3c`。在已有 Darling 检出中，可使用其固定 gitlink 获取：

```bash
git -C vendor/darling submodule update --init --depth 1 src/external/libsystem
python3 scripts/build-libsystem-kqueue-source.py
# 使用上一步输出的实际目录，不覆盖已有证据。
python3 scripts/link-libsystem-kqueue-source.py \
  --objects runtime/libsystem-kqueue-source-NEW/objects.json
python3 scripts/probe-original-dotnet-socket-events.py \
  --runtime-profile scripts/libsystem-kqueue-runtime-profile.py \
  --stage runtime/libsystem-kqueue-source-NEW/build.json
python3 scripts/test-kqueue-receipts.py \
  --stage runtime/libsystem-kqueue-source-NEW/build.json
python3 scripts/test-shared-remap.py \
  --runtime-profile scripts/libsystem-kqueue-runtime-profile.py \
  --stage runtime/libsystem-kqueue-source-NEW/build.json
python3 scripts/probe-original-codesign-native-identity.py \
  --runtime-profile scripts/libsystem-kqueue-runtime-profile.py \
  --runtime-stage runtime/libsystem-kqueue-source-NEW/build.json \
  --tamper-checks --with-entitlements
```

原版 Xcode 构建使用新的独立输出目录，保留原工程和原脚本：

```bash
python3 scripts/probe-xcode-service-runtime.py build \
  --native-codesign-stage artifacts/native-codesign-ci-v3-stage.json \
  --identity-store runtime/local-identity-xcode-empty-v1/store.plist \
  --mldr-stage artifacts/mldr-dynamic-rlimit-v3-stage.json \
  --shared-remap-stage artifacts/shared-remap-runtime-v2-stage.json \
  --libsystem-kqueue-build runtime/libsystem-kqueue-source-NEW/build.json \
  --core-volume-diagnostic --cfprefsd-daemon --filecoordination \
  --xcode-arguments-file config/unity-device-gameassembly-v4-build-arguments.json \
  --timeout-seconds 600
```

这些命令不拉起图形界面；Darling 执行通过 session.lock 串行运行。GameAssembly 只是静态库子目标，参数显式关闭其签名，不能代替最终 App 签名。

## 下一处实际失败

本次原版 xcodebuild/IL2CPP 编译在 Bee HostPlatform 初始化中报告无法找到或打开 `uname`，预期的 libGameAssembly.a 不存在。`/usr/bin/uname` 实际存在；独立探针通过同一原版 System.Native 完成 stat、fork/exec、获取 Darwin 输出及等待子进程，因此尚不能把问题归因于缺少命令文件。正在检查实际托管调用的环境与路径查找。

完整 Unity/UE + CocoaPods App、原版 actool/ibtool 产物、开发者证书/provisioning、设备信任、archive/export 和完整冷重建均未完成。evidence.json 记录本机报告路径和哈希，摘要不能替代开发者自己运行验证。公开附件不含 Apple/Unity 二进制、SDK、资源或凭据。
