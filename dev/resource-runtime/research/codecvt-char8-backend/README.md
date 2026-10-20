# 完整 libc++ 后端与 C++20 字符转换

本附件在 Linux x86_64 / Darling 中使用原版 Xcode 工具，继续前序 PMR/AudioToolbox 检查点。它没有完成完整 Unity/UE App 的资源编译、链接或签名，也没有提升默认安装候选。最新完整构建和直接工具的实际结果见 evidence.json。

## 同时构建 facet 和 locale 安装路径

AppleMediaServicesKitInternal 需要 `codecvt<char32_t, char8_t, mbstate_t>::id`。原有 Darling libc++ 源码已经包含 char16_t/char32_t 的 char8_t 转换实现，以及 classic、命名和分类组合 locale 的安装路径；C++11 编译条件关闭了它们。

build-libcxx-char8-backend.py 读取原有 CMake 的完整 38 单元列表，用相同源文件和原有头文件按 C++20 编译，不只补一个 id，也没有将不同 facet 类型别名化。头文件依赖和对象 SHA 均记录在构建报告。首次整库编译因缺 mach-o/loader.h 停止；补入已有 XNU EXTERNAL_HEADERS 的低优先级搜索路径后，全部单元成功。

整个后端保留原有 1837 个直接导出，新增 47 个。其中包括真正的 char8_t facet，也包括由原有 C++20 源码条件启用的 format_error 和 barrier 组件；不能据此声称完整 C++20/C++23 库兼容性。

## 使用原版链接器恢复导出属性

第一份 LLVM 链接候选虽然导出齐全，但 880 个原有符号的强弱属性发生变化，因此没有选用它。relink-libcxx-char8-native.py 使用与 XIP 提取件逐字节一致的苹果 ld-classic，执行原有 unexported、force-not-weak、force-weak 规则，再独立比较结果。最终候选对全部 1837 个旧直接导出保留名称和属性，仍转导出原有 libc++abi。首次原版链接因版本字符串格式被拒绝，失败也保留在 reference。

新目录仅含 libc++0.dylib。既有 PMR/expected/typed-new/to_chars wrapper 继续使用原有字节，通过它已有的转导出关系选中新的完整后端。旧运行根中的库没有覆盖。资源配置仅在 actool/ibtool 的既有子进程作用域选用新后端。

在完整历史开发基线上，用新 tag 构造独立候选：

```bash
python3 scripts/build-libcxx-char8-backend.py --tag my-objects
python3 scripts/relink-libcxx-char8-native.py \
  --build artifacts/libcxx-char8-backend-my-objects-build.json \
  --tag my-linked --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-libcxx-char8-backend.py \
  --build artifacts/libcxx-char8-backend-my-linked-build.json \
  --configuration config/direct-resource-tool-environment-v67.json \
  --stage artifacts/private-procfs-v11-stage.json
```

需要已有 Darling 源码/头文件、LLVM 19、本地原版 Xcode ld-classic 和已验证的运行基线。bootstrap 配置必须尚未选入新后端，才能验证旧库的真实缺失负例。新配置应引用自己生成的构建报告、原生证明与实际 SHA；不能直接复用参考工作区的输出路径。所有输出使用新名字，原生会话串行运行并清除图形会话环境变量。

## 原生行为验证

两个使用实际 Xcode SDK 编译的 DSO 验证 id 的唯一性、facet 身份及 RTTI。测试覆盖 classic、命名 C locale、默认及 global locale、自定义 facet 生命周期、4000 次线程查询，以及已有 stream/regex 消费者。

全部 1,112,064 个 Unicode 标量分别验证 UTF-8/UTF-16/UTF-32 转换、输入输出游标和 length；另有独立编码字面量、无效/过长 UTF-8、surrogate、越界码点及部分缓冲区检查。共 13,328,539 次检查通过。首轮测试曾错误要求命名 locale 的动态类型也等于基类；源码实际安装 codecvt_byname，现按真实动态类型检查跨 DSO 身份，并单独验证 classic 的基类类型。旧断言和失败记录保留，不将其当作运行库缺陷。

已有 PMR 测试另通过 274020 次检查、128 次分配和两次销毁；expected 异常/生命周期通过 3215 次检查。数字格式化复用既有 11427 个有限值和 15 个 Intel long-double narrowing 用例，并与独立 Linux 参考逐行比较，保留既有允许的十六进制表示差异。五项原生模式必须全部通过才允许资源配置选择这个后端。

## 继续恢复原版资源依赖

v68 的原版 actool/ibtool 已越过字符转换缺失，随后缺少 UserNotifications 的 UNNotificationActionIcon 类。新增的 usernotifications-patch-got-v1 保留原始 Intel 框架的可执行指令及 VM 相对位置，并验证真实序列化绑定；没有自行伪造这个类。候选还通过苹果 dyld_info 格式校验及两个损坏对照，另有实际候选的篡改拒绝测试。格式和加载检查不证明整个框架的 API 行为。

v69 已越过该类缺失，随后缺少 AVFAudio 所转导出的 AVAudioSessionRoutingContextChangeNotification。原始导出表明确指向 AudioSession；当前选用的 AudioSession 候选已经包含这个导出。后续应恢复 AVFAudio 的真实转导出链，并验证实际解析，而不是猜常量值或重复构造提供者。

原版工具、原始 Unity/CocoaPods workspace 和命令不变。后续配置和完整构建的实际失败、产物是否存在均记录在 evidence.json；版本查询成功也不能代替资源编译或完整 App 证明。

payload 是相对于完整开发工作区的增量源码，需要与前序附件合并并保留精确源码历史。reference 中的日志以 JSON text 保存原始 UTF-8 字节，original-file-map.json 提供 SHA；summary_only 文件只是完整本地报告的摘要。公开材料不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥，也不是干净机器的一键安装成果。
