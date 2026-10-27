# Linuxcode

在 Linux x86_64 上安装隔离的 Darling 和用户提供的原版 Xcode，并管理经过验证的兼容性候选。

**原版 xcodebuild 已成功编译并用原版 codesign 完成真实 Unity/CocoaPods iPhoneOS/arm64 App 的 ad-hoc 签名。** 原版 Storyboard、actool、IL2CPP/Bee 和三个内嵌 Framework 均完成处理；App、三个 Framework、两个 CocoaPods 静态库通过原版严格签名验证，App 的 2,904 项资源通过独立哈希检查。详见[完整 Unity 签名里程碑](dev/resource-runtime/research/unity-signed-app/README.md)。

Unity 授权现可使用原生 Linux CLI：`linuxcode.py unity auth login`，无需在 Darling 中运行 Hub；详见[安装说明](docs/install.md)。当前机器已完成官方登录及 Personal 激活，**全新 Unity 6000.3.27f1 项目已在无图形界面的 Linux 上成功导出 iOS Xcode 工程**（424 个 C++ 文件）；**CocoaPods、原版 Xcode 构建的内外退出码、原版严格验签、独立资源/页面检查和 Pod 符号链接均已通过**。首次编译成功后修复了 Darling 收尾崩溃，恢复验证复用了编译缓存；尚未验证设备安装。详见[完整链路记录](dev/resource-runtime/research/unity-fresh-linux-end-to-end/README.md)。详见[全新 Unity 导出里程碑](dev/resource-runtime/research/unity-fresh-linux-export/README.md)。

新增 RSA P12 导入入口：`import-identity --p12 … --output runtime/my-signing/store.plist --password-env MY_P12_PASSWORD`。P12 导入后的测试身份已完成原版 Unity 构建和七个产物验证；三层链查找、原版 codesign 和独立 CMS 验证也已通过；详见[安装说明](docs/install.md)。

新增：**完整 Unity/CocoaPods 工程已由原版 xcodebuild 调用原版 codesign 完成真实测试证书签名，构建退出码为 0。** App、内嵌 Framework 和静态库共七个产物通过原版严格验证及独立 CMS/页面/资源检查，包含双 CodeDirectory 与篡改拒绝测试。本次复用编译缓存；自签测试明确关闭 profile 要求，尚不代表开发者 provisioning 或设备安装可用。详见[完整 Unity 证书 CI](dev/resource-runtime/research/unity-certificate-ci/README.md)。

最新补充已通过**单次全新 DerivedData 构建**，并确认 Unity 临时缓存入口起初也不存在：58 项 Xcode 编译、完整 IL2CPP 和资源流程成功，374 个 arm64 Unity 归档对象独立核对。修复与证据见[加载器布局和文件事件检查点](dev/resource-runtime/research/loader-layout-and-fsevents/README.md)。

原版 `xcodebuild archive` 已完成真实 [Unity/CocoaPods Release xcarchive 与 dSYM](dev/resource-runtime/research/unity-release-xcarchive/README.md)：iOS arm64 主程序、归档元数据、七项原版/独立验签通过，App 与 UnityFramework 的实际 DWARF 数据和 UUID 对应关系通过核对。已修复归档中的 fork 子进程队列锁；较早 [Debug 归档](dev/resource-runtime/research/unity-original-xcarchive/README.md) 的空 dSYMs 记录保留，export 仍单独推进。

成功候选来自已有研究工作区，使用单独的 CoreServices 诊断策略。样例保留明确记录的两行 AFNetworking SDK 兼容修改，Xcode 工程与 CocoaPods 配置未修改。尚未验证开发者证书、描述文件、真机安装、UE 或任意工程，也尚未实现从干净 Linux/XIP 自动重建这套完整候选。基础安装器和较早的默认候选保留；使用成功的 Unity 候选需要显式选择下述里程碑。

此前各阶段的源码、失败记录和验证见[开发研究索引](dev/resource-runtime/README.md)。历史附件描述的是当时的状态。

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

原工程与 CI 中的 `xcodebuild` 参数保留。当前工程必须在指定工作区内；显式路径参数会转换到 Darling 可见路径。启动器保留实际工作目录，使用原版 xcodebuild、真实服务与 v2 工具作用域；每次运行保存独立日志并验证原生命令退出码。默认启动预算为 600 秒；长构建可设置 `LINUXCODE_BUILD_TIMEOUT_SECONDS=3600`（1–86,400 秒），无需改 CI 命令。超时会失败。新增入口已实际通过版本查询和全新 DerivedData 的 CocoaPods iOS App 编译、静态库和链接，原生与外层退出均为 0；独立核对产物为 iPhoneOS/arm64，并包含实际 Pod 函数。这一较早的默认候选未用于完整 Unity 工程；Unity 成功候选需要下面的显式选择。

接入已经组装好的 Unity 成功候选：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt \
  --engine-milestone artifacts/unity-original-fresh-signed-app-v1.json
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
```

此后在工程目录运行原来的 `xcodebuild` 命令。该入口使用里程碑记录的运行库、工具环境和服务准备步骤，并检查原生命令的实际退出码。它需要对应的研究工作区和本地产物，不能用于把一个基础 XIP 安装直接当作完整成功候选。

已有完整证书候选时，可指定自己的只读身份库接入同一个 PATH 入口：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt \
  --certificate-candidate config/native-certificate-candidate-v9.json \
  --identity-store runtime/my-signing/store.plist
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
```

