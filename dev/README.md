# 开发者环境

开发约束：优先复用上游 Darling 已有实现。缺符号或调用失败时，先确认实际加载的库，再核对固定上游源码、构建目标、导出与依赖；已有实现应修正接入，避免在外围复制或简化重写。只有确认接口缺口或原实现错误后，才修改对应组件并保留与基线的差异和实际验证。现有组件的重新构建、版本适配和本实验环境的装配问题，应分别说明，不能统称为“Darling 没有这个组件”。[定点核对记录](resource-runtime/research/upstream-implementation-reuse-audit/README.md) 说明已确认的复用实例及核对范围。

[信号中断时保留已发送的内部 RPC 事务](resource-runtime/research/s2c-interrupted-reply-transaction/README.md)：真实故障抓取确认成功的旧 `mmap` 回复与新 `munmap` 回复碰撞；stage107 保留既有串行令牌，直到取走真实回复。五项实际 C++ 事务回归通过，旧源码负对照复现三项协议故障；原版 UE 构建继续验证，死亡与 exec 生命周期仍待处理。

[XNU 等待与既有挂起接口的原子交接](resource-runtime/research/xnu-wait-atomic-suspension-handoff/README.md)：stage106 保持上游 C++ 调度器原样，通过现有“挂起时释放锁”接口消除检查等待条件到挂起之间的唤醒丢失窗口。实际 C/C++ 时序回归 8 项通过，原版 UE 资源目录的 actool 查询正常返回且输出 plist 可解析；过宽的 stage105 唤醒标志方案经负对照发现风险后已撤销。完整 UE/CocoaPods App 编译与签名继续推进。

[原版 UE workspace 接入真实 CocoaPods](resource-runtime/research/unreal-cocoapods-workspace-integration/README.md)：原版 Darwin CocoaPods 已安装 LocalMath，原 workspace 的四个 UE 工程引用、scheme 和 UBT 命令保留，只增加 Pods 依赖；原 UE 配置通过 wrapper 与 Pods 配置合并，首次基线及 UE 原配置字节保持。原生安装和配置检查通过，原版 Xcode 已实际编译 Pod（见下一项）；UBT 最终链接和完整 App 仍待验证。

[原版 Xcode 已实际编译 UE 的 CocoaPod](resource-runtime/research/unreal-real-pod-archive/README.md)：同一 workspace 已生成真实 `libLocalMath.a`，LLVM 独立解析确认两个 arm64 对象及 `_local_add` 定义。后续 server 信号量调用崩溃使完整构建未完成；下一次继续复用 Pod 产物并抓取真实故障栈。此进展尚不代表 UBT 最终链接、UE App 或签名成功。

[复用 Mach 接口并接入真实内存统计](resource-runtime/research/host-vm-statistics-upstream-interface/README.md)：原版 Xcode 已完成 UHT 并进入 805 项 UBA 任务的调度准备，但上游现有 VM 统计占位接口返回全零，使原版调度器一直等待初始内存估计。stage104 在原接口中接入 Linux 实际页数，原生调用、历史版本与缓冲区边界检查通过；原有 XNU 分发和缓存复用，UE 代码未改。完整游戏构建继续验证，不能据此宣称 UE App 已完成。

[原版 UBA 调用原版 Clang 编译 iOS 目标文件](resource-runtime/research/original-uba-clang-library-paths/README.md)：完整 Xcode 构建已越过调度等待并启动编译，随后暴露研究环境过长的库搜索路径超出 UBA 固定缓冲区。只压缩路径组织、保留原库和查找顺序后，原版 UBA 与 Clang 的定点编译正常退出，产物与直接调用 Clang 逐字节一致。完整 UE 构建已继续，签名和 UE CocoaPods 仍待验证；没有替换 UBA 或修改引擎代码。

[内部任务恢复与 XNU 等待语义修正](resource-runtime/research/microthread-pending-wait-upstream-reuse/README.md) 复用原有等待队列与锁，将等待状态的清理放回真正唤醒处。定点测试修正前失败、修正后通过；stage102 的原版 UE 工程生成随后遇到另一处共享内存映射失败，尚未完整通过。Unity 的既有 stage101 验证范围不变。

