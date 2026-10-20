# 原版资源工具的异常初始化与 Stickers 依赖

纯 Linux x86_64 / Darling，无界面。选用 direct-resource-tool-environment-v100.json、graphics v147 和 stickers overlay；原版 Xcode 工具、Unity/CocoaPods workspace 与 CI 命令保持不变。

## 真实 libc++abi 实现

将 LLVM 19.1.7 的 __cxa_init_primary_exception 初始化路径补入现有 Darling libcxxabi，原有 __cxa_throw 复用同一路径。异常头布局保持不变。完整重建 CMake 中的 18 个源码单元；独立检查确认原有 365 个导出的名称和强弱标志全部保留，只新增该接口。首次构建遗漏原有 libcxx 头目录与 DARLING 编译定义的失败记录保留。

修改已提交到用户账号下的 [kxn/darling-libcxxabi](https://github.com/kxn/darling-libcxxabi/commit/ff0dc59932cc7ad26384303c9c7751eaf319fa5c)，使用其原有默认 master 分支；作者与提交者均为 Comman Kang <kangxn@gmail.com>。完整候选只加入资源工具子进程的库搜索路径，没有覆盖基础运行库。

实际 Darling 原生验证通过 5910 项检查：初始引用计数、异常头字段、实际提供者、跨动态库类型身份、引用拥有与析构、嵌套重抛、直接清理回调以及四线程共享异常。旧库对照重现真实缺失符号。现有 PMR 274020 项、expected 3215 项及 to_chars 数值格式化回归通过。候选输入检查的一个正例、八个损坏对照通过。完整现代 SDK 的 exception_ptr 接口覆盖尚未验证；这些测试不代表整个 C++ 标准库均已兼容。

## 原版框架与完整工程

恢复 PowerLog、Stickers、RecencyService、Coherence、EmojiFoundation、ServiceShared、DifferentialPrivacy、VDAF 八个原版映像，核对 4458 个 GOT 单元和 13794 个绑定，可执行节字节保持一致。原版 dyld_info 的八个格式正例和十六个损坏对照通过；实际候选代码及绑定篡改也被拒绝。原版 Stickers 嵌入目录保留，七个映像在五棵外层框架树中的实际字节已核验。Stickers 与四个依赖的首次重建失败及后续精确导入审计保留，没有猜测未知导入。

原版资源工具依次越过 C++ 异常初始化、PowerLog 遥测符号和 Stickers 类型缺失。最终 actool/ibtool 与完整 Unity/CocoaPods workspace 一致，停在 ODTDevTool 所需的 dgesvd$NEWLAPACK。已核对原版重导出链为 Accelerate → vecLib → libLAPACK.dylib，下一步需要恢复真实提供者，核实 NEWLAPACK ABI，并通过原生奇异值分解的数值/残差检查后接入。

完整 workspace 进入五 target 依赖图，UTI 预检通过，原版 xcodebuild 和外层进程均正常返回 65。CompileC 为零，uEmuera、UnityFramework、AFNetworking 最终二进制仍不存在。资源编译、完整 Unity/UE App 链接与签名、证书签名和 archive/export 尚未完成；默认安装候选没有提升。历史启动超时根因也未证明修复。

## 开发者复现

需要完整本地开发工作区、用户自行提供的锁定 Intel cache/提取件、Xcode/SDK、Darling 与 LLVM。公开包只含源代码、配置与文字证据，不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥；XIP 不提供全部系统框架。payload 路径相对于开发工作区，合并 pins 和历史 revisions 时保留已有 target 和开发者修改。reference/summary 是本地大报告摘要，不能作为运行输入。

```bash
python3 scripts/build-cxxabi-primary-exception.py --tag my-v1
python3 scripts/probe-cxxabi-primary-exception.py \
  --build artifacts/cxxabi-primary-exception-my-v1-build.json \
  --configuration config/direct-resource-tool-environment-v97.json \
  --stage artifacts/private-procfs-v11-stage.json
python3 scripts/test-primary-exception-runtime-inputs.py \
  --output artifacts/my-primary-input-controls.json
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v100.json
```

重建和原生测试使用新名字；此检查点的完整配置仍锁定已记录候选与探针哈希。最后一个命令目前应失败于 NEWLAPACK。完整工程参数为 unity-ios-cocoapods-v57-probe-arguments.json；新运行应换用新的 DerivedData。所有原生命令串行，清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，不覆盖已映射库。reference/original-file-map.json 记录路径与 SHA；日志和历史源码采用 UTF-8 JSON text 封装。进度以 reference/artifacts/primary-exception-resource-progress-v2.json 为准。
