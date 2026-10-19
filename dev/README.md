# 开发者环境

整合入口在独立的 [kxn/linuxcode](https://github.com/kxn/linuxcode) 工程；Darling 和各子模块的兼容性修改继续保存在各自的 fork。本目录提供 `linuxcode-dev`，在宿主 Linux 上构建和检查组件，帮助开发者接着完善编译流程。需要 Linux x86_64；不需要 Mac，也不使用 Darling 内核模块。

整合工程只使用 `main` 分支，安装器与开发者工具在同一个仓库维护；固定实验工作区保存在版本标签 `runtime-2026.10.19`。当前锁定的可复核基线是 [原版 xcodebuild 成功编译带 CocoaPod 的 iOS App 的里程碑](https://github.com/kxn/linuxcode/tree/375e52ea83e0f1a8dba3b16a0600d01292a9fe61)。该 App 尚未签名，工程测试使用 CoreServices 诊断策略；资源工具、Unity/UE、归档导出和可信签名还没有贯通。这是开发基线，不代表所有游戏工程都已兼容。

## 获取和核对源码

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
