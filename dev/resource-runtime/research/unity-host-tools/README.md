# Unity 宿主工具与 Darling 描述符上限修复

已在 Linux x86_64/Darling 中运行 Unity 2022.3.42f1 导出工程自带、未经修改的 macOS x86_64 IL2CPP 和 Bee，二者 `--help` 原生与外层退出均为 0。没有显示图形界面，没有替换成 Linux 版 Unity 工具。**这只是宿主工具启动里程碑，尚未完成 Unity/UE App 编译或签名。**

## 修复与证据

IL2CPP 自带 .NET 6 降低 `RLIMIT_NOFILE` 后，旧 mldr 仍按启动时缓存的上限分配内部通信 FD。实际系统调用先把软上限降到 10241，随后 `dup2(3, 524286)` 返回 `EBADF`，线程初始化失败。新分配器读取当前软上限，保留旧预留索引，跳过已占用的描述符，耗尽时返回错误。不是忽略 socket 错误，也没有关闭 .NET 的功能来避开它。

真实 Linux 测试对旧源码复现断言失败；新源码通过降低/恢复上限、已有高号 socket 继续通信、占用 FD 保持不变、零上限、耗尽和 8 线程共 256 次实际 datagram 收发。完整 mldr 由五个源码单元构建，在隔离运行根中选择，没有替换基础安装。修改已推到[现有 Darling fork 分支](https://github.com/kxn/darling/commit/9550252e0594e0a8e858c2b449c66d6e282140d5)，提交身份仍为 Comman Kang。

## 真实引擎输入和失败

- [Unity 2022 导出](https://github.com/SuQiang2007/iOSHomeQuickActionsOCWrapper/tree/a2a2f5f1883b14358693a0f3a3a4372b24aab7d8) 是 **iOS Simulator/x86_64**，包含生成的 C++、引擎库、IL2CPP、Bee 和 Storyboard。只用它证明宿主工具启动，不能充当 iPhoneOS 构建证据。
- [Unity 6 导出](https://github.com/kusadact/uEmuera-for-iOS/tree/3944888ac3917624081ff18beca2874c0ec19748) 的工程配置是 **iPhoneOS/arm64**，使用 .NET 7.0.13。它的 Bee 已正常启动；IL2CPP 启动触发 Darling 未实现的共享内存重映射路径，随后超时。这个失败尚未修复，不能据此声称 Unity 6 可用。引擎静态库保存在 Git LFS，普通 Git 检出得到的 134 字节指针不是有效引擎库。已实际下载 217810216 字节原库并核对 LFS SHA256，独立检查全部 1640 个 Mach-O 对象均为 iOS/arm64，仍未证明可链接完整 App。

原版 xcodebuild 已读取该工程、生成构建计划并进入 GameAssembly 脚本阶段；之后 Darling 服务在同一共享内存重映射未实现路径退出，原生 Xcode 状态 132，外层最终 -9。这是编译子步骤检查，参数明确关闭该静态库目标的签名，不能代替最终 App/CocoaPods/签名验证。最终构建还要完成资源工具和实际产物检查。资源实验 v40 已越过 XPCDistributed 和 AAAFoundationSwift，actool/ibtool 当前缺 AppleIDSSOAuthentication；其二进制重建仍拒绝无法确定的代码/数据边界和引用，没有生成猜测实现。

## 在已有开发工作区复现

这是显式源码附件，不由固定 67 镜像 overlay 自动应用。需要已有研究工作区及其 Darlingserver 生成的 RPC/配置头、LLVM 19、XNU 开源头和匹配运行基线；单独下载本附件尚不能完成冷安装。先审阅 `payload/`，在独立工作区合并同名文件，保留已有开发修改。`reference/mldr-before.c` 保存精确旧源码供负向回归。

```bash
python3 scripts/build-mldr-source.py
python3 scripts/test-mldr-dynamic-rlimit.py \
  --build runtime/mldr-source-NEW/build.json \
  --baseline /path/to/linuxcode/dev/resource-runtime/research/unity-host-tools/reference/mldr-before.c
python3 scripts/stage-mldr-dynamic-rlimit.py \
  --build runtime/mldr-source-NEW/build.json --tag v1
python3 scripts/probe-unity-export-host-tools.py \
  --runtime-profile scripts/mldr-dynamic-rlimit-profile.py
```

`NEW` 使用构建器实际打印的目录；v1 已存在时不要覆盖，换新 tag 并通过宿主探针的 `--runtime-stage artifacts/mldr-dynamic-rlimit-TAG-stage.json` 显式选择对应 stage。宿主探针要求 `runtime/unity-quick-actions-export` 或 `runtime/unity-uemuera-device-export` 检出上述固定提交且无受跟踪文件修改；`--export device` 选择后者。执行共享 `runtime/session.lock`，串行运行，每次报告位于新的临时目录。工具探针会固定完整受跟踪输入的哈希；帮助命令成功不证明工具能完成转换或编译。

GameAssembly 检查示例（已有对应服务、Xcode 和固定导出工程）：

```bash
python3 scripts/stage-mldr-dynamic-rlimit.py \
  --build runtime/mldr-source-NEW/build.json --tag v2 --diagnostic
python3 scripts/probe-xcode-service-runtime.py build --tool-dispatch \
  --mldr-stage artifacts/mldr-dynamic-rlimit-v2-stage.json \
  --core-volume-diagnostic --cfprefsd-daemon --filecoordination \
  --xcode-arguments-file config/unity-device-gameassembly-v1-build-arguments.json \
  --timeout-seconds 240
```

这些输入当前预期失败；重复实验应换新的输出目录。附件只包含源码、配置和带哈希的证据摘要，不含 Unity 或 Apple 二进制、引擎资产、SDK、证书或凭据。完整原版签名基线仍在前面的 codesign 附件中，尚未验证与这个新 mldr 合并后的签名构建。

真机引擎库输入检查可执行 `python3 scripts/verify-unity-device-engine-input.py`。它只解析并核对本地原库，不运行引擎代码、不代表游戏产物完成。新的 mldr 还在已有原版签名运行配置上通过了 IL2CPP/Bee 启动检查，但没有因此声称签名构建回归已通过。
