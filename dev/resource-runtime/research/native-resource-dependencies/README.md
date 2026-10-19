# 原版资源工具依赖与 Swift 元数据开发检查点

本附件继续 [CoreGraphics 实验](../native-coregraphics/README.md)，仍是 Linux x86_64/Darling 无界面路线。它提供源码、可复现检查和失败证据摘要，**不是 actool/ibtool 已完成资源编译的发行版**。没有 Apple 二进制、SDK、缓存或字体输入，也没有改变安装器和成功 ad-hoc 签名的既有基线。

## 本轮已验证的内容

- 原版 Apple Swift 编译器复现了一个 `~Copyable` 泛型环境：头部声明 1 条约束，实际发出 2 条记录；编译后的程序成功执行 6 个 KeyPath 投影。Swift 开源实现先写入普通约束数，再追加逆协议约束，与实际输出吻合。
- CoreVideo 的原始环境记录保持不变。解析器只对固定哈希、原始符号边界、参数引用和协议描述符均匹配的布局恢复完整边界；15 个损坏记录测试均拒绝。CoreVideo 镜像成功重建，但不能据此推断其 API 可用。
- 现有 Swift os 和 RSD 两个代表库用修改后的共享工具重新构建，输出与已有基线逐字节一致；旧 Foundation/KeyPath 布局检查也通过。
- 后续补读原版 `__swift5_acfuncs` 表：按 Swift 的 `TargetAccessibleFunctionRecord` 布局定位无本地符号名的泛型环境，不扫描猜测整数头。IDSFoundation 的 19 条记录、4 个环境和 18 项损坏检查通过，镜像保留 15,950 个原版导出。原版 Apple Swift 编译器生成相同记录布局，程序实际完成两次本地 distributed actor 调用；不代表远程调用已验证。修改后 Swift os、RSD、CoreVideo 三个代表库的输出仍逐字节一致。
- 补入原版数学库的 7 个缺失 SIMD 函数，仅显式增加这些名字，不替换已有数学接口。七个函数的完整指令范围和四个只读数据节都与原缓存逐字节一致。实际执行通过 129 组精确有理数矩阵求逆对照，408 个向量分量的数值检查通过。
- 恢复新增 OpenGL 配套库和既有 70 个资源依赖的延迟函数入口；70 个镜像重建恢复 28,150 个延迟绑定槽，其中 56 个为 Swift 镜像。未提供成功桩；调用到尚未实现的目标仍会由动态链接器报错。重建成功不代表这些框架 API 均可用。
- 五个缺失扩展标志按原版缓存恢复为真正的 `uint32_t` 对象，编译后字节和原值一致；实际进程验证五个新对象的所有者及数值，并检查四个已有标志没有改变。只增加常量，不增加对应策略操作。

## 实际失败与兼容范围

1. **SIMD 严格标量等价检查没有通过。** 混合向量 `[-0,+0,NaN,+Inf]` 中，原版向量 sin 的第一分量返回 `+0`，Linux 标量参考为 `-0`。保留原始实现，没有修补结果；测试整体仍非零退出，并单独记录数值检查与符号零差异。指令和常量字节相同不能证明所有运行环境语义相同，也没有证明完整 IEEE 或 Apple 平台等价性。
2. **CoreVideo CPU 像素缓冲区测试失败。** 已确认调用原版 `CVPixelBufferCreateWithBytes`，随后原版 IOSurface 因无法打开内核服务（`e00002c7`）断言退出。不能声称无需 GPU 的缓冲区路径已可用，也不能用“工具不显示界面”推断它不需要其他系统服务。
3. **原版 actool 和 ibtool 仍未启动成功。** 恢复延迟绑定并复用已有签名兼容导出后，已越过此前 Security 加载错误；该轻量要求 API 并未因此实现。最新实验缺 IDSFoundation 所需的 XPCDistributed。这是启动依赖证据，不是完整图形算法或资源产物正确性证据。新增 CFString 类型/值/复制测试也仍因依赖未加载而失败，没有给出通过结论。
4. 前一附件中的 `CGColorConversionInfoCreate` 仍返回 NULL。真实 Unity/UE 导出工程、证书/provisioning 签名、设备信任、archive/export、完整冷重建都尚未完成。

完整状态及本地报告路径、SHA256 见 [evidence.json](evidence.json)。失败报告和前一版 stage 均保留，不用后续成功覆盖。

## 开发工作区复现

需要已有候选工作区、固定 Intel 缓存/提取镜像、Xcode SDK 和 LLVM 19。先审阅 `payload/` 并在独立开发工作区手动合并；其中包含共享重建脚本的新版本，**不能直接覆盖开发者修改**。本附件不由固定 67 镜像 overlay 自动应用，也不构成从 XIP 开始的完整安装方案。

先复现编译器行为，使用打印出的新报告路径检查固定 CoreVideo 记录：

```bash
python3 scripts/test-original-swift-inverse-environment.py
python3 scripts/test-swift-environment-inverse-bounds.py \
  --compiler-proof runtime/original-swift-inverse-environment-NEW/result.json \
  --report artifacts/my-corevideo-environment-proof.json
python3 scripts/rebuild-c-cache-image.py \
  --target-manifest config/coregraphics-image-pins.json --target corevideo-resource-native \
  --analyze-code --experimental-swift --repair-swift-relative --collect-missing-imports
```

