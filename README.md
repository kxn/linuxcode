# Linuxcode

在 Linux x86_64 上安装隔离的 Darling 和用户提供的原版 Xcode，并管理经过验证的兼容性里程碑。

目前已有**原版 xcodebuild 编译并用原版 codesign 完成 CocoaPod iPhoneOS/arm64 App 的 ad-hoc 签名**的研究里程碑；整合工程的 PATH 入口也已从全新 DerivedData 复现。它使用单独的 CoreServices 诊断策略，尚不是完整 Unity/UE 或开发者证书 CI 环境。本工程把安装、依赖锁定、候选运行入口和开发工具集中起来；完整成功候选的干净机器重建还没有自动化完毕。

游戏工程的后续研究已通过原版 Unity 6 IL2CPP/Bee 生成并独立核对 377 个 iPhoneOS/arm64 静态库对象，并将真实 CocoaPods/AFNetworking 接入完整 workspace；**完整 Unity/UE App 尚未构建成功**。此前的[XPC 后端与资源依赖检查点](dev/resource-runtime/research/xpc-peer-error/README.md)补齐九个后续原版依赖候选，并通过后端单例与 160 项实际错误对象检查；完整 workspace 进入五 target 依赖图和原版资源查询，因缺 CloudKit 通知符号返回 65，尚无 CompileC 或最终 App。前一批 [12 个依赖和严格准备工具](dev/resource-runtime/research/resource-image-preparation/README.md)也已保存。此前的[时钟修正](dev/resource-runtime/research/stable-boottime/README.md)已解决一秒级启动时间跳变。此前的[原始绑定表检查点](dev/resource-runtime/research/native-cache-patch-got/README.md)保留 AppleIDSSO 恢复与初始化超时的历史证据。研究附件没有升级默认安装候选。

此前的[原版 Vision 依赖组检查点](dev/resource-runtime/research/vision-original-dependencies/README.md)恢复九个原始映像，并通过原版 dyld 的九个正例和十八个损坏对照。TextRecognition 的二进制泛型环境边界已根据原始 KeyPath 引用校验；原版 Swift 编译器也复现了相同布局和两次实际 KeyPath 访问。原版资源工具继续推进到 MobileAsset 类缺失，完整游戏 App 仍未构建成功。

此前的[原版 MobileAsset 与 AVFoundation 检查点](dev/resource-runtime/research/mobileasset-avfoundation/README.md)加入六个原始映像，并为没有函数体的原版转发框架增加独立校验路径。资源工具继续推进到 Swift AVFoundation 类型元数据缺失；该后续原版库已有验证候选。完整 workspace 后续重跑进入五 target 依赖图，因同一 Swift 类型缺失返回 65，仍未产出 App；此前一次启动服务查询超时的失败与实时栈也完整保留。

最新的[Storyboard 服务启动与资源目录检查点](dev/resource-runtime/research/coresim-resource-startup/README.md)厘清真机 build 对宿主 CoreSimulator 服务的实际调用，并修复原版 DiskImages2 硬编码 bundle 路径导致的错误描述异常；真实 Storyboard 和最终 Unity App 仍未完成。

此前的[CoreSimulator 磁盘服务检查点](dev/resource-runtime/research/coresim-disk-services/README.md)已进入原版 Swift 磁盘服务初始化，验证真实 DiskArbitration 会话，并补全 Swift 版本比较。实际 Storyboard 和最终 Unity App 仍未完成。

此前的[CoreSimulator 服务与 launchd 任务检查点](dev/resource-runtime/research/unity-coresimulator-services/README.md)已让原版 CoreSimulatorService 进入 main，修复 User XPC 服务注册和 UTF-16 plist，并通过真实任务提交、启动、XPC 往返与移除回归。实际 Storyboard 和最终 Unity App 仍未完成。

此前的[Unity 编译器启动检查点](dev/resource-runtime/research/unity-commpage/README.md)修复了 Linux 初始栈偶尔占住 Darwin commpage 地址导致的 Clang 除零；原先失败的编译已重放成功。UnityFramework 和两个 Pod 静态库也通过原版 codesign 的严格验证。完整 Unity App 仍未完成。

此前的[Unity Data、线程池和 PNG 检查点](dev/resource-runtime/research/unity-data-png-workqueue/README.md)已在实际工作区完整复制2880个资源文件并逐文件比对一致，补齐已复现的线程池信号量竞态；原版 PNG 工具的新环境通过190个像素的独立比较。最终 Unity App 与 Storyboard 输出仍未完成验证。

