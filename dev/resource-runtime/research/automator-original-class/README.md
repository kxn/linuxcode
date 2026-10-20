# 原版 Automator 类继承与 Interface Builder 初始化

原版 Cocoa 插件在 IBReplaceMethodPrimitive 中因缺少 encodeWithCoder: 的类型编码而断言。原生检查确认：插件的 AMPathPopUpButtonIntegration category 正常挂载，ibSwizzledEncodeWithCoder: 已存在；Darling 旧 Automator 把 AMPathPopUpButton 定义为直接继承 NSObject 的占位类，丢失了真实类的 UI 控件继承链。初期根据返回地址误判为 replacement 方法缺失，后续对照检查纠正，原始失败记录保留。

从匹配系统缓存恢复原版 Automator 及 AppleScriptObjC、XprotectFramework、yara、libEndpointSecuritySystem、OSAKit，六个映像保持原始可执行字节，分别经过苹果原版 dyld_info 格式验证和损坏对照。Endpoint dylib 的 sandbox_ms 名称依据缓存 patch 的精确身份及原版 reexport 路由恢复。独立 dylib 保留在已验证 graphics library 搜索目录，四个 framework 放入隔离 overlay；后续额外加入 OSAKit，补足实际加载发现的 OSAScriptErrorMessage。没有更换原版工具或添加假的 coder 方法。

原生三组检查：旧配置缺 coder 方法返回 12；新配置返回 0，真实 provider 为原版 Automator，继承链为 AMPathPopUpButton → _AMVariablePopUpButton → NSPopUpButton → NSButton → NSControl → NSView → NSResponder → NSObject，encodeWithCoder: 编码 v24@0:8@16；错误类名返回 15。类/方法检查与资源工具运行、最终 App 编译各自独立，最新结果见进度报告，不能据此宣称完整 Unity/CocoaPods App 或签名成功。

## 开发复现

依赖此前 appkit-mapkit-layout 检查点与完整本地开发环境。用户自行提供 Xcode、SDK 和匹配系统参考资料；无 Apple/Unity 二进制、XIP、证书或私钥。payload 相对工作区，reference 的 UTF-8 text 可恢复精确原始字节；历史修订应合并，不能覆盖旧证据。stage 摘要不是可直接启动的完整 stage，重建必须更新实际路径/SHA。

```bash
python3 scripts/select-verified-resource-frameworks.py --help
python3 scripts/probe-original-automator-class.py --help
python3 scripts/probe-ib-cocoa-category.py --help
```

原生执行必须串行，使用新的 tag/config/output。默认安装环境仍未提升。