此处 `NEW` 要替换为第一条命令实际输出的目录；结构检查明确核对该报告与编译输入的哈希，不接受手写成功标志。共享布局回归：

```bash
python3 scripts/test-swift-metadata-layouts.py
python3 scripts/test-swift-keypath-environments.py
```

两个旧布局测试使用固定报告路径，重跑前先归档原报告。重建 CoreImage、ATS 和 SIMD 数学库使用 `--analyze-code --collect-missing-imports`；CoreImage/ATS 没有 Swift 类型，不加 Swift 实验参数。新增 OpenGL 配套库使用配置中的 `*-lazy-resource-native` 目标并加 `--lazy-functions`；`rosetta-x86-lazy-resource-native` 只是 Intel 依赖镜像恢复，不提供 ARM 执行能力。

在上一附件构造的系统导出 stage 上，显式补入原版数学函数：

```bash
python3 scripts/rebuild-c-cache-image.py \
  --target-manifest config/coregraphics-image-pins.json --target simd-math-resource-native \
  --analyze-code --collect-missing-imports
python3 scripts/verify-original-simd-math-bytes.py --report artifacts/my-simd-byte-identity.json
python3 scripts/stage-native-simd-math.py --tag my-simd \
  --base-stage artifacts/native-system-resource-exports-MY-stage.json
```

`stage-coregraphics-native.py` 的 `--simd-stage` 选择这个新报告，并用 `--dependency` 加入所需原版镜像，生成新的独立 graphics stage。两个实际 API 检查使用该报告：

```bash
python3 scripts/test-original-simd-math.py --graphics-stage artifacts/coregraphics-native-MY-stage.json
python3 scripts/test-original-corevideo-native.py --graphics-stage artifacts/coregraphics-native-MY-stage.json
```

以上两项目前预期失败，分别为已记录的符号零差异、IOSurface 服务断言；失败结果是后续工作的依据。工具启动检查使用 `probe-ios-resource-tools.py --runtime-profile scripts/coregraphics-native-profile.py --graphics-stage … --tag NEW`，仍须检查真实 native 状态标志。所有 Darling 执行串行共享 `runtime/session.lock`，每次 stage 和报告使用新名字。

## 复现 accessible-function 修复与 70 镜像候选

新增源文件 `scripts/swift-accessible-function-records.py` 必须与新版 `restore-swift-metadata.py` 一起合并。它按记录表验证名称、类型、环境、函数或异步入口描述符的界限，拒绝未知标志和不支持的布局。原始记录和泛型环境头均不改写。布局依据为 Swift `swift-6.3.3-RELEASE` 的 [Metadata.h](https://github.com/swiftlang/swift/blob/swift-6.3.3-RELEASE/include/swift/ABI/Metadata.h)、`MetadataValues.h` 和 `GenDecl.cpp`，精确来源和 SHA256 存在证据摘要中。

```bash
python3 scripts/test-original-swift-accessible-functions.py
python3 scripts/test-swift-accessible-function-records.py \
  --compiler-proof runtime/original-swift-accessible-functions-NEW/result.json \
  --report artifacts/my-accessible-record-proof.json
```

`NEW` 使用第一条命令的真实输出目录。此程序只验证本地调用和编译产物布局，没有声称分布式远程调用可用。

`payload/artifacts/ios-resource-lazy-v1-rebuild-plan.json` 保存 70 个目标的确切构建参数；对应 pin 文件为 `config/ios-resource-lazy-image-pins.json`。在已有完整候选的独立工作区中合并附件后，可用以下批次构造新资源 stage。预检查会拒绝覆盖任何已有目标输出：

```python
import json
import subprocess
from pathlib import Path

plan = json.loads(Path('artifacts/ios-resource-lazy-v1-rebuild-plan.json').read_text())
for row in plan['targets']:
    assert not Path('runtime/rebuilt-' + row['target']).exists(), row['target']
for row in plan['targets']:
    subprocess.run(['python3', 'scripts/rebuild-c-cache-image.py',
        '--target-manifest', plan['manifest'], '--target', row['target'],
        *row['flags']], check=True)
command = ['python3', 'scripts/stage-ios-resource-closure.py', '--tag', 'my-lazy-v1',
           '--target-manifest', plan['manifest']]
for row in plan['targets']:
    command += ['--target', row['target']]
subprocess.run(command, check=True)
```

原版 IDS/IDSFoundation 以及新增依赖另在 `coregraphics-image-pins.json`；Swift 目标继续使用 Swift 实验参数，函数目标使用 `--lazy-functions --analyze-code --collect-missing-imports`。未解析引用仍须审计，不能删除或改成固定返回值；缓存导出解析器只接受唯一对应的原依赖导出。

`stage-native-sandbox-extension-constants.py --tag NEW --base-stage …` 在前述数学 stage 上加入五个常量；`test-sandbox-extension-constants.py --graphics-stage …` 已通过实际九对象检查。新增的 `coregraphics-native-security-profile.py` 显式选用已有签名兼容导出及空的本地测试身份库，只用于该候选，尚未验证用它完成签名构建。

工具检查应指定 `--stage artifacts/ios-resource-my-lazy-v1-stage.json --runtime-profile scripts/coregraphics-native-security-profile.py --graphics-stage … --tag NEW`。当前仍预期在加载依赖时失败；成功签名构建基线保持原样。仅有这些源码或 XIP 仍不足以完整冷重建候选环境。
