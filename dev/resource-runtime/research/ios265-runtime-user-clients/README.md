# Intel iOS 26.5 运行时与真实 IOKit 用户连接

继续在 Linux x86_64 / Darling 运行原版工具，原工程和 CI 命令保持。未提升默认安装基线，Storyboard 与最终 Unity App 仍未生成。

前一检查点修复 XPC 回复关联及真实对端权限元数据后，原版 Storyboard 返回 iOS 26.5 Platform Not Installed；复用 DD76 的完整 xcodebuild 增量尝试也在 generic iOS 目标选择时以70退出。原版 IBCocoaTouchPlatformToolDescription 调用 simulatorRuntimeFromService:matchingSDK:error:，当前没有匹配运行时。

选择与 SDK 匹配、包含 x86_64 的 Apple iOS 26.5 / 23F77 通用资产。公开 URL 引用来自 AppleDB 的版本记录，二进制从 Apple CDN 下载，并按该记录的 SHA256 校验。Linux ipsw 3.1.739 完成 AEA 解码；新的开发脚本检查 AppleArchive 外层边界、并行解 PBZX 和流式提取内层文件；7-Zip 解开原版 APFS 磁盘映像。80个被7-Zip拒绝的原版相对符号链接已与磁盘映像的元数据逐个核对并原样恢复，包括其遗留的空占位文件。没有修改 Apple 可执行文件内容。原版清单声明 arm64 与 x86_64，运行时主程序也有 Intel slice。

运行时通过私有 Developer 树的符号链接提供。原版 ibtoold 已真实读取其 profile、Info 和 RuntimeRoot，不再报平台未安装，随后触发 IOSurface 用户服务打开错误。这些记录不证明模拟器已启动，亦不证明完整运行时行为或 App 构建成功。

真实 IOSurfaceRoot 服务已经注册，但旧的 IOServiceOpen 入口只接受 IOPMrootDomain，其他服务一律 unsupported。新的 ServiceUserConnection 为已经存在的 IOUserClient 服务建立独立 Mach 连接，保留服务对象、关闭状态和调用者身份；仍拒绝不存在/不支持的服务、类型、属性和任务。旧电源连接路径保留。每次调用刷新方法表，空方法不再进入空函数；参数结构也清零。原生测试证明 IOSurfaceRoot 的两个独立连接、服务身份、无效类型/任务、未知选择器、保留发送权后的重复关闭及关闭后调用行为。失败的两个测试记录保留：fork不继承这些Mach权利、IOServiceClose会释放发送权；后续测试按实际API生命周期修正。未声称验证跨进程转移连接权利的行为。

原版 Storyboard 已越过 IOSurface 打开断言，继续启动 Intel SimLaunchHost.x86。实际采集显示这个新辅助进程被过滤普通 DYLD 路径，而此前选择列表未覆盖它；所需 libimg4 已在既有 device-identity-native 环境中。v145为它及其标准路径添加同一套兼容库选择，正在验证。没有伪造 IOSurface 分配成功，CPU共享图像内存和完整图形服务仍未实现。

开发脚本仅处理用户自行取得的输入。重现需要既有检查点、原版 Xcode/SDK 及相应 Apple 运行时；附件不包含 Apple/Unity 二进制、SDK、XIP、core、证书或私钥。340MB完整APFS目录清单留在本地，仅保存其摘要与被恢复的80条链接信息。公开资产的包装密钥不写入附件；需要从记录指定的公开版本数据取对应x86_64资产字段。

这次只验证新增运行时发现、真实用户连接及受影响的原版资源工具。未重跑此前未变化的 Unity编译、签名、Swift 和格式检查。iokitd修改继续发布到 kxn/darling-iokitd 的 linuxcode/xcode-x86_64 分支，身份为 Comman Kang <kangxn@gmail.com>。