[等待完成与后续代码执行的复查](resource-runtime/research/microthread-wake-completion-gating/README.md) 记录 stage102 后续完整运行仍出现等待队列崩溃，以及新增的“仅恢复调度、尚未真正唤醒”测试。原版适配代码的两个路径均在该测试中失败；stage103 的状态复查使四项定点测试通过，完整 UE 流程仍待验证。

[原版 UE 生成 iOS Xcode 工程并由原版 Xcode 解析](resource-runtime/research/unreal-stage103-original-ios-projects/README.md)：stage103 上 UBT 使用官方 `-NoIntelliSense` 选项正常退出，三个 iOS 工程和共享 scheme 写出；现有 stage101 Xcode CLI 读取游戏工程的 scheme、两个 target、五种配置，原生与外层退出均为 0。显式平台筛选触发的 workspace 清理问题已记录，完整 UE App 编译尚未通过。

[原版 UBT 保留可用 iOS workspace](resource-runtime/research/unreal-original-ios-workspace-preserved/README.md)：使用生成器默认平台选择后，原生与外层退出均为 0，workspace 与四个引用工程、游戏 scheme 均保留。没有修改引擎或手写 workspace；原版 Xcode 的实际游戏构建继续推进。

[将已有 UBT 环境接入 Xcode 子流程](resource-runtime/research/unreal-xcode-existing-dotnet-environment/README.md) 记录原版 UE 外部脚本首次失败的临时目录原因，以及复用现有临时文件系统、CLI home 和 NuGet 缓存的接入。新尝试已启动原版 MSBuild 工作进程；完整游戏构建仍未通过。

[恢复原版 UHT 配置并生成 11,804 个文件](resource-runtime/research/unreal-original-UHT-config-and-generated-headers/README.md)：Xcode 已进入原版游戏 UBT/UHT；从锁定提交恢复测试环境遗漏的原始配置后，同一份 235 模块的 iOS 清单由原版 UHT 正常处理，原生和外层退出均为 0。其余 58 个原始程序配置/辅助文件也已补齐，解析器代码未改；完整 Xcode 游戏构建继续验证。

UE 调试中修好的源代码运行库已接回 Unity/CocoaPods 证书构建：[stage101 整合实测](resource-runtime/research/stage101-unity-certificate-integration/README.md) 的原版 Xcode 构建、外层退出及 7 项严格签名与独立 CMS 检查全部通过。该次复用编译缓存；下文的新空构建目录流程也已通过。

当前 v12/stage101 也已完成[全新 Unity 项目的 Release xcarchive](resource-runtime/research/stage101-fresh-unity-release-archive/README.md)：App 和 UnityFramework 的签名、真实 dSYM、UUID 匹配及 LLVM 全量 DWARF 校验全部通过，原有 Debug 产物保留。

最新实测进展：全新 Linux Unity 6000.3.27f1 项目已完成 iOS 导出、原版 CocoaPods、空 DerivedData 中单次原版 Xcode 编译和证书签名；原生与外层正常退出，原版严格验签、独立 CMS 检查及实际 Pod 符号链接全部通过。[完整证据与可复用脚本](resource-runtime/research/unity-fresh-linux-certificate-end-to-end/README.md) 保存 48 项 Xcode 编译、282 项 IL2CPP 更新和 5 项签名记录。使用自生成测试证书；当前运行库的 Release xcarchive/dSYM 也已通过下述实测；开发者 provisioning、设备安装与完整冷重建继续推进。下文历史附件的“当前阻塞”对应其生成时的状态。

UE 的原版 Intel macOS SDK 已在 Darling 下成功编译完整 UnrealBuildTool：13 个项目、零警告、零错误、正常退出；生成的工具也已实际运行 `-Help` 并返回零。[完整 UBT 构建及启动证据](resource-runtime/research/unreal-original-UBT-build/README.md) 保存参数和 13 个私有产物的校验摘要。UE iOS App 仍未验证；Linux SDK 只用于下载依赖，实际编译使用原版 macOS SDK。

[真实文件创建时间与 iOS 平台检查](resource-runtime/research/unreal-real-birthtime-ios-validation/README.md) 已修复旧 stat 接口留下的未初始化字段。七项结果与宿主 Linux statx 精确一致，生成的原版 UBT 明确输出 `IOS VALID 26.1.1` 并正常退出；没有为这项读取修复重复完整 C# 构建。

