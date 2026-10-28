# 资源工具和签名候选的开发源码

较新 stage104/106、UE CocoaPods 和原版 Unity 证明的选择与复现边界见[研究源码核验和审阅指南](../research-sources.md)。独立工具可从默认 source 包验 SHA、比较文件并导出到新审阅目录；本页下方的固定 overlay 不会自动装配这些后续运行候选。

最新里程碑：[原版 xcodebuild 完整编译并签名 Unity/CocoaPods App](research/unity-signed-app/README.md)。原版严格验证及独立资源、代码页检查均通过；整合入口新增显式 engine milestone 选择。下列早期附件及固定 overlay 的缺口描述保留当时状态，不代表最新候选。冷重建、开发者证书和真机验证仍未完成。

[Contacts 原版依赖组附件](research/contacts-original-dependencies/README.md) 保存九个原版映像、保留明确准备选项的批量工具及单会话原版 dyld 正/负例验证。原始指令/绑定检查和真实 Unity/CocoaPods 构建已继续推进到 Vision 类缺失，完整 App 仍未生成；默认安装候选没有提升。

[AVFAudio 转导出与符号表修复附件](research/avfaudio-reexport-symbol-tables/README.md) 保存原版 AVFAudio 和 AudioSession 的真实对象/CFString 对照，并修复提取件追加转导出别名未计入动态符号表的问题。原版 dyld 校验、独立分组/索引检查及真实 Unity/CocoaPods 构建已越过此前缺口，当前缺 Contacts 类；完整 App 仍未生成。

[完整 libc++ 后端与字符转换附件](research/codecvt-char8-backend/README.md) 以未修改的 38 个源码单元启用 C++20 facet 和 locale 安装，用原版链接器保留全部旧导出属性，并通过全部 Unicode 标量及既有消费者的原生回归。原版 UserNotifications 候选和完整 Unity/CocoaPods 构建已继续推进到 AVFAudio 转导出缺口；完整 App 仍未生成。

[PMR 类型 ABI 与 AudioToolbox 附件](research/pmr-runtime-abi/README.md) 保存真实标准 PMR key function、跨 DSO 分配/异常/析构回归及零长度 weak-bind 修复，并保留原版 AudioToolbox 指令与绑定。实际工具已越过这两处缺失，当前缺口为 C++20 char8_t locale facet；完整 Unity/UE App 和默认安装提升仍未完成。

[完整 Unity/CocoaPods 构建附件](research/unity-full-app-cocoapods/README.md) 提供原始工程与真实 AFNetworking 的准备/安装入口，并修复资源工具直接调用的环境选择；实际完整 App 构建仍因 AppleIDSSOAuthentication 缺失而失败。

[Unity 私有 procfs 与文件复制附件](research/unity-private-procfs/README.md) 保存原版 Bee 平台识别、完整源码运行候选和稀疏复制数据丢失的修复，附真实 Unity GameAssembly 构建和独立产物检查。它需要此前完整研究基线；完整 App 和资源链仍未完成。

本目录在整合仓库的 `main` 维护，向固定的 `runtime-2026.10.19` 源码工作区应用一组可审阅、可回滚的更新。Darling 及其子模块仍在原有 fork 中维护，不新增开发分支或提交身份。

这批固定 overlay 恢复 67 个明确锁定的原版 Intel 资源映像，补上 Swift KeyPath 二进制泛型环境、缓存合并的 Objective-C 协议引用和类引用表。它是资源工具兼容性的开发材料。**原版 actool/ibtool 尚未完成启动和资源编译**；固定 67 镜像候选仍缺 Sharing 所需的 CoreWiFi.framework。后续独立附件已经验证原版 ad-hoc 签名及 CPU 图像处理，Unity/UE 和完整冷安装仍未完成。

[原版 CoreGraphics 附件](research/native-coregraphics/README.md) 保存真实位图绘制、原版 PNG 解码和字体链的进展。CPU 图像测试不需要图形界面；颜色转换对象创建仍失败。[后续依赖检查点](research/native-resource-dependencies/README.md) 保存原版依赖的延迟绑定和 Swift accessible-function 表修复，最新工具实验缺 AppleIDSSOAuthentication；实际 CoreVideo CPU 测试因 IOSurface 内核服务不可用而断言退出。这些附件没有自动加入固定 overlay 或已成功的原版签名候选。

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

