# 资源工具和签名候选的开发源码

本目录在整合仓库的 `main` 维护，向固定的 `runtime-2026.10.19` 源码工作区应用一组可审阅、可回滚的更新。Darling 及其子模块仍在原有 fork 中维护，不新增开发分支或提交身份。

这批代码恢复 67 个明确锁定的原版 Intel 资源映像，补上 Swift KeyPath 二进制泛型环境、缓存合并的 Objective-C 协议引用和类引用表。它是资源工具兼容性的开发材料。**原版 actool/ibtool 尚未完成启动和资源编译**；本次公开候选最新实际缺口是 Sharing 所需的 CoreWiFi.framework。没有完成 Unity/UE、签名或完整冷安装。

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

省略 `--target` 会按 `overlay.json` 中实际验证过的参数重建全部 67 项。每次运行保存新的 `logs/developer-resources-*/` 及结果 JSON，首个失败会停止后续构建。输出在 `runtime/rebuilt-<target>/`，不会安装或选入默认运行根。请在自己的开发工作区迭代；重建会更新该目标的实验产物与报告。

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

资源路径已增加私有 `xcrun` 分发入口：保留全部原始参数；仅执行 `actool`、`ibtool` 时恢复资源路径。SDK 查询和其他工具保留已验证的编译环境，Ruby/OpenSSL 在调用前清除覆盖库路径。这样避免旧 Ruby 的 `rbconfig.rb` 在启动时调用 `xcrun --show-sdk-path`，把资源库带进 SDK 查询进程。

原版 `xcrun` 还通过提供 dyld API 的系统库的最低部署版本推断宿主版本。旧源码库声明 11.0，导致最低要求 14.0 的原版 Clang 被拒绝。新增构建参数将私有源码库的部署元数据与选定的 guest 身份 26.6.2 对齐；实际 API 返回已验证，原版 `xcrun clang --version` 成功。原版工具及其版本检查未修改；编译 SDK 仍是 11，不能据此推断完整 macOS 26 API 已实现。其他版本 API 的一致性仍需完善。

在完整基线已具备时，可构造独立候选并核对实际命令：

```bash
python3 /path/to/workspace/scripts/build-libdyld-source.py \
  --output-dir runtime/dev-libdyld-guest \
  --variant-base runtime/xcode-tool-dispatch-v2-normal/darling-root \
  --report artifacts/dev-libdyld-guest-build.json --minimum-os 26.6.2
python3 /path/to/workspace/scripts/stage-resource-tool-dispatch.py \
  --tag my-dispatch --resource-stage artifacts/ios-resource-my-resource-change-stage.json \
  --libdyld-source-build artifacts/dev-libdyld-guest-build.json
python3 /path/to/workspace/scripts/test-resource-tool-dispatch.py \
  --dispatch-stage artifacts/resource-tool-dispatch-my-dispatch-stage.json --diagnostic
python3 /path/to/workspace/scripts/test-libdyld-guest-identity.py \
  --dispatch-stage artifacts/resource-tool-dispatch-my-dispatch-stage.json --diagnostic
```

构建 libdyld 会在隔离的 Darling 中使用原版链接器，但不会启动图形界面。stage 复制普通与诊断运行根，并检查源库 SHA256、固定 loader ABI 以及选定 SystemVersion；不推广到默认入口。这里 `--diagnostic` 选择现有 CoreServices 诊断策略。第一个测试中的资源工具目前预期仍失败，测试会返回非零并保留真实日志；其余三个命令检查已实际通过。第二个测试还核对真实加载/卸载、八线程 512 次循环、进程映像快照及线程局部存储；它需要先前完整基线生成的生命周期夹具，只有源码检出不能运行它。

`probe-xcode-service-runtime.py` 新增 `--resource-tool-dispatch-stage`，可以在这一候选中运行真实服务、Pod 预处理和原版 Xcode 构建；`verify-ios-cocoapods-product.py` 支持独立产物目录和报告路径。这一新候选已实际从全新 DerivedData 完成 Pod install、C/Objective-C 编译、静态库和 App 链接；原生与外层退出均为 0，独立核对为 iPhoneOS/arm64 并含实际 Pod 函数。`record-resource-tool-dispatch-progress.py` 复核日志、实际状态标记、组件与产物哈希，避免把 shell 跟踪输出当作成功。它们不代表资源编译、Unity/UE 或签名已完成。