证书入口按本次身份库启动 SecurityServer/trustd，保留 CI 的 `xcodebuild` 参数；不会自动换证书、关闭 profile 要求或注入测试工程。身份库当前使用只读 RSA PKCS1 DER 格式，详情见[安装与证书入口](docs/install.md#证书签名入口)。证书签名链路已验证，Apple 开发者 provisioning、设备信任与任意钥匙串操作仍未验证。

安装器已在全新的本地目录从 GitHub 严格核验修正后的 1,080 项清单，并直接从原始 XIP 解压、导入 Xcode；原版 xcodebuild/clang/ld 与 iPhoneOS SDK 元数据逐字节核对通过，重复导入可安全识别已安装状态。候选启动器实际执行 `xcodebuild -version` 已返回 Xcode 26.6 / 17F113，原生和外层退出均为 0；这不代表干净机器已经具备完整候选。

查看安装步骤、输入来源和缺口：

```bash
python3 linuxcode.py recipe
python3 linuxcode.py status
python3 linuxcode.py package --output dist/linuxcode-0.1.0-source.tar.gz
```

默认包保留安装器、开发源码和文档，省略体积较大的历史诊断附件；需要完整历史时添加 `package --include-research-history`。公开包只含安装器、开发源码、文档和依赖锁定；不含 Xcode、SDK、Apple 框架、运行前缀、XIP、证书或私钥。离线安装、精确锁定、依赖说明见 [安装文档](docs/install.md)；系统参考输入与冷重建限制见 [运行时输入](docs/runtime-inputs.md)。

以下说明保留固定安装基线与历史检查点的当时状态；最新 Unity 候选见本文开头。

研究代码锁定到 [运行时快照 runtime-2026.10.19](https://github.com/kxn/linuxcode/tree/375e52ea83e0f1a8dba3b16a0600d01292a9fe61)，其 `checkpoint/source-manifest.json` 记录了 17 个源码仓库的精确修订和补丁，`checkpoint/evidence/` 保存首次成功 iOS 编译日志与产物检查。后续里程碑应更新锁文件和证据，不追踪随时变化的分支。

开发者可从 [开发环境说明](dev/README.md) 继续工作。新增的 [资源工具源码更新](dev/resource-runtime/README.md) 提供可回滚的源码应用器、67 个锁定映像的重建参数、私有 xcrun 分发、系统库版本回归及可选 ad-hoc codesign 命令候选，仍在本仓库 `main` 维护。它不代表原版资源编译已经完成，也不改变上述安装器的固定编译基线。

最新的 [原版 codesign 源码附件和实测说明](dev/resource-runtime/research/native-codesign/README.md) 提供真实扩展属性支持、原生签名接口兼容和原版分配器入口。已有完整候选时，可通过 `adopt --native-codesign-stage … --identity-store … --build-report … --product-report …` 一次选用它；随后仍使用原来的 `xcodebuild` 命令和工程。此候选不需要 zsign；目前只验证 ad-hoc，尚未验证开发者证书、provisioning 或设备信任。默认不带这些选项的 adopt 继续选择旧的无签名基线。

[原版 CoreGraphics 图像处理实验](dev/resource-runtime/research/native-coregraphics/README.md) 已通过真实位图绘制和原版 ImageIO 的 PNG 像素检查。颜色转换对象创建和 actool/ibtool 仍失败；源码及失败证据作为独立开发附件保存。

[后续资源依赖开发检查点](dev/resource-runtime/research/native-resource-dependencies/README.md) 保存 Swift 泛型环境和 accessible-function 表的解析修复、70 个原版依赖的延迟绑定恢复、原版 SIMD 数值检查及当时缺少 AppleIDSSOAuthentication 的失败证据。CoreVideo CPU 缓冲区仍缺 IOSurface 服务。它没有改变安装基线，也没有宣称资源编译已完成。

[Unity 宿主工具检查点](dev/resource-runtime/research/unity-host-tools/README.md) 保存 Darling 对动态描述符上限的源码修复、原版 IL2CPP/Bee 启动结果，以及 Unity 6 共享内存重映射的实际失败。尚未完成游戏 App 构建。

[Unity 6 共享内存与启动修复](dev/resource-runtime/research/unity-shared-remap/README.md) 已通过原版 IL2CPP/Bee 启动和实际内存共享检查。该检查点记录了 GameAssembly 编译驱动的异步 socket 注册错误；Xcode 的成功横幅与缺失的实际产物被独立区分，尚未完成游戏编译。

[Unity 6 事件注册修复](dev/resource-runtime/research/unity-kqueue-receipts/README.md) 已让原版 IL2CPP 越过 EAGAIN，启动 Bee 和 il2cpp-compile。完整源码库通过事件、共享内存和原版 ad-hoc 签名回归；该检查点当时仍因子进程环境/`uname` 查找失败，尚未生成 GameAssembly。

[Unity 子进程环境与原版 plutil 修复](dev/resource-runtime/research/unity-exec-environment/README.md) 已恢复原版 .NET 环境枚举并补齐绝对路径 plutil，候选通过原版 ad-hoc 签名回归。该检查点记录了 Bee 因客体 `/proc` 判定 Linux 而拒绝 iOS 工具链的旧失败；后续静态库成功及完整 scheme 的范围见[真实 Unity/CocoaPods 工作流](dev/resource-runtime/research/unity-full-app-cocoapods/README.md)和上方最新状态。
