# Intel 模拟器加载器版本与文件签名登记

原版 Xcode / Storyboard 流程继续在纯 Linux x86_64 Darling 中运行，工程与 CI 参数保持。尚未生成最终 Unity App，不提升默认安装候选。

现代 dyld 版本集合原先只有截至 2021 年的表，SimLaunchHost 触发未知集合断言。新生成器从已有 Intel 参考 dyld 的实际 mapper 推导 40 字节步长和 61 条边界，核对两份表完全一致；源码库使用这些数值事实，未知未来集合返回零。完整 29 单元 libdyld 已重建，真实加载的三个不同 min/SDK 映像和主程序快速路径测试通过。该修改已经发布到 kxn/darling-dyld 原有分支。

下一步原版加载器需要 F_ADDFILESIGS_FOR_DYLD_SIM（83）。新服务通过 SCM_RIGHTS 接收实际描述符，读取调用者 LP64 参数，验证 Mach-O 的 LC_CODE_SIGNATURE、SuperBlob 边界/唯一槽位、Apple CMS 证书链、软件签名叶标记及用途、CodeDirectory、每个代码页和存在的特殊槽位，最后才记录签名和返回覆盖范围。信任锚为 Apple 开源 Security 中的三份公开根证书。按 AppleSoftwareSigning 的 Basic X509 / 默认代码签名语义，不单凭证书过期拒绝；未声称实现联网吊销查询、完整 AMFI、内核逐页执行约束或全部 CodeDirectory 形式。

真实 iOS 26.5 Intel dyld_sim 返回覆盖长度 639920。ASan/UBSan 下的真实文件及 13 个损坏/错误输入对照通过；原生动态库调用还验证了 SCM_RIGHTS、空/错误指针、错误范围、坏描述符和只读返回地址。源服务与完整 879 单元内核库已重建，代码分别发布到 kxn/darlingserver 和 kxn/darling-xnu 的 linuxcode/xcode-x86_64 分支，提交身份为 Comman Kang <kangxn@gmail.com>。

原版 Darling 主加载器静态带有另一份旧 fcntl，所以更新动态内核库不能覆盖启动阶段。新增构建脚本把同一份已测试 fcntl 源码及生成 RPC 链接成无动态导入、无重定位的 RX 组件，追加到固定版本的开源 Darling 加载器，并将原 syscall 入口的五个字节跳转到新实现。保留原有段、C++ 对象布局、符号地址和其他代码字节，逐字节限制允许变动的入口、头部和新增段；这是源码组件更新，尚非完整主加载器源码重建。未修改 Apple 工具或 Apple 模拟器加载器的内容。

首次把文件绑定到 overlay 的底层目录后，真实进程仍加载旧入口；失败记录保留。后续在 darlingserver 的实际挂载命名空间中绑定到合并视图，直接调用主加载器静态入口的七组原生测试全部通过，并读回新的入口字节。只影响当前私有会话。最新原版 Storyboard 的实际输出、退出码与未完成原因见 reference/original-file-map.json 中指定的最后一次 result.json；没有把局部成功当作完整构建成功。

复现先应用此前研究基线，再使用 payload 中的脚本与源码；主机服务新增依赖 libssl-dev / OpenSSL::Crypto，宿主校验使用 g++ 的 ASan/UBSan。build-dyld-bootstrap-fcntl.py 接收完整内核构建清单；stage-dyld-bootstrap-fcntl.py 创建独立挂载入口和新配置。开发者自行提供 Xcode、SDK 和运行时。附件只含 UTF-8 源码、公开根证书文本、摘要及报告，不含 Apple/Unity 可执行文件、SDK、XIP、CMS 输入或私钥。原始日志与历史源码用 UTF-8 JSON 包装保存。

本次复用未受影响的既有 Unity 编译和签名结果，只运行新版本判断、签名接口、启动入口及受影响原版资源工具。
