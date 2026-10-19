# 原版资源工具的开发源码

本目录在整合仓库的 `main` 维护，向固定的 `runtime-2026.10.19` 源码工作区应用一组可审阅、可回滚的更新。Darling 及其子模块仍在原有 fork 中维护，不新增开发分支或提交身份。

这批代码恢复 64 个明确锁定的原版 Intel 资源映像，补上 Swift KeyPath 二进制泛型环境、缓存合并的 Objective-C 协议引用和类引用表。它是资源工具兼容性的开发材料。**原版 actool/ibtool 尚未完成启动和资源编译**；最新实际缺口是 DesktopServicesPriv 所需的 Sharing.framework。没有完成 Unity/UE、签名或完整冷安装。

## 应用到开发工作区

在整合仓库目录运行，工作区按现有开发工具检出固定版本：

```bash
./dev/linuxcode-dev checkout /path/to/workspace
./dev/linuxcode-dev --workspace /path/to/workspace sources restore --clone
python3 dev/resource-runtime/apply-overlay.py --workspace /path/to/workspace --plan
python3 dev/resource-runtime/apply-overlay.py --workspace /path/to/workspace
```

应用器核对固定 HEAD、检查点、依赖和全部目标文件后才修改文件。它保留已有文件的普通权限位，不把不同 umask 误当作源码修改；目标路径有不同的工作区内容、暂存修改或符号链接时拒绝覆盖。重复执行是幂等操作。应用输出包含备份目录及完整回滚命令；回滚遇到后续开发修改时也会拒绝覆盖。它不下载、不编译、不执行 Darling、不修改 Git 索引。

对已有开发修改，应先审阅并自行合并源码差异。不要为通过检查而重置工作区或清掉暂存区。

## 在 Linux 重建参考映像

此步骤不需要运行 Darling 或使用桌面。需要 LLVM 19 工具、已恢复的 DyldExtractor 源码，以及与 `payload/config/ios-resource-image-pins.json` 中 SHA256 对应的本地原始输入：

- `runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h` 及其完整子缓存。
- `runtime/fullsystem-libraries/` 下对应的提取映像。

这些额外的 Intel OS 参考输入没有包含在公开包中，Xcode XIP 也不包含它们。完整候选的从零组装依赖图仍未自动化完成。输入和现有运行环境限制见 [运行时输入](../../docs/runtime-inputs.md)。

若工作区还没有 DyldExtractor，在新的依赖目录检出固定版本（已有目录先核对并保留本地修改）：

```bash
git init /path/to/workspace/vendor/DyldExtractor
git -C /path/to/workspace/vendor/DyldExtractor remote add origin https://github.com/arandomdev/DyldExtractor.git
git -C /path/to/workspace/vendor/DyldExtractor fetch --depth 1 origin 0e1b35a5f60e7041c51b57a54cc36d815fe7adf2
git -C /path/to/workspace/vendor/DyldExtractor checkout --detach FETCH_HEAD
```

先安装固定的项目内反汇编依赖；它只下载并按长度/SHA256 核验公开的 Capstone wheel，不修改系统 Python：

```bash
python3 /path/to/workspace/scripts/prepare-capstone.py
python3 dev/resource-runtime/build-resources.py --workspace /path/to/workspace --plan
python3 dev/resource-runtime/build-resources.py --workspace /path/to/workspace \
  --target extensionkit-resource-native --target onboardingkit-resource-native \
  --target telephonyutilities-resource-native
```

省略 `--target` 会按 `overlay.json` 中实际验证过的参数重建全部 64 项。每次运行保存新的 `logs/developer-resources-*/` 及结果 JSON，首个失败会停止后续构建。输出在 `runtime/rebuilt-<target>/`，不会安装或选入默认运行根。请在自己的开发工作区迭代；重建会更新该目标的实验产物与报告。

相关检查：

```bash
python3 /path/to/workspace/scripts/test-swift-keypath-environments.py
python3 /path/to/workspace/scripts/test-objc-protocol-got.py
python3 /path/to/workspace/scripts/test-pooled-objc-class-references.py
```

KeyPath 布局检查是 22 项；协议元数据指针通过独立 LLVM 重定位检查六项；类引用表的两层指针、符号绑定和损坏输入拒绝检查共 33 项。后两项需要先重建对应三个目标。`test-objc-protocol-got.py` 的文件名保留自早期诊断；实际检查的两个残留引用位于原始 `__objc_const`，并非 GOT。结构检查不证明完整框架 API 可执行。测试报告存在时应先保存旧证据；协议测试也可用 `--output artifacts/new-protocol-check.json`。

## 实际运行原版工具

只有在固定编译基线的 Darling/Xcode 候选和原始参考输入已经组装好后，才运行下面的命令。运行阶段还需要 `runtime/recovery/macOS Base System/` 下对应框架的原始 Resources 目录；stage 脚本在该路径存在时复制这些 bundle 资源。只有库映像并不代表运行输入完整。这些命令不会用重建成功代替原版工具成功：

```bash
python3 /path/to/workspace/scripts/prepare-ios-resource-probe.py
python3 dev/resource-runtime/build-resources.py --workspace /path/to/workspace \
  --stage-tag my-resource-change
python3 /path/to/workspace/scripts/probe-ios-resource-tools.py \
  --stage artifacts/ios-resource-my-resource-change-stage.json --tag my-resource-change
```

每个 stage/tag 必须使用新名字，以保留旧证据。探测清除宿主及 Darwin 子进程中的 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，串行执行原版工具，并同时核对原生命令状态标记和外层退出码。`ibtoold` 是命令行后台辅助进程；本项目不以桌面或显示服务器为前提。实际资源编译通过前，不把版本查询或框架加载进展记作完成。

独立资源路径尚未整合进原版 xcrun 的整个构建进程树。运行原版 Apple Swift 的 KeyPath 测试需要上述完整候选；它已实际完成三个泛型投影，并复现 marker 协议造成的声明/实际需求条数差异，原始元数据头没有改写。选定共享重建回归的两个输入配置另存于 `config/ios-resource-regression-pins.json`，避免覆盖原候选产物。

`evidence/summary.json` 是本机实际实验的摘要，只有哈希、计数和范围说明；没有包含 Apple 库、SDK、IR、XIP、证书或私钥。开发者应重新运行自己修改所涉及的检查，而不是把摘要当作本机验证结果。

## 应用器的隔离测试

```bash
python3 dev/resource-runtime/tests/test_overlay.py --base /path/to/workspace
```

测试从固定 Git 对象创建临时检出，验证计划、重复应用、回滚、权限及开发修改保护。不运行 Darling、不读取 Apple 输入，也不修改 `--base` 的工作区或索引。