后续[原始绑定表与代码字节恢复实验](research/native-cache-patch-got/README.md)保存 AppleIDSSO 的保留指令字节模式、七个原始资源依赖候选及独立检查，以及当时缺 BiomeStreams、完整构建超时的历史证据。[稳定时钟与资源依赖检查点](research/stable-boottime/README.md)修复一秒级时钟倒退，最新完整 Unity workspace 已到达实际资源查询并返回 65，后续直接工具探测当时仍缺 InternationalTextSearch。后续的[资源映像准备与依赖推进](research/resource-image-preparation/README.md)补齐 12 个原版依赖候选，新增严格准备与原始导出审计脚本。最新 [XPC 后端错误单例与资源依赖](research/xpc-peer-error/README.md)又追加九个候选，修复实际初始化循环并验证一个共享后端对象和 160 项错误对象行为；完整 Unity workspace 再次到达真实资源查询，现因缺 CloudKit 通知符号返回 65，尚无 CompileC 或最终产物。尚未完成真实资源编译；固定 overlay 和默认安装候选没有提升。

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

`probe-xcode-service-runtime.py` 增加 `--codesign-stage`，可用 `config/ios-cocoapods-zsign-adhoc-build-arguments.json` 复现原版 Xcode 的签名构建尝试。**该固定候选的首次完整尝试未成功**：当时原版 Xcode 停在 `GatherProvisioningInputs`，实际堆栈在 `SecItemCopyMatching` 等待配套 `SecurityServer`，尚未执行 CodeSign。`probe-securityd-identity-store.py` 可复现启动包内配套服务并查询不存在的测试标签；服务目前退出，查询不能完成。实际选定的 sandbox 初始化返回 Invalid argument；尚未确认失败位于 profile 编译还是策略应用，不能归因于未确认调用的源码占位入口。命令适配器签署 App 副本成功，不证明这些准备步骤、证书/provisioning、设备信任或 Unity/UE 已完成。

## 应用器的隔离测试

```bash
python3 dev/resource-runtime/tests/test_overlay.py --base /path/to/workspace
```

测试从固定 Git 对象创建临时检出，验证计划、重复应用、回滚、权限及开发修改保护。不运行 Darling、不读取 Apple 输入，也不修改 `--base` 的工作区或索引。

70 映像实验中的 CoreGraphics 源码和 pin 更新另外保存在 [研究附件](research/cg-colorspace-names/README.md)，不由固定的 67 项 overlay 自动应用。该附件记录实际名称 API 测试以及后续 GetType 缺口，供继续开发。

本地原生身份查询的后续源码和证据见 [身份存储实验](research/local-identity-store/README.md)。该实验已使原版 Xcode 构建越过 GatherProvisioningInputs；补齐 derq 后进入了 CodeSign，当前因静态库签名尚未支持而失败。完整 App 签名仍在验证。

原版签名的后续里程碑已完成原版 Xcode 的三个 CodeSign 任务及 PATH 入口全新构建，详见 [原版 codesign 附件](research/native-codesign/README.md)。该可选候选不使用 zsign，仍仅验证简单 CocoaPods App 的 ad-hoc 签名。

[Unity 宿主工具检查点](research/unity-host-tools/README.md) 保存 Darling 对动态描述符上限的源码修复、原版 IL2CPP/Bee 启动结果，以及 Unity 6 共享内存重映射的实际失败。尚未完成游戏 App 构建。

[Unity 6 共享内存与启动修复](research/unity-shared-remap/README.md) 已通过原版 IL2CPP/Bee 启动和实际内存共享检查。该检查点记录了 GameAssembly 编译驱动的异步 socket 注册错误；Xcode 的成功横幅与缺失的实际产物被独立区分，尚未完成游戏编译。

[Unity 6 事件注册修复](research/unity-kqueue-receipts/README.md) 已让原版 IL2CPP 越过 EAGAIN，启动 Bee 和 il2cpp-compile。完整源码库通过事件、共享内存和原版 ad-hoc 签名回归；当前编译仍因子进程环境/`uname` 查找失败，实际 GameAssembly 产物尚未生成。

[Unity 子进程环境与原版 plutil 修复](research/unity-exec-environment/README.md) 已恢复原版 .NET 环境枚举并补齐绝对路径 plutil，新的候选通过原版 ad-hoc 签名回归。最新构建在 Bee 因客体 `/proc` 判定 Linux 后拒绝 iOS 工具链，GameAssembly 仍未生成；包含源码、实际失败证据和后续定位。

最新研究附件：[ScreenTime 依赖与 Swift 原指令保留](research/screentime-patch-got/README.md)，包含 33 个候选、批量准备/staging、实际二进制校验和完整 workspace 的失败证据；默认安装候选未升级。

最新研究附件：[Telephony、原始弱引用与 KeyPath 环境](research/telephony-weak-imports/README.md)，包含 26 个候选、实际弱/强链接矩阵、原指令与 NULL 槽位校验，以及完整 workspace 的失败证据；默认安装候选未升级。