运行原版 Apple Swift 的 KeyPath 测试需要上述完整候选；它已实际完成三个泛型投影，并复现 marker 协议造成的声明/实际需求条数差异，原始元数据头没有改写。选定共享重建回归的两个输入配置另存于 `config/ios-resource-regression-pins.json`，避免覆盖原候选产物。

`evidence/summary.json` 是本机实际实验的摘要，只有哈希、计数和范围说明；没有包含 Apple 库、SDK、IR、XIP、证书或私钥。开发者应重新运行自己修改所涉及的检查，而不是把摘要当作本机验证结果。

## Darwin 中的真实签名命令

新增可选的 `codesign` 命令适配器：Darwin shell 保留调用参数，Ruby 解析已支持的签名选项，实际签名交给固定版本的静态 Linux zsign，通过 Darling 原有 ELF exec 路径执行。校验独立检查 Mach-O 页、Info.plist、资源封印以及 XML/DER entitlements；它不使用原版 codesign 前端。原版 xcodebuild 仍未修改。

这一候选只支持 `--sign -` 的 ad-hoc 签名和单个平面、thin 64-bit bundle。entitlements 支持字符串、布尔值、数组和字典；整数、日期、data 类型以及证书身份、嵌套 code、`--deep` 和未知参数均返回错误。尚未实现的功能不会被当作成功。独立 Python 校验器复核实际签名，原生命令测试覆盖四种文件篡改与不支持参数、身份、entitlements 类型的拒绝。

在已具备 CocoaPods 构建基线、原版 Ruby 和锁定 gems 的工作区中运行：

```bash
python3 /path/to/workspace/scripts/build-zsign-linux-static.py \
  --output-dir runtime/zsign-static-dev-v1
python3 /path/to/workspace/scripts/stage-codesign-zsign-runtime.py \
  --tag signing-dev-v1 \
  --dispatch-stage artifacts/resource-tool-dispatch-my-dispatch-stage.json \
  --zsign-build runtime/zsign-static-dev-v1/build.json
python3 /path/to/workspace/scripts/test-codesign-zsign-runtime.py \
  --codesign-stage artifacts/codesign-zsign-signing-dev-v1-stage.json
```

最后一个命令默认使用最初 CocoaPods 编译基线的 App 副本；可用 `--source-app` 指定工作区内的测试 App 路径。测试始终签署私有副本。静态构建需要宿主 OpenSSL/zlib/zstd 开发库和 pkg-config；缺少 zsign 源码时，构建脚本检出 `config/zsign-source.json` 固定的公开提交。它不修改该源码。输出目录和 stage/tag 均须使用新名字。

stage 冻结 Ruby 适配器、已验证的 CFPropertyList 3.0.6/REXML 3.3.9 gem 文件哈希、静态 ELF 后端与专用 namespace 入口。它只在这次 Darling 的挂载视图中绑定 `/usr/bin/codesign`；持久前缀中原有命令的哈希保持不变，默认启动器不受影响。源码包不包含这些 gems、Apple 文件或编译后的签名程序。

`probe-xcode-service-runtime.py` 增加 `--codesign-stage`，可用 `config/ios-cocoapods-zsign-adhoc-build-arguments.json` 复现原版 Xcode 的签名构建尝试。**这条完整流程目前未成功**：原版 Xcode 停在 `GatherProvisioningInputs`，实际堆栈在 `SecItemCopyMatching` 等待配套 `SecurityServer`，尚未执行 CodeSign。`probe-securityd-identity-store.py` 可复现启动包内配套服务并查询不存在的测试标签；服务目前退出，查询不能完成。Darling 的相关 sandbox 初始化入口仍未实现，是后续需要继续定位的模块。命令适配器签署 App 副本成功，不证明这些准备步骤、证书/provisioning、设备信任或 Unity/UE 已完成。

## 应用器的隔离测试

```bash
python3 dev/resource-runtime/tests/test_overlay.py --base /path/to/workspace
```

测试从固定 Git 对象创建临时检出，验证计划、重复应用、回滚、权限及开发修改保护。不运行 Darling、不读取 Apple 输入，也不修改 `--base` 的工作区或索引。

70 映像实验中的 CoreGraphics 源码和 pin 更新另外保存在 [研究附件](research/cg-colorspace-names/README.md)，不由固定的 67 项 overlay 自动应用。该附件记录实际名称 API 测试以及后续 GetType 缺口，供继续开发。