此前的[Unity 编译与 Unicode 路径检查点](dev/resource-runtime/research/unity-compile-unicode/README.md)已产出并独立核验原版签名的 UnityFramework 与两个 Pod 静态库，58 个编译对象为 iPhoneOS/arm64；完整 App 仍未完成。资源复制的 NFC/NFD 路径问题已在 Darling 源码修复，原版 Swift 遍历 3041 项及 176 项原生路径回归通过。 后续完整重跑暴露的旧等待计时器问题已独立复现，并按 XNU 取消规则修复，39 项公有信号量检查通过。

此前的[系统框架路径检查点](dev/resource-runtime/research/canonical-system-frameworks/README.md)修复 PlugInKit 被当成 Xcode 插件加载的问题，原版 actool / ibtool 版本查询均返回 0。完整 App 与签名仍未验证。

此前的[原版 Automator 类继承检查点](dev/resource-runtime/research/automator-original-class/README.md)恢复 Interface Builder 需要的真实控件继承链及 coder 方法，三组原生检查通过；完整 App 与签名仍未验证。

此前的[原版 AppKit / MapKit / 布局资源检查点](dev/resource-runtime/research/appkit-mapkit-layout/README.md)恢复 Swift Any 命名 binding、七个原始依赖映像及缺失的布局资源。完整 App 和资源编译仍未通过。

此前的[Mach 普通消息 ABI 检查点](dev/resource-runtime/research/mach-msg2-scalar/README.md)实现寄存器消息头与真实 IPC 传输，115 项原生检查及既有 537 项会话回归通过。原版资源工具继续执行后崩溃，最终 App 与签名尚未验证。

此前的[无界面会话与 AppKit 数据检查点](dev/resource-runtime/research/audit-sessions-solarium/README.md)完成 537 项会话原生检查，原版 AppKit 功能查询与只读数据验证通过。完整原版资源工具和 Unity 工程仍单独记录结果，尚未验证最终 App 和完整签名。

此前的[Objective-C 自定义析构检查点](dev/resource-runtime/research/objc-custom-dealloc/README.md)移植苹果开源运行时接口，两种 ISA 各 1,429 项原生检查和五项既有回归通过。原版资源工具随后发生空地址调用，完整 Unity 工程仍无 CompileC 或最终 App。

此前的[EventKit 与 Swift QuartzCore 检查点](dev/resource-runtime/research/eventkit-swift-quartzcore/README.md)恢复三个原版映像，读取真实通知常量，并用原版 Swift 编译器验证 23 项帧率范围行为。完整 Unity/CocoaPods 构建当前停在 `__class_setCustomDeallocInitiation`；仍无 CompileC 或最终 App。

此前的[CommunicationTrust 与 AppleAccount 检查点](dev/resource-runtime/research/communicationtrust-appleaccount/README.md)恢复五个原版映像，验证真实只读 UUID，并用 NSError 和原版 getter 核验实例变量布局。完整 Unity/CocoaPods 构建当前停在 EventKit 通知常量；仍无 CompileC 或最终 App。

此前的[Settings 与 GeoToolbox 检查点](dev/resource-runtime/research/settings-geotoolbox/README.md)恢复 62 个原版映像，核验 Swift 元数据边界和原始导入身份，并以原版 Swift 编译器完成 12 次泛型 KeyPath 读写。完整 Unity/CocoaPods 构建当前停在 `_$s18CommunicationTrust9BlockListCMa`；仍无 CompileC 或最终 App。

此前的[系统脚本存储与 RemoteUI 检查点](dev/resource-runtime/research/script-config-remoteui/README.md)实现真实 16 KB 存储并验证写读、进程隔离及页面保护，恢复三个原版映像并验证同名重导出身份。完整 Unity/CocoaPods 构建当前停在 `_$s8Settings0A8IconViewV5StyleOMa`；仍无 CompileC 或最终 App。

此前的[Swift NaturalLanguage 与 AuthKitUI 检查点](dev/resource-runtime/research/naturallanguage-authkitui/README.md)恢复七个原版映像，核实 25 个整库重导出导入，并验证真实 CFString 常量及错误值对照。完整 Unity/CocoaPods workspace 已越过这些加载缺口，当前停在 JavaScriptCore 所需的系统存储符号；仍无 CompileC 或最终 App。

此前的[原版 NEWLAPACK 检查点](dev/resource-runtime/research/native-newlapack/README.md)恢复原版 LAPACK/BLAS 及 Accelerate/vecLib 转发框架，通过 12 个矩阵的 638 项奇异值分解检查和既有 CPU 回归。完整 Unity/CocoaPods workspace 已越过 NEWLAPACK，当前停在 Swift NaturalLanguage 接口缺失；仍无 CompileC 或最终 App。

