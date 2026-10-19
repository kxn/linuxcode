# 原始 dyld 绑定元数据与保留代码字节的恢复实验

本附件为原版 actool/ibtool 的依赖恢复保存源码、配置及实际失败证据。新候选越过了 AppleIDSSOAuthentication、ApplePushService、BackgroundSystemTasks、DuetActivityScheduler、CoreDuetContext、BiomeLibrary 和 CoreDuet 的缺失；目前直接工具仍因 DuetActivityScheduler 要求原版 BiomeStreams 而退出。**版本查询、真实资源编译及完整 Unity App 仍未成功。** 默认安装候选没有升级。

## AppleIDSSO 的处理依据

该映像的混淆控制流夹有不能可靠线性解码的数据。旧流程把部分数据误当成指令，产生未知跳转和六个伪导入；本附件没有为这些值猜符号或制造成功返回值。

解析器依据苹果开源 dyld 的 v4 patch table 格式，参考提交和文件 SHA256 记录在 `payload/config/cache-patch-metadata-format.json`。本机对原始缓存的 141 条位置记录逐项验证：实际指针与实现地址加偏移一致，原始提供库的导出解析也与记录一致。17 个非零偏移因此获得准确的符号身份，包括原先不能在 `_mach_task_self_` 与邻近符号之间判断的一项。

新模式保留原始代码及其相对 VM 地址，在原有相对位置构造私有 GOT 段。只恢复元数据与原始 nlist 共同确认的 144 个可达导入单元；段中未选择的空间是新分配的零填充，不复制缓存中其他映像的数据。共享池可由多个映像使用，其 weak 标记可能不同，恢复绑定保留本映像原始 nlist 的 weak 语义。非零偏移使用 eager bind，允许 lazy 的符号跳转使用原有绑定辅助流程。

这不是通用缓存提取器，也没有证明任意外部相对引用都已恢复。它是固定输入上的实验模式，仍需真实方法执行和资源产物检查。保留原始代码只能降低重新实现算法的风险，不能证明 Darling 下层 API 与 macOS 完全一致。

## 独立检查及保留的失败

独立检查器从原始文件和候选文件重新解析 Mach-O、VM 段及经典绑定流。它确认 226,919 字节原始 `__text` 和 318 字节原始符号跳转代码逐字节一致，144 个 GOT 单元和 17 个非零偏移绑定与实际写入的符号、ordinal、weak 和 addend 一致。原有段/节描述会为容纳新加载命令而合并，检查按实际 VM 和文件位置进行，不假设节名保持不变。

一个早期候选只描述 GOT 段、没有 section，LLVM 拒绝其绑定流。旧候选和独立失败日志保留；修正后的 v4 增加 section，LLVM 的 eager/lazy bind 解析均成功。11 项小型二进制格式测试检查越界、版本、符号、偏移及损坏数据；另外四项真实候选检查包括正常对照，以及指令字节、绑定符号、段重叠三种破坏的拒绝。

其他六个映像仍使用既有的原始代码/ObjC/Swift 元数据恢复流程。BiomeLibrary 含 1,066 个 ObjC 类、8,738 个导出；首轮因 20 个未知导入拒绝输出，后续只按依赖库中地址完全一致的唯一导出补齐，审计记录保留。这些计数与加载推进均不代表类方法或 Swift 行为已验证。

本轮完整 Unity/CocoaPods workspace 从新 DerivedData 重试，在 600 秒后被超时机制终止，外层 -9，没有原生构建返回码。两次现场栈经 x86_64 fat slice 校正后，均显示后台处于 `loadValidCoreSimulatorService`，主线程等待输入选项准备。它尚未到达资源调用，不能用直接工具的依赖推进替代完整流程证据。等待原因仍待确认；本附件没有禁用原版插件或合成服务成功。

另一个独立的原生 dlopen 夹具实际进入 main，但加载 AppleIDSSO 时也沿依赖链停在 BiomeStreams。因此目前还没有证据证明 AppleIDSSO 完整 dlopen、初始化器或方法执行成功。该夹具每次由 Linux clang/lld 在新目录编译，不使用固定成功返回的替代库。

## 已有研究基线上的配方

需要先前 CoreGraphics v40、lazy resource closure、private-procfs v6、资源专用 libSystem、原版 Xcode 和本地 Intel 原始缓存等输入。按前序研究附件准备基线，审阅后将本附件 payload 合并到工作区对应路径。它没有包含 Apple/Unity 二进制、SDK、缓存、证书或编译产物，也不是从零安装器。

以下为本机配方；已有同名输出时，应先在 pin 中创建新的 target alias 并相应调整路径，使用新的 stage/tag 和报告名，保留旧证据。

```bash
python3 scripts/test-cache-patch-metadata.py
python3 scripts/rebuild-c-cache-image.py \
  --target-manifest config/coregraphics-image-pins.json \
  --target appleidsso-patch-got-v4 --modern-adapter \
  --lazy-functions --analyze-code --collect-missing-imports
python3 scripts/inspect-preserved-patch-got.py \
  --target appleidsso-patch-got-v4 \
  --output artifacts/my-patch-got-inspection.json
python3 scripts/test-preserved-patch-got-inspector.py
python3 scripts/extend-coregraphics-stage.py \
  --parent artifacts/coregraphics-native-v40-stage.json \
  --tag my-patch-got --target appleidsso-patch-got-v4
```

随后按相同方式构建/追加 `applepushservice-resource-v1`、`backgroundsystemtasks-resource-v1`、`duetactivityscheduler-resource-v1`、`coreduetcontext-resource-v1`、`biomelibrary-resource-v2` 和 `coreduet-resource-v1`。C/ObjC 项使用 `--lazy-functions --analyze-code --collect-missing-imports`；BiomeLibrary 使用 `--lazy-functions --experimental-swift --repair-swift-relative --collect-missing-imports`。每次追加以刚生成的 stage 作为 parent，使用新 tag。新 stage 不安装到持久前缀。

使用前一附件的 `stage-direct-resource-environment.py` 为最新 stage 生成新描述，再以 `probe-direct-resource-tools.py --stage ... --configuration ...` 调用原版工具。实际测试清除图形会话环境，由原有 session.lock 串行化 Darling。`config/direct-resource-tool-environment-v9.json` 是本机最新直接工具实测配置，v8 是本轮完整 workspace 尝试所用配置，不能把它们引用的本机产物视为源码包已经提供的文件。独立加载使用 `probe-original-image-runtime.py --runtime-stage ... --configuration ... --target appleidsso-patch-got-v4`。

Unity 完整 scheme 的参数在 `unity-ios-cocoapods-v4-build-arguments.json`，探针参数在 `unity-ios-cocoapods-v5-probe-arguments.json`；复现时将工程、派生数据及 stage 路径替换为本机新产物。`record-resource-patch-got-progress.py` 汇总本机保留的历史报告与哈希，依赖这些历史文件，不是独立冷恢复入口。

完整 App、真实资源内容、Pod 实际编译与最终链接、Unity/UE 签名、证书/provisioning、archive/export、稳定性和从零环境恢复仍未完成。
