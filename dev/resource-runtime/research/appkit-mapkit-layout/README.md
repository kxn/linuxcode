# 原版 AppKit 元数据、MapKit 与布局资源

这是纯 Linux x86_64 / Darling 资源工具路径的实验检查点，完整 Unity/CocoaPods App 尚未编译成功，默认安装环境未提升。

原版 AppKit 的数组桥接代码此前从共享缓存池读到空的 Swift Any 类型元数据。依据精确原始指令、缓存指针和唯一命名导出 `$sypN`，恢复一个指向原版 SwiftCore 的 eager dyld bind。全部原始代码、45,152 个已有 binding 和全部 rebase 保留，只增加一个 binding。Apple 原版格式验证器通过；6 个错误契约和错误 ordinal 被拒绝。原生测试确认指针等于真实 dlsym 返回值，元数据 kind 为 771，原始类型查询重复运行正常。早期测试自身错误的 Swift generic 调用原型导致崩溃，修正后复测，失败证据保留。

随后原版 Interface Builder 插件无法加载：缺少 MapKit 的 MKLookAroundViewController。恢复原版 MapKit 和六个实际依赖；七个映像均保留原始可执行字节，分别通过 Apple 格式验证和破坏对照。两个 math 导入依照缓存 v4 patch 的精确符号名及原版 reexport 路由恢复，没有选用地址相近的替代函数。原生测试验证真实 MapKit 类及 NSViewController → NSResponder → NSObject 继承链；没有伪造类。

新的失败位于原版 initializeLayoutRules → addLayoutRulesFromFile。只读调试器捕获 NSData 的文件参数为空；原始调用明确查找 AppKit 的 AquaGuideRules.plist。新独立 overlay 复制匹配 25G83 系统的原始规则文件和 Info.plist，并保留原始框架代码。运行结果与后续限制见 reference 中的进度报告。不能将映像可加载、类检查或资源路径检查当作实际 actool/ibtool 编译成功。

诊断发现此前 dyld cache assertion 是错误栈符号化引发的二次失败。新增脚本读取原版 DVT assertion / 异常参数和调用栈；原版工具自带的 DVTStackBacktrace__DisableSymbolication 仅用于诊断调用，不改原始 CI 命令。没有屏蔽正常构建中的断言或把错误伪装为成功。

## 开发复现

payload 路径相对完整开发工作区；reference 记录精确原始 SHA 和日志，UTF-8 包装中的 text 可还原原始字节。历史源码须合并入 source-input-history，不应覆盖其他修订。stage 摘要不能当成完整运行输入；重新构建须使用实际新报告和 SHA。用户自行提供 Xcode、SDK 和匹配系统缓存；本目录不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。

```bash
python3 scripts/probe-appkit-swift-any.py --help
python3 scripts/select-verified-resource-frameworks.py --help
python3 scripts/stage-appkit-layout-resources.py --help
python3 scripts/probe-appkit-layout-resource.py --help
```

原生 Darling 运行和使用原生链接器的构建必须串行，使用新 tag/config/output，保留既有候选和失败报告。
