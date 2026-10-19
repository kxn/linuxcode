# Linuxcode

在 Linux x86_64 上安装隔离的 Darling 和用户提供的原版 Xcode，并管理经过验证的兼容性里程碑。

目前已经有**原版 xcodebuild 编译带 CocoaPod 的 iPhoneOS/arm64 App 成功**的研究里程碑；签名关闭，使用了单独的 CoreServices 诊断策略。这不是完整 Unity/UE CI 环境。本工程把安装、依赖锁定、候选运行入口和开发工具集中起来；完整成功候选的干净机器重建还没有自动化完毕。

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

公开包只含安装器、文档和依赖锁定；不含 Xcode、SDK、Apple 框架、运行前缀、XIP、证书或私钥。离线安装、精确锁定、依赖说明见 [安装文档](docs/install.md)；系统参考输入与冷重建限制见 [运行时输入](docs/runtime-inputs.md)。

研究代码锁定到 [运行时快照 runtime-2026.10.19](https://github.com/kxn/linuxcode/tree/375e52ea83e0f1a8dba3b16a0600d01292a9fe61)，其 `checkpoint/source-manifest.json` 记录了 17 个源码仓库的精确修订和补丁，`checkpoint/evidence/` 保存首次成功 iOS 编译日志与产物检查。后续里程碑应更新锁文件和证据，不追踪随时变化的分支。

开发者可从 [开发环境说明](dev/README.md) 继续工作。新增的 [资源工具源码更新](dev/resource-runtime/README.md) 提供可回滚的源码应用器、67 个锁定映像的重建参数、私有 xcrun 分发、系统库版本回归及可选 ad-hoc codesign 命令候选，仍在本仓库 `main` 维护。它不代表原版资源编译已经完成，也不改变上述安装器的固定编译基线。
