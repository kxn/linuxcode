# PMR 类型 ABI 与原版 AudioToolbox

本附件继续推进 Linux x86_64 / Darling 上的原版 Xcode 工具。原版 actool、ibtool 及 Unity/CocoaPods 工程和命令保持不变；没有生成完整 App，也未完成 Unity/UE 链接、签名、archive/export 或设备验证。默认安装候选没有提升。

## 使用真正的标准 PMR 类定义

caulk 需要 C++17 `std::pmr::memory_resource` 的类型信息。现有后端只有旧实验命名空间，不能将两个不同的 C++ 类型直接别名化。新增源码使用本地 Xcode SDK 的实际类声明，析构函数正文来自固定 LLVM 提交 `2078da43e25a4623cab2d0d60decddf709aaea28` 的 `libcxx/src/memory_resource.cpp`，保留 LLVM 许可证标识。RTTI、虚表及三个析构入口由编译器生成，没有手工拼装。

构建器先重新链接旧输入，要求旧库与对照仅 UUID 不同，再添加新对象。107 个旧直接导出全部保留，只新增六个 PMR 导出，后端命名空间仍完整转导出。新搜索目录只含一个 libc++.1.dylib，避免将构建目录中的其他旧库带入进程。

原生验证包含缺失库负例和两个实际成功用例。SDK 编译的两个 DSO 共同验证标准类 RTTI 身份、虚表、虚调用、128 次不同大小/对齐分配及释放、跨 DSO bad_alloc、相等性、dynamic_cast 和通过基类删除；共 274020 次检查。已有 std::expected 异常与生命周期夹具另有 3215 次检查通过；其生产者二进制保持不变，消费者仅替换显式检查的库所属路径。

这只补齐 memory_resource 的真实 key function 和由它生成的类 ABI。没有宣称实现标准 PMR 的全部默认资源、pool 或 monotonic 运行时。

需要完整历史开发基线、固定 LLVM checkout、本地 Xcode SDK 和既有 wrapper 对象。使用新 tag，在完整工作区中运行：

```bash
python3 scripts/build-pmr-key-function.py --tag my-pmr
python3 scripts/probe-pmr-key-function.py \
  --build artifacts/pmr-key-function-my-pmr-build.json \
  --configuration config/direct-resource-tool-environment-v65.json \
  --stage artifacts/private-procfs-v11-stage.json
```

bootstrap 配置必须尚未选入新 PMR 库，才能执行真实的缺失负例。v66/v67 是后续选用新库的配置，不适合作为该负例的基线。probe 返回新的 result.json；生成自己的后续配置时须填入实际构建/原生证明路径与 SHA，不应照搬此工作区的输出。

## 修复没有 weak-bind 流时的归一化

PMR 消费者没有 weak-bind 流，旧归一化器会错误地尝试在偏移零插入终止指令，随后被结构检查拒绝。现在零长度流直接返回原始字节，不修改 Mach-O。真实输入回归证明无流文件逐字节不变、旧失败可复现，且既有非空流的绑定记录和其余载荷完整保留。首次失败和旧源码均保存在 reference 中。

```bash
python3 scripts/test-empty-weak-normalization.py \
  --empty-image runtime/your-pmr-native-directory/pmr-test \
  --prior-normalizer /path/to/exact-prior-normalizer.py \
  --weak-image runtime/expected-access-source/unprocessed-libc++.1.dylib \
  --output artifacts/my-empty-weak-normalization.json
```

## 保留原版 AudioToolbox 代码

PMR 修复后，原版资源工具以及完整五目标 Unity/CocoaPods 构建越过 PMR 缺失，暴露 MediaToolbox 所需的 AudioToolbox 常量。新增 audiotoolbox-patch-got-v1 使用原始 Intel AudioToolbox，独立检查原有可执行节字节、VM 相对位置、1104 个 GOT 单元、27 个非零 addend 和 2005 个序列化绑定；没有替换常量或函数实现。

苹果原版 dyld_info 接受候选，并拒绝损坏加载命令和绑定段的两个对照。LLVM 19 的首节基址限制另有明确记录，未将其失败冒充通过。实际二进制的代码、绑定及局部绑定证明篡改均被独立检查拒绝。

v67 只在原版 actool/ibtool 子进程选用新的不可变 graphics/overlay 目录。实际工具已越过 AudioToolbox 常量，下一缺口是 AppleMediaServicesKitInternal 需要的 C++20 `codecvt<char32_t, char8_t, mbstate_t>::id`。Darling 的 locale.cpp 已包含相关转换与 classic-locale 安装代码，但 C++11 构建及头文件条件关闭了这些特化。后续需补齐实际 facet 和 locale 集成，验证转换、错误/部分输入及既有运行时；不能只补一个全局符号或将不同类型别名化。

已将未修改的 Darling locale.cpp 在独立目录按 C++20 编译成功，生成 46 个 char8_t 相关外部符号，包含实际缺失的 id。这只是对象编译证据，尚未链接成运行库或验证 locale 集成；不会把这个对象直接当成已完成的修复。

具体命令、原生命令状态、完整 App 产物检查和最新失败见 evidence.json。版本查询、加载和格式检查均不等于资源编译成功。所有 Darling 会话串行运行，并清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY。

payload 是相对于完整开发工作区的增量材料，应与前序附件审阅合并，并保留精确源码 SHA 历史。reference 日志以 JSON 的 text 字段保存原始 UTF-8 字节，original-file-map.json 给出 SHA；summary_only 报告仅为完整本地报告摘要。公开包不包含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。这不是干净机器的一键安装成果。