此前的[异常初始化与 Stickers 依赖检查点](dev/resource-runtime/research/primary-exception-stickers/README.md)完整重建并验证 libc++abi 的真实异常初始化实现，保留 365 个既有导出，并恢复八个原版框架。完整 Unity/CocoaPods workspace 已越过异常、PowerLog 和 Stickers 缺口，当前停在 NEWLAPACK 数值接口；仍无 CompileC 或最终 App。

此前的[原版 QuickLook 与资源依赖检查点](dev/resource-runtime/research/quicklook-original-dependencies/README.md)恢复 13 个原版映像，核验原始绑定与可执行字节，并补入工具实际使用的弱依赖。完整 Unity/CocoaPods workspace 进入五 target 依赖图，当前停在 C++ 异常初始化接口缺失；仍无 CompileC 或最终 App。

此前的[原版 ApplicationServices 检查点](dev/resource-runtime/research/native-applicationservices/README.md)恢复九个原版映像，保留版本导出与嵌入框架路径，并在 Darling 中核对四个真实 AX 字符串。完整 Unity/CocoaPods 工程已越过本轮依赖缺口，现缺 ViewBridge 的一个类；仍未进入 CompileC 或产出最终 App。

此前的[SIMD 与原版 AppKit 检查点](dev/resource-runtime/research/simd-appkit-singletons/README.md)通过 60 项 SIMD 原生检查，选入原版 AppKit 与九项强依赖，核验 32 个 Swift 单例类，并补回类表外的 4 个。完整 Unity/CocoaPods 工程已越过 AppKit 协议缺失，现停在 ApplicationServices 的 AX 常量；仍无 CompileC 或最终 App。

此前的[原版资源依赖与符号表检查点](dev/resource-runtime/research/accessibility-runtime-inventory/README.md)选入七个原版映像，修复改名符号别名、嵌入 dylib 搜索及纯数据映像恢复。完整 Unity/CocoaPods workspace 正常返回 65，资源工具当前缺少 libSystem 的 double4x4 矩阵常量；尚无 CompileC 或最终 App。

此前的[当前运行输入与 CallHistory 依赖检查点](dev/resource-runtime/research/current-inputs-callhistory/README.md)选用四个原版映像，并将约 22 GB 未使用的祖先副本从启动校验表分离，保留历史哈希及当前库校验。整理前后原版工具日志逐字节一致；后续完整 Unity/CocoaPods workspace 进入五 target 图，因 CoreTelephony 常量缺失返回 65，仍未产出 App。所需原版 CoreTelephony 已有验证候选。

```bash
git clone https://github.com/kxn/linuxcode.git
cd linuxcode
python3 linuxcode.py doctor
python3 linuxcode.py setup --xip /path/to/Xcode_26.6_Universal.xip
```

`setup` 安装基础 Linux/Darling 环境并从 XIP 导入 Xcode。它需要主机具备文档中的依赖，基础 rootfs 安装通过 sudo 完成，Darling 日常执行使用用户命名空间；不安装内核模块。**基础安装完成不等于已经组装出成功构建的兼容性候选。** 当前不会把缺失组件当作安装成功，也不会把原版工具错误改成成功。

