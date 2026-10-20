# 将系统框架与 Xcode 插件搜索路径分开

原版 actool --version 和 ibtool --version 在 Linux x86_64 / Darling 中都已返回 0，输出 26.6 / 24765。工具原始字节与 XIP 提取版本一致。版本查询不证明实际资源编译、完整 Unity/CocoaPods App 或签名成功；完整工程的后续结果须单独核验，默认安装环境未提升。

此前 DVT 提前创建 NSApplication，使 ibtoold 之后创建自己的 IBCLIServerApplication 时触发原版单例断言。只读调试器捕获了第一次和第二次 init，并定位到 DVTPlugIn _instantiatePrincipalClass。进一步确认被实例化的插件是放在 graphics framework override 目录中的 PlugInKit.framework，主类名称与解析结果均为 NSApplication。

完整 macOS 安装包 SHA256 和 53 个缓存 payload CRC 全部校验，使用原版 aa 在 Darling 内提取 4 个原始资源文件。Info.plist 与之前 Recovery 来源逐字节一致：PackageType=APPL，NSPrincipalClass=NSApplication。原始资源并未拷错，因此没有编辑这些元数据。DVT 原版映像包含明确的额外插件搜索路径逻辑与 DYLD_FRAMEWORK_PATH 日志。

新的独立 graphics stage 将 PlugInKit 从 override 目录移出，保持所有框架代码、资源与符号链接字节，并由专用 launcher 仅在本次私有 Darling mount namespace 中，将完整框架树绑定到 /System/Library/PrivateFrameworks/PlugInKit.framework。原版 dyld 使用正常系统位置加载它，DVT 的额外插件路径不会扫描到这个副本。live process root 中映像可读且 SHA256 与原始候选相同，宿主 prefix 视图中没有映像文件；工作区可能留下空的挂载点目录。原始 CI 命令、工具二进制及苹果 Info.plist 均未修改。

完整原始样本 DD70 已执行到 16 个 ScanDependencies 任务，仍无 CompileC；原版工具明确拒绝 AFNetworking 的两处 netinet6/in6.h 私有头文件直接导入。独立 Apple Clang 对照：私有导入返回 1，公开 netinet/in.h 导入及 IPv6 ABI 断言通过。SDK modulemap 也明确标为 private textual header。

另建 SDK 兼容测试副本，仅删除两行冗余私有导入，23 个 Xcode/CocoaPods 配置文件及其余 5979 个文件逐字节一致，原样本不变，没有压制编译器诊断。副本 DD71 / v78 的后续构建需单独验证；此项是测试样本源码的 SDK 兼容修正，不是 Darling 运行时修复，也不宣称原样本已编译通过。

## 复现与范围

依赖此前 Automator 与 AppKit/MapKit 检查点和用户自行提供的 Xcode、SDK、匹配系统缓存。payload 相对完整工作区；reference 中 UTF-8 text 可还原原始字节，历史源码应合并保留。当前 stage 摘要不可直接拿来启动；重新生成候选须更新实际路径和 SHA。源码包不含 Apple/Unity 二进制、XIP、SDK、证书或私钥。

```bash
python3 scripts/stage-canonical-pluginkit.py --help
python3 scripts/probe-direct-resource-tools.py --configuration config/direct-resource-tool-environment-v130.json --stage artifacts/private-procfs-auditsession6-stage.json
```

生成过程使用新 tag/config，不覆盖已映射文件。Darling 原生执行及原生链接须串行。完整工作区构建参数 v77 / DD70 保留原 workspace、scheme 与 CI 操作，仅选取新的隔离资源环境和 DerivedData 目录。