[CMCapture 与转导出检查点](research/cmcapture-reexports/README.md) 保存 42 个原版依赖候选、显式导出链审计、原子准备清单和嵌套 framework 路径修复。真实构建与资源工具结果及未完成范围见该附件的 evidence.json；默认安装候选没有提升。

[AuthKit / Security 与缓存 ABI 检查点](research/authkit-security-abi/README.md) 保存八个保留原始指令的候选、原生 Security TLS / 类身份验证、URLFormatting 类别方法表恢复与候选发布写入锁。完整 Unity workspace 仍因 LocalAuthentication 的 LAUserStore 缺失而返回 65；默认安装环境未提升。

[原版认证、目录与媒体依赖加载](research/local-auth-resource-loader/README.md) 保存 14 个保留原始指令的候选、嵌套 framework 搜索路径修正、原始跳转桩缺口诊断和损坏副本对照。资源工具已继续到 SkyLight 的 ProDisplayLibrary Swift 类型依赖；完整 Unity/UE 构建签名仍未完成，默认安装候选未提升。

[原始 GOT 身份与 dispatch 类型](research/pooled-got-dispatch/README.md) 保存 `_scalbn` 原始符号校验、六个原版候选、完整 libdispatch 源码类型移植，以及避免旧兄弟库被一起选入的原生对照。最新完整 Unity workspace 返回 65，缺少 caulk 所需的 C++17 pmr 类型信息；尚无 CompileC 或最终 App，默认安装环境未提升。
# 最新 Intel 模拟器加载进展

[版本集合与真实签名登记](research/simulator-dyld-registration/README.md) 保存现代版本判断、Apple CMS/代码页校验、描述符 RPC 及 Darling 加载器静态入口更新。原生动态与启动入口测试通过；原版 Storyboard 已越过签名登记报错，仍因模拟器子进程启动失败返回 255，最终 Unity App 尚未完成。默认安装候选未提升。

[后续动态库签名与宿主接口](research/simulator-dylib-signatures/README.md) 已让原版模拟器加载器运行 IBAgent-iOS 并装载 iOS QuartzCore、Foundation、libdispatch。包含 Developer ID/ad-hoc 与平台身份的分离、原版 codesign 重签私有兼容库、真实 voucher 权利清理及上游 pthread 别名。最新缺口为 mach_eventlink 用户态接线；完整 Storyboard/App 仍未生成。

[真实 Mach eventlink 后续](research/native-mach-eventlink/README.md) 已补齐四个 MIG 与三种64位信号/等待调用，实际计数、超时、跨线程交接和销毁测试通过。原版流程继续到 work interval 调度元数据接口，完整资源编译仍未完成。

[工作区间实例后续](research/work-interval-instances/README.md) 补齐16个真实载荷和方法，单元及原生错误传播检查通过；性能控制内核后端仍未实现。原版流程继续到 cooperative workqueue 接口，完整资源/App 仍未完成。

[协作工作线程后续](research/cooperative-workqueue/README.md) 完整 pthread 源码构建保留194个旧导出，256次新旧请求与9216个GCD任务通过。原版 ibtool 继续到工作组回调注册接口，完整资源/App仍未完成。

[模拟器工作组、平台与目录节点操作](research/simulator-workgroup-platform-nodeat/README.md) 复用 Apple 开源实现，完整重建 pthread/platform，54万多项内存边界检查、实际 FIFO 字节读写及GCD回收通过；原版流程推进到 openat_authenticated_np，完整资源/App仍未完成。

[数据保护文件接口后续](research/authenticated-open-interface/README.md) 原生普通I/O与七参数ABI通过，未实现认证明确报错；原版流程进入Skywalk channel组，完整资源/App仍未完成。

[完整Skywalk客户端后续](research/skywalk-channel-client/README.md) 复用2369行Apple开源客户端及Intel校验和，实际属性/克隆和16400组复制校验通过；先前14个名字缺口已补齐。原版资源编译仍以255退出，正在定位初始化，完整App尚未完成。

[原版首次初始化回调与桥接](research/libkernel-init-v5-bridge/README.md) 修复version5公共表与Darling私有扩展冲突，实际桥接恢复、保护页和4个子进程检查通过；原版进入ObjC镜像注册，仍在定位选择器锁，完整App未完成。

- [Original iOS lock provider repair](research/internal-futex-lock-providers/README.md): remove empty kernel lock exports, verify real unlocks and native contention; next original dispatch workqueue capability assertion.

- [Direct event workqueues and embedded Linux backend](research/direct-kevent-workqueues/README.md): real pipe/Mach callbacks, auxiliary buffers, large-message retry and GCD; original iOS now reaches the missing kevent_id workloop backend.

