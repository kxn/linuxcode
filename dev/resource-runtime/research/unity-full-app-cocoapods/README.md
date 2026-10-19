# Unity 完整 App / CocoaPods 构建入口：资源链仍未完成

本附件把已经验证的 Unity iPhoneOS 静态库流程接到完整 App scheme，并修复 Xcode 直接执行资源工具时丢失独立库环境的问题。实际完整构建返回 65，停止于原版资源工具缺少 AppleIDSSOAuthentication。**尚未生成或签名完整 Unity App，AFNetworking 也尚未进入实际源文件编译。**

## 真实工程与依赖

准备器按固定提交导出 uEmuera 的原始 Unity 6000.0.19f1 iOS 工程，不读取或改写原检出中的开发修改。它按原 Git LFS 的 SHA256 与长度补齐约 218 MB 的真实 libiPhone-lib.a，再加入固定提交的 AFNetworking 4.0.1 原始源码和 podspec。

安装使用 Darling 内的真实 CocoaPods。依赖通过 `:path` 指向按固定提交下载的原始 AFNetworking，避免把构建测试依赖于变化中的 Specs/CDN。真实安装生成了 Podfile.lock、Pods 工程和 Unity-iPhone.xcworkspace。Ruby/xcodeproj 对照确认原有四个 target 的 UUID、产品类型、源文件引用及每个原始构建脚本内容保持一致；原文件中只有 CocoaPods 正常修改的 PBX 元数据变化，LFS 文件按原 OID 实体化。

完整原版 xcodebuild 已解析五个 target：Unity-iPhone、UnityFramework、GameAssembly、Pods-UnityFramework、AFNetworking，并确认 `-lAFNetworking` 链接依赖。第一次准备命令同时使用 `-arch` 和通用 destination，被 Xcode 拒绝；后续使用 `ARCHS=arm64` 构建设置，失败记录保留。Podfile 目前只声明 UnityFramework，CocoaPods 对未声明 host target 有警告；原工程的 Unity-iPhone 已依赖并嵌入 UnityFramework，最终配方仍需清理 host 声明。

## 直接执行资源工具

旧 xcrun 包装器只覆盖经过 xcrun 的调用。Swift Build 在生成完整 App 构建描述时直接执行原始 actool/ibtool 绝对路径做版本查询，最初在缺失 CoreSVG 处失败。

新增的 libsystem_kernel 源码支持显式启用的 Mach-O 子进程环境范围：`DARLING_DYLD_OVERRIDE_EXECUTABLES` 是以冒号分隔的精确绝对路径列表，两个对应的 FRAMEWORK_PATH/LIBRARY_PATH 值只用于匹配工具的子进程。父进程、输入环境缓冲区和其他可执行文件保持原值。没有修改 Apple 工具，也没有替换资源编译结果。

同一原生回归在旧内核库中失败，在完整 879 单元的新库中通过九个子进程检查：fork/exec、posix_spawn、相似路径不匹配、UTF-8/空格、缺省项、合法空值和真实 ENOENT。原有十四次连续 exec 的回归也通过。

资源侧完整源码 libSystem/libkqueue 还合并了原版图形候选需要的 17 个额外导出。20 个源码单元对应的指令保留，46 个本地导出和 75 个命名重导出共 121 项；独立检查确认原有类型、符号及提供库不变。只有资源工具选择这个 System，调用方继续使用其已验证的完整队列库。

最终真实 Unity workspace 的 actool/ibtool 调用已经加载到最新资源框架候选，并在原版 FamilyCircle 要求 AppleIDSSOAuthentication 时退出。这证明直接执行的环境选择已生效；不代表工具版本查询或资源编译成功。证据与明确的失败状态见 evidence.json。

## 已有开发工作区复现

依赖先前 private-procfs、CoreGraphics v40、lazy resource closure 等完整研究基线及其本地原始输入。先按 reference/source-revisions.json 检出组件，再审阅并合并 payload 到对应源码路径。构建源码候选的方法沿用前一附件；本附件替换 execve.c、源码链接器和 Xcode 探针，新增工程准备、CocoaPods 检查和配置生成入口。

```bash
python3 scripts/prepare-unity-ios-cocoapods.py --tag NEW
python3 scripts/install-unity-ios-cocoapods.py \
  --project-report artifacts/unity-ios-cocoapods-NEW-project.json \
  --stage artifacts/private-procfs-PREVIOUS-stage.json

python3 scripts/build-libsystem-kernel-source.py \
  --source-manifest /path/to/this-attachment/reference/source-revisions.json \
  --output-dir runtime/direct-tool-environment-kernel-NEW \
  --variant-base runtime/original-host-tools-PREVIOUS/darling-root \
  --report artifacts/direct-tool-environment-kernel-NEW-build.json
python3 scripts/stage-private-procfs-runtime.py \
  --parent-stage artifacts/original-host-tools-PREVIOUS-stage.json \
  --server-build runtime/shared-remap-server-PREVIOUS/stage.json \
  --kernel-build artifacts/direct-tool-environment-kernel-NEW-build.json \
  --libsystem-build runtime/libsystem-kqueue-source-PREVIOUS/build.json --tag NEW
python3 scripts/test-direct-tool-environment.py --stage artifacts/private-procfs-NEW-stage.json
python3 scripts/test-exec-environment.py \
  --runtime-profile scripts/private-procfs-runtime-profile.py --stage artifacts/private-procfs-NEW-stage.json

python3 scripts/link-libsystem-kqueue-source.py \
  --objects runtime/libsystem-kqueue-source-PREVIOUS/objects.json --tag resourceNEW \
  --template runtime/coregraphics-native-v40/libraries/libSystem.B.dylib \
  --runtime-profile scripts/coregraphics-native-security-profile.py \
  --profile-arguments-file config/resource-libsystem-providers-v1.json
python3 scripts/stage-direct-resource-environment.py \
  --runtime-stage artifacts/private-procfs-NEW-stage.json \
  --resource-stage artifacts/ios-resource-lazy-v1-stage.json \
  --graphics-stage artifacts/coregraphics-native-v40-stage.json \
  --libsystem-build runtime/libsystem-kqueue-source-PREVIOUS/resourceNEW/build.json \
  --output artifacts/direct-resource-tool-environment-NEW.json
```

NEW/PREVIOUS 必须替换为实际输出。准备器写入新工程目录，安装器拒绝覆盖已经集成的工程，环境描述生成器核对输入哈希和 profile 后才发布文件，不启动 Darling。生成器输出与本次实际构建使用的配置逐项一致。新回归与已存在失败证据均保留，Darling 执行继续由 session.lock 串行化。

Xcode 探针在前一附件的完整命令上增加：

```bash
--private-procfs-stage artifacts/private-procfs-NEW-stage.json \
--direct-resource-environment artifacts/direct-resource-tool-environment-NEW.json \
--xcode-arguments-file config/unity-ios-cocoapods-v3-build-arguments.json
```

参数文件展示实际 workspace/scheme、iPhoneOS、Debug、通用 iOS destination 和 ad-hoc 签名设置。复现新工程时应将其中 v1 工程路径改为准备器输出，派生数据路径使用新目录。原始 CI 仍调用 xcodebuild，资源环境由 Darling 执行层选择。

完整 App、资源输出、App/Framework/Pod 实际链接、原版签名、证书/provisioning、archive/export、UE、稳定性与从零安装仍未完成。此前的一次 server 信号量 panic 也尚未修复。公开包只含源码、配置和证据摘要，未包含 Apple/Unity 二进制、SDK、证书、私钥或此次编译产物。
