# 原版 QuickLook 与资源依赖检查点

纯 Linux x86_64 / Darling，无界面。选用 direct-resource-tool-environment-v97.json、graphics v145 和 quicklook-logging overlay，原版 Xcode 工具、Unity/CocoaPods workspace 与 CI 参数保持不变。

恢复并选入 13 个原版映像：ViewBridge、AssetCacheServices、QuickLook、MediaAnalysis、ANSTKit、CoreAppleCVA、MediaAnalysisPhotosServices、MediaAnalysisServices、SoundAnalysis、AppleNeuralEngine、EmbeddedAcousticRecognition、ANEServices、IsolatedContextLogging。独立核对 8424 个 GOT 单元、32191 个序列化绑定，可执行节字节保持一致。原版 dyld_info 的 13 个格式正例、26 个损坏对照均通过；实际候选的代码和绑定篡改也被独立检查器拒绝。这些检查不证明框架所有 API 都兼容。

MediaAnalysis、SoundAnalysis 和 EmbeddedAcousticRecognition 的首次重建失败均保留。前后两个数学导入分别由原版跳转桩、GOT patch 记录和 libSystem 重导出链核实为 lround 与 scalbnf；没有按相同函数地址猜名称。SoundAnalysis 的 13 个导入通过原版显式重导出链核实。IsolatedContextLogging 在依赖表中为弱依赖，但原版工具实际引用其 Swift 类型后仍需要该原版库，因此依据实际失败补入。

## 完整工程结果

原版 Unity/CocoaPods workspace 进入五 target 依赖图，UTI 预检通过；原版 xcodebuild 和外层进程正常返回 65。直接运行的 actool/ibtool 与完整工程均停在 EmbeddedAcousticRecognition 所需的 __cxa_init_primary_exception：当前 libc++abi 没有该导出。已核对 LLVM 19.1.7 上游有对应真实初始化实现，下一步需要适配现有异常头 ABI 并验证构造、引用计数、析构、重抛及多线程行为。

CompileC 为零，uEmuera、UnityFramework、AFNetworking 的最终二进制仍不存在。资源编译、完整 Unity/UE App 链接与签名、证书签名和 archive/export 均未完成；默认安装候选没有提升。历史启动超时根因仍未证明修复。

## 开发者复现

需要完整本地开发工作区、自行提供的锁定 Intel cache/提取件、Xcode/SDK、Darling 与 LLVM。公开附件只包含源代码、配置和文字证据，不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。XIP 本身不提供全部系统框架。payload 相对于开发工作区；合并 pins 和历史 revisions 时保留已有 target 与开发者修改。旧检查点保留祖先环境的证据，reference/summary 是大报告摘要，不能作为运行输入。

```bash
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v97.json
python3 - <<'PYTHON'
import json, subprocess, sys
args = json.load(open('config/unity-ios-cocoapods-v54-probe-arguments.json'))
sys.exit(subprocess.run([sys.executable, 'scripts/probe-xcode-service-runtime.py', *args]).returncode)
PYTHON
```

当前两个命令均应失败于上述异常接口。所有原生命令串行运行，清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY；新运行使用新 DerivedData、阶段和报告名，不覆盖已映射库。reference/original-file-map.json 提供原始路径与 SHA，日志及历史源码使用 UTF-8 JSON text 封装。当前进度以 reference/artifacts/quicklook-original-dependencies-resource-progress-v1.json 为准。
