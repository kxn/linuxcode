# Objective-C 自定义析构启动接口

移植苹果开源 objc4 的 `_class_setCustomDeallocInitiation`。源代码与独立测试已发布在 [kxn/darling-objc4](https://github.com/kxn/darling-objc4/commit/ebeed2c3e13ffcaab199e82723dc01e8ed59048d)，沿用已有分支。

在旧运行时空闲的 class_rw_t bit 24 保存策略，保持对象、类和 cache 的结构大小。标记现有类和子类，后建子类在 addSubclass 继承；最后一次 release 转入析构状态后调用真实 `_objc_initiateDealloc`；析构中的对象不再放进 autorelease pool。不是空函数或强行跳过初始化。

原生探针分别要求实际非指针 ISA 和 raw ISA。两组各 1,429 项检查覆盖未标记对象、现有/后建静态和动态子类、工作线程触发而主线程完成析构、弱引用、反复 retain/release 以及释放对象后再排空 pool。旧配置缺少 API 返回 12；错误计数返回 15；两种 ISA 给析构中对象建立新弱引用均按实际运行时行为 abort，作为负对照。

五项既有 selector、枚举、NSInvocation、tagged pointer 回归通过。保留原有 771 个导出。最终 v4 编译的 43 个对象文件与已完成回归的 v3 逐字节一致；v4 源文件与发布的源码提交对应，且 v4 重新完成了原生析构探针。

## 原版工具和完整工程的边界

原版 actool/ibtool 越过缺少该接口的错误，随后在初始化 XCTAutomationSession 时发生空地址调用。保留原始 GDB 寄存器、frame 链、映射和正确处理 fat slice 的符号化证据；栈顶直接返回地址及原版 stub/弱导入表进一步确认：未加载的 AutomationMode.framework 提供 `_XAMRegisterAutomationModeChangeHandler`，原版调用方直接调用了该空弱导入。该原版框架文件存在，接口执行仍待验证。重复 Objective-C 类警告仍在，不能视作已解决。

完整 Unity/CocoaPods 原版 workspace 使用 v118/v3，五 target 图和 UTI 预检通过，xcodebuild native/outer 65。CompileC 仍为零，最终 App、UnityFramework 和 AFNetworking 产品不存在。配置 v119/v4 的独立原版工具探针亦失败。没有实际资源编译、Unity/UE App、完整签名或 archive/export 成功声明，默认安装候选未提升。

## 复现

需要完整 Linux x86_64 开发工作区、自行提供的锁定 Xcode/SDK/系统框架和 Darling/LLVM。payload 相对工作区，reference 的源码、日志和历史输入以 UTF-8 JSON text 封装；映射包含原始 SHA。旧版本源输入应按 source-history-entries 合并保存。附件不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。

```bash
python3 scripts/build-objc-source.py --output-dir runtime/objc-custom-dealloc-source-v4 --report artifacts/objc-custom-dealloc-source-v4-build.json
python3 scripts/probe-objc-custom-dealloc.py --configuration config/direct-resource-tool-environment-v119.json --baseline-probe runtime/direct-resource-tools-9ha_46ri/result.json --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-objc-custom-dealloc-regressions.py --configuration config/direct-resource-tool-environment-v119.json --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-direct-resource-tools.py --configuration config/direct-resource-tool-environment-v119.json --stage artifacts/private-procfs-v11-stage.json
```

所有原生运行串行、无图形界面。最后一项当前仍失败；完整工程参数为 unity-ios-cocoapods-v72-probe-arguments.json。研究配置固定了本工作区生成的报告 SHA；重新构建后必须重新计算配置中的 build 报告 SHA，不要把旧 hash 当作可跨构建复用的输入。