底层修复及独立对照分别见 [普通 fork 双事件队列](resource-runtime/research/plain-fork-kqueue/README.md)、[Linux 依赖准备](resource-runtime/research/unreal-dependency-input-preparation/README.md)、[时间戳与原版 Touch](resource-runtime/research/native-file-timestamps-and-msbuild-touch/README.md)、[原版 Copy 回退](resource-runtime/research/original-msbuild-copy-fallback/README.md) 和 [正常启动输出与原版 Csc](resource-runtime/research/quiet-signal-setup-original-csc/README.md)。

[完整 Unity/CocoaPods 入口](resource-runtime/research/unity-full-app-cocoapods/README.md) 保留真实工程准备、原版 CocoaPods 安装和项目结构对照。最新[完整 Unity 证书 CI](resource-runtime/research/unity-certificate-ci/README.md) 已通过原版 xcodebuild 构建签名及七项原版/独立验签；使用临时自签证书，真实 provisioning 和设备安装仍待验证。

后续 Unity 工具链兼容修复见 [私有 procfs 与文件复制附件](resource-runtime/research/unity-private-procfs/README.md)：包含四个现有 fork 的源码提交、原版工具探针和独立产物检查，继续使用 Linux x86_64 与原版 Xcode 工程。

整合入口在独立的 [kxn/linuxcode](https://github.com/kxn/linuxcode) 工程；Darling 和各子模块的兼容性修改继续保存在各自的 fork。本目录提供 `linuxcode-dev`，在宿主 Linux 上构建和检查组件，帮助开发者接着完善编译流程。需要 Linux x86_64；不需要 Mac，也不使用 Darling 内核模块。

整合工程只使用 `main` 分支，安装器与开发者工具在同一个仓库维护；`checkout` 的固定实验工作区仍是 `runtime-2026.10.19` 对应的[早期 CocoaPods 基线](https://github.com/kxn/linuxcode/tree/375e52ea83e0f1a8dba3b16a0600d01292a9fe61)，其中 App 尚未签名。后续完整 Unity 构建、资源处理、ad-hoc 和证书签名修复保存在各研究附件与 fork 中；`checkout` 尚不会自动组装最新成功候选。工程测试仍使用 CoreServices 诊断策略；UE、归档后的 IPA 导出、开发者 provisioning 和完整冷重建仍未验证。

## 获取和核对源码

较新的 stage104/106 与 UE/Unity 研究源码不由旧 `checkout` 或固定 overlay 自动组合。可按[研究源码核验和审阅指南](research-sources.md)使用随默认 source 包提供的 `research-sources.py` 列举、核验、比较和导出；它不覆盖工作区，也不声明完整冷启动可用。

所有工具命令均在整合工程目录运行；`--workspace` 指向实际实验工作区，无需切换到该目录。路径中有空格时应加引号。

```bash
./dev/linuxcode-dev checkout /path/to/linuxcode-workspace
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace sources restore --clone
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace sources verify
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace doctor
```

根整合 CLI 也提供 `dev` 转发入口。`checkout` 创建新的目录，下载并检出固定的 workspace commit，而不是跟随可变分支。`sources restore --clone` 检查锁定的恢复脚本和源码清单 SHA256，再复用该里程碑的 `checkpoint/restore-sources.py`，下载缺失上游仓库及子模块、检查补丁 SHA、检查每个 base HEAD 后应用补丁。已有工作区不允许直接重置或覆盖；源码有冲突时命令失败，需保留开发者修改后自行合并。

这里的源码组织是 **17 个仓库的上游 base HEAD 加源码补丁**。旧构建脚本会校验这些 HEAD，因此不能直接把源码仓库切换到 fork 的发布 commit 后期待全部脚本继续工作。fork commit 是同一份修改的发布副本；`locks/source-manifest.json` 同时记录 base、fork commit、补丁 SHA 和 247 个修改文件的内容及执行位。`sources verify` 检查这 247 个文件和 17 个 HEAD，不会擦除额外开发修改，也不承诺检查仓库内每个未修改文件。

`source-manifest.json` 和 `workspace-files.json` 是不同清单。原始 b5225c4 发布的后者曾包含 11 个没有随 Git 提交的 CocoaPods 生成文件；当前统一锁定到修正后的版本快照 commit `375e52ea83e0f1a8dba3b16a0600d01292a9fe61`，其 workspace 清单只列实际公开文件。17 份源码补丁没有改变；最新快照同时纠正提交身份及相应提交引用，实际源码字节与构建证据保持不变。冷启动重建仍有下一节说明的输入缺口。

## 工具链和输入

`doctor` 不启动 Darling，不安装依赖，输出 JSON，分别列出工具版本、源文件差异和运行输入。命令本身完成检查时返回 0；请检查 `sources.exact_checkpoint`、`tools`、`inputs` 与 `cold_candidate_rebuild_ready`，不能仅凭 doctor 的退出码推断环境已经能编译 iOS。

实际组件脚本使用 Linux Clang/LLVM 19、GNU C++、CMake/Ninja、Bison/Flex/M4。Debian 13 的宿主包清单在 `debian-packages.txt`，需要时可由开发者安装：

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends $(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' dev/debian-packages.txt)
```

本机曾将 Bison、Flex、M4 解包至 `runtime/host-build-tools/usr`，CLI 在宿主没有对应工具时可复用这些私有工具，同时设置 Bison 数据目录及 M4 路径；这不是新机器必须有的额外下载。

开发者分为两个可实际工作的层次：

- **Linux 组件开发**：拿到锁定源码和宿主编译器，就可以运行 journal 的 ASan/UBSan 回归，并在私有目录完整构建 Darling server。此层不需要 Xcode、Apple OS 参考库或运行中的 Darling。
- **Xcode 集成开发**：需要整合入口导入的 Xcode、Darling rootfs、生成的 RPC/MIG 输入及当前运行配置。FSEvents 框架构建使用原版 macOS SDK 和现有 Darling 链接库；kernel 构建末尾实际在 Darling 中调用原版 Apple 链接器。当前完整候选还依赖额外的 Intel OS 参考镜像/缓存恢复出来的库、元数据及 ICU 数据。**XIP 一项不足以从零重建该候选**；所有历史阶段的依赖图和重建顺序还没有被完整自动化。

因此整合入口负责 XIP/rootfs 安装，本工具提供组件构建与诊断；`doctor` 明确保留 `cold_candidate_rebuild_ready: false`。不要把某台已有机器上的 `artifacts/*.json` 单独拷贝过去，当作所引用二进制已经存在或验证通过。

## 宿主开发 shell

```bash
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace shell
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace shell -- clang-19 --version
```

shell 的工作目录为指定 workspace，设置 `CC=clang-19`、`CXX=clang++-19` 和 `LINUXCODE_DEV_WORKSPACE`。进入 shell 前移除外部 `DYLD_*` 与 `LINUXCODE_*` 运行选择变量，防止不匹配的覆盖库污染宿主子进程；命令不是 Darling 会话。没有提供未验证的容器镜像；真实 Darling 启动所需 mount namespace 由现有运行入口管理。

## 按模块修改、构建和回归

动作命令默认实际执行，`--plan` 只输出 argv 和输出路径。构建目录默认在 `runtime/developer/<module>/`，首次创建后带专用标记；拒绝覆盖没有标记的既有目录。不会安装系统库，也不会替换当前默认 server、持久 prefix 或运行根。可用 `--output-dir /path/to/workspace/runtime/developer/my-change` 保留多个候选。

```bash
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test journal
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace build server
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace build fsevents
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace build kernel --plan
```

| 模块 | 源码入口 | 构建/回归含义 |
| --- | --- | --- |
| journal | `vendor/darlingserver/src/fsevents-journal.cpp` | Linux 原生 ASan/UBSan，真实 inotify 事件；`test journal` 编译后执行回归，当前 6,945 项检查 |
| server | `build-support/darlingserver`、`vendor/darlingserver` | 重新配置独立 CMake/Ninja 目录，完整 server、duct-tape 与 RPC 生成器；输出 `runtime/developer/server/darlingserver/darlingserver`，不启动它 |
| fsevents | `vendor/darling/src/frameworks/CoreServices/src/FSEvents` | 完整两源文件框架，通过现有构建脚本检查旧导出均保留；输出私有 framework；不自动选入候选 |
| kernel | `vendor/darling/src/external/xnu/darling/src/libsystem_kernel` | 现有完整构建脚本，约 879 个源文件；依赖 `runtime/darlingserver-source-build` 生成头/MIG 和 `runtime/vchroot-links-normal/darling-root`；链接时会启动 Darling |

`build server` 的新目录不会自动替换 kernel 脚本硬编码的 `runtime/darlingserver-source-build`。若 RPC 协议或生成器发生变化，需要先让 server 与客户端构建使用一致的生成输入，再按 profile/stage 脚本创建新候选；不要把单边 ABI 修改直接放入现有候选。FSEvents/runtime profile 亦须保持 framework、server、kernel 的匹配关系。

已有运行环境就绪后，逐项执行最相关的回归，而不是对每次修改无差别运行全部历史脚本：

```bash
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test vchroot
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test metadata
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test fsevents
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test stat-cache
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test real-sdk
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test xcode-version
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test ios-cocoapods
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace test ios-product
```

这些入口调用已有诊断/回归脚本，保留其日志和判定条件；`test ios-product` 静态检查真实 Mach-O/Pod 链接结果，不代表设备执行。运行类命令使用已有 `runtime/session.lock`，应串行执行。历史脚本可能重写其固定 `artifacts/` 和 `logs/`，新一轮实测前应先归档需要保留的旧证据。某些早期 dyld 故障没有原生命令状态标记，外层 launcher 的返回 0 不能当作成功；报告应包含真实任务、状态标记和产物校验。

## 保存修复和对应证据

完成一项有意义的进展后，先把变更和实际验证配在一起导出：

```bash
./dev/linuxcode-dev --workspace /path/to/linuxcode-workspace evidence /path/to/new-milestone-capsule \
  --report artifacts/my-feature-test.json \
  --report logs/my-feature-test.log \
  --source vendor/darlingserver/src/my-new-source.cpp
```

`--source` 用于显式加入新建且尚未被 Git 跟踪的文件；没有新文件就省略。导出会遍历 17 个源码仓库的跟踪修改和锁定修改文件，保留基于各自上游 base HEAD 的补丁，并为源码、执行位、补丁和显式报告记录 SHA256。每个 patch 只含所属仓库修改，不把嵌套仓库的 gitlink 当作补丁代替其源码。二进制内容和隐式全目录报告收集会被拒绝；导出前检查所选文本日志是否含本机私密信息。

导出目录必须新建。工具不 push，也不把“导出成功”记录成“运行验证成功”。发布者在各组件 fork 创建对应源提交，更新整合工程的 source lock，再把该 capsule、构建命令、测试结果、实际产物哈希及剩余限制一起提交到新的 milestone。保留上一里程碑，不改写历史成功或失败记录。Apple XIP、SDK、提取的闭源库、证书和私钥留在本机输入目录，不进入公共源码包。

## 继续开发原版资源工具

新增的 [资源源码更新包](resource-runtime/README.md) 在本仓库 `main` 维护，可向固定源码快照应用并回滚。它带有 67 个原版 Intel 资源映像的锁定配置、重建参数和针对 Swift/Objective-C 缓存元数据的检查。资源工具仍停在实际依赖加载阶段；该目录明确列出额外原始输入、无显示环境测试和当前缺口。安装器的已验证编译基线保持原来的固定快照。

[原版 codesign 附件](resource-runtime/research/native-codesign/README.md) 保存了后续内核扩展属性源码、缓存提示、新接口兼容、原版工具入口和实测证据。原版 xcodebuild 与原版 codesign 已一起完成简单 CocoaPods App 的 ad-hoc 构建，整合 PATH 入口也已复现。附件显式复制到对应工作区，不由较早固定 overlay 自动应用；仍需完整研究基线，不能把源码打包成功当作干净机器重建成功。

[Unity 6 事件注册修复](resource-runtime/research/unity-kqueue-receipts/README.md) 已让原版 IL2CPP 越过 EAGAIN，启动 Bee 和 il2cpp-compile。完整源码库通过事件、共享内存和原版 ad-hoc 签名回归；当前编译仍因子进程环境/`uname` 查找失败，实际 GameAssembly 产物尚未生成。

[Unity 子进程环境与原版 plutil 修复](resource-runtime/research/unity-exec-environment/README.md) 已恢复原版 .NET 环境枚举并补齐绝对路径 plutil，新的候选通过原版 ad-hoc 签名回归。最新构建在 Bee 因客体 `/proc` 判定 Linux 后拒绝 iOS 工具链，GameAssembly 仍未生成；包含源码、实际失败证据和后续定位。