已有成功实验工作区时，可以直接接入经过验证的候选，而不用旧的基础入口：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
cd /path/to/experiment/my-project
xcodebuild -workspace MyApp.xcworkspace -scheme MyApp -sdk iphoneos CODE_SIGNING_ALLOWED=NO build
```

原工程与 CI 中的 `xcodebuild` 参数保留。当前工程必须在指定工作区内；显式路径参数会转换到 Darling 可见路径。启动器保留实际工作目录，使用原版 xcodebuild、真实服务与 v2 工具作用域；每次运行保存独立日志并验证原生命令退出码。默认启动预算为 600 秒；长构建可设置 `LINUXCODE_BUILD_TIMEOUT_SECONDS=3600`（1–86,400 秒），无需改 CI 命令。超时会失败。新增入口已实际通过版本查询和全新 DerivedData 的 CocoaPods iOS App 编译、静态库和链接，原生与外层退出均为 0；独立核对产物为 iPhoneOS/arm64，并包含实际 Pod 函数。尚未验证 Unity/UE 导出工程。

安装器已在全新的本地目录从 GitHub 严格核验修正后的 1,080 项清单，并直接从原始 XIP 解压、导入 Xcode；原版 xcodebuild/clang/ld 与 iPhoneOS SDK 元数据逐字节核对通过，重复导入可安全识别已安装状态。候选启动器实际执行 `xcodebuild -version` 已返回 Xcode 26.6 / 17F113，原生和外层退出均为 0；这不代表干净机器已经具备完整候选。

查看安装步骤、输入来源和缺口：

```bash
python3 linuxcode.py recipe
python3 linuxcode.py status
python3 linuxcode.py package --output dist/linuxcode-0.1.0-source.tar.gz
```

公开包只含安装器、开发源码、文档和依赖锁定；不含 Xcode、SDK、Apple 框架、运行前缀、XIP、证书或私钥。离线安装、精确锁定、依赖说明见 [安装文档](docs/install.md)；系统参考输入与冷重建限制见 [运行时输入](docs/runtime-inputs.md)。

研究代码锁定到 [运行时快照 runtime-2026.10.19](https://github.com/kxn/linuxcode/tree/375e52ea83e0f1a8dba3b16a0600d01292a9fe61)，其 `checkpoint/source-manifest.json` 记录了 17 个源码仓库的精确修订和补丁，`checkpoint/evidence/` 保存首次成功 iOS 编译日志与产物检查。后续里程碑应更新锁文件和证据，不追踪随时变化的分支。

开发者可从 [开发环境说明](dev/README.md) 继续工作。新增的 [资源工具源码更新](dev/resource-runtime/README.md) 提供可回滚的源码应用器、67 个锁定映像的重建参数、私有 xcrun 分发、系统库版本回归及可选 ad-hoc codesign 命令候选，仍在本仓库 `main` 维护。它不代表原版资源编译已经完成，也不改变上述安装器的固定编译基线。

最新的 [原版 codesign 源码附件和实测说明](dev/resource-runtime/research/native-codesign/README.md) 提供真实扩展属性支持、原生签名接口兼容和原版分配器入口。已有完整候选时，可通过 `adopt --native-codesign-stage … --identity-store … --build-report … --product-report …` 一次选用它；随后仍使用原来的 `xcodebuild` 命令和工程。此候选不需要 zsign；目前只验证 ad-hoc，尚未验证开发者证书、provisioning 或设备信任。默认不带这些选项的 adopt 继续选择旧的无签名基线。

[原版 CoreGraphics 图像处理实验](dev/resource-runtime/research/native-coregraphics/README.md) 已通过真实位图绘制和原版 ImageIO 的 PNG 像素检查。颜色转换对象创建和 actool/ibtool 仍失败；源码及失败证据作为独立开发附件保存。

[后续资源依赖开发检查点](dev/resource-runtime/research/native-resource-dependencies/README.md) 保存 Swift 泛型环境和 accessible-function 表的解析修复、70 个原版依赖的延迟绑定恢复、原版 SIMD 数值检查及当时缺少 AppleIDSSOAuthentication 的失败证据。CoreVideo CPU 缓冲区仍缺 IOSurface 服务。它没有改变安装基线，也没有宣称资源编译已完成。

[Unity 宿主工具检查点](dev/resource-runtime/research/unity-host-tools/README.md) 保存 Darling 对动态描述符上限的源码修复、原版 IL2CPP/Bee 启动结果，以及 Unity 6 共享内存重映射的实际失败。尚未完成游戏 App 构建。

[Unity 6 共享内存与启动修复](dev/resource-runtime/research/unity-shared-remap/README.md) 已通过原版 IL2CPP/Bee 启动和实际内存共享检查。该检查点记录了 GameAssembly 编译驱动的异步 socket 注册错误；Xcode 的成功横幅与缺失的实际产物被独立区分，尚未完成游戏编译。

[Unity 6 事件注册修复](dev/resource-runtime/research/unity-kqueue-receipts/README.md) 已让原版 IL2CPP 越过 EAGAIN，启动 Bee 和 il2cpp-compile。完整源码库通过事件、共享内存和原版 ad-hoc 签名回归；该检查点当时仍因子进程环境/`uname` 查找失败，尚未生成 GameAssembly。

[Unity 子进程环境与原版 plutil 修复](dev/resource-runtime/research/unity-exec-environment/README.md) 已恢复原版 .NET 环境枚举并补齐绝对路径 plutil，候选通过原版 ad-hoc 签名回归。该检查点记录了 Bee 因客体 `/proc` 判定 Linux 而拒绝 iOS 工具链的旧失败；后续静态库成功及完整 scheme 的范围见[真实 Unity/CocoaPods 工作流](dev/resource-runtime/research/unity-full-app-cocoapods/README.md)和上方最新状态。