- [Workloop event domains and original task voucher diagnosis](research/workloop-event-domains/README.md): distinct real callback domains, exact original Mach flags and large-message retries; original iOS now reaches missing Bank voucher support.

- [Native Bank voucher creation and process identity](research/native-bank-vouchers/README.md): real ports, thread ownership, copies and cross-process account identity/UUID checks; original IBAgent advances to its next event request.

- [Async workloop requests and exact queue-state debounce](research/workloop-async-requests/README.md): real serial callbacks,200 coalesced updates,pending cancellation and affected Mach regression; original iOS advances to a mach_msg2 options mismatch.

- [Original Mach message vectors](research/mach-msg2-vectors/README.md):497 vector checks plus115 scalar checks; original IBAgent reaches main and UIKit screen/resource initialization.

- [Server-wide original activity IDs](research/mach-activity-ids/README.md):8 threads and2 exec children reserve6531 nonoverlapping IDs; original UIKit initialization advances to actual auxiliary message bytes.

- [Real auxiliary message bytes and timer preallocation](research/mach-msg2-auxiliary/README.md):cross-process payloads,retained retries and3966 message checks plus real timers; original IBAgent reaches its message channel and main-queue synchronization.

- [Original Unity Storyboard compilation](research/original-storyboard-ulock/README.md): original ibtool and IBAgent pass twice, with matching NIB hashes and entry mapping; real ulock waiter counts and error handling tested. Full App remains in progress.

- [Process-event notification and subscription ordering](research/process-event-channel/README.md): 64 real queued exit/update cycles and disable/re-enable retention; one kernel source unit recompiled, 906 reused.

- [Receive-message flag translation](research/recvfrom-message-flags/README.md): live syscall exposes Darwin/Linux MSG_DONTWAIT mismatch; independent old-stage timeout and fixed-stage immediate EAGAIN, peek and real process events.

- [Unity Storyboards and main executable link](research/unity-storyboards-and-main-link/README.md): original full build compiles/links both Storyboards and arm64 Unity main; actool remains the resource blocker, so final App signing is not claimed.

- [Real synchronous workloop waits](research/workloop-sync-waiters/README.md): actual asset-agent first fault,96 blocking waits and32 delete/reuse rounds; affected async queue regression also passes.

- [Asynchronous XPC connection lifetime](research/xpc-async-reply-lifetime/README.md):32 delayed replies,32 cancellations and64 exactly-once finalizers after caller release; original asset task retry continues.

- [Workloop owner discovery and handoff](research/workloop-owner-handoff/README.md): actual Mach thread validation, parked delivery and stale-END resume; wrong-port null-target server failure corrected and native checks pass.

- [Ownership release and repeated assurance](research/workloop-owner-release/README.md): valid delete/enable precedence and repeat wake/discovery match original dispatch; previous duplicate-wake expectation corrected with native evidence.

- [Original Unity asset catalog compilation and dispatch2 lifecycle](research/dispatch2-assetcatalog/README.md): original actool produces Assets.car; native tagged cancellation and vnode close/reuse checks pass.

- [NULL exec/spawn environment and original bitcode_strip](research/null-exec-environment/README.md): captures the real SwiftBuild pre-exec crash, verifies empty/inherited environments and original framework-tool output.

- [加载器布局、内部文件事件与全新构建](research/loader-layout-and-fsevents/README.md)：处理真实编译器启动冲突，隔离日志持久化自通知，并验证单次从空 DerivedData 完成 Unity/CocoaPods 构建。

[Native identity leaf policy](research/local-identity-leaf-policy/README.md):23 native checks pass; original certificate codesign reaches chain construction, whose headless trust service is still being completed.

[launchctl long UTF-8 strings](research/launchctl-long-strings/README.md):39 native checks; fixes truncated job environment and starts paired headless trust services.

[Local certificate parents](research/local-certificate-parent-candidates/README.md):27 native checks and actual recoverable self-signed trust result; CMS legacy module dependency remains under investigation.

[Original CMS and SecurityServer](research/original-cms-securityserver/README.md):coherent old/new backends reach the same module-service dependency; paired securityd startup is stopped by its unimplemented native prerequisite.

[Source SecurityServer and original certificate CMS](research/native-securityd-certificate-cms/README.md):159 translation units; original native CMS signature independently verifies and rejects tampering. App signing continues through the upstream requirement-parser bundle.

[Original certificate-signed iOS App](research/original-certificate-signed-app/README.md):original codesign sign/strict verification and independent CMS/code/resource checks pass; full Unity certificate CI and provisioning remain open.
