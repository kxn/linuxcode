# 原版 XPC 回复与对端签名元数据

全部工作运行于 Linux x86_64 / Darling，使用原版工具。默认安装基线未提升，实际 Storyboard 和最终 Unity App 仍未生成。

原版 simdiskimaged 收到请求后记录“was not awaiting a reply”。精确指令断点证明 incoming Mach send-once 端口、引用计数和 xpc_dictionary_create_reply 返回值实际有效。原版 Swift 调用先 createReply(request)，再 remoteConnection(reply)，任一返回空值都进入相同日志分支。Darling 原有创建回复仅转移回复端口，漏掉关联连接；现将请求的弱连接关联复制到回复。旧库原生控制重现缺失，新库同步和异步控制均通过，并拒绝再次消费已转移端口。原版服务已经真实回复 GetVersion 1051.55 及其他镜像管理请求。

进一步运行触发原版 CoreSimulator 的对端权限读取断言。xpc_connection_copy_entitlement_value 原先仅返回空值。实现现在复制由真实 Mach 消息带来的对端 audit token，取得对应 task，核对服务器管理的 PID/version，读取已加载主程序头和 load commands，核对实际可执行文件，读取签名中的真实 XML 权限字典，并在读取前后重新核对进程身份和路径。复用此前自身签名解析器；同步回复也像异步回复一样保存真实发送者身份。没有写死原版服务权限或修改原版判断逻辑。

跨进程、具名 XPC 双向检查使用原版 codesign 分别签入客户端和服务端不同值：薄文件、FAT32 服务端的布尔真/假、字符串、数字、数组和字典在同步及异步查询中正确返回；缺少的值和未签名服务端均为空；更改 PID-version 或使用零 PID 均拒绝。服务端也确认自己读到的是客户端签入的另一组值。共享签名解析器的10个正例/损坏输入检查在地址及未定义行为检测器下通过。既有无关签名、Swift和编译对象检查没有重跑。

这是签名元数据读取兼容性，不包含证书链信任判断、内核权限执行或完整 Security 实现。进程身份与实际加载映像核对不会替代这些语义。FAT64 文件解析沿用已验证控制，未声称支持其 Darling 执行。原版 Storyboard 后续运行已越过对端权限断言，返回明确的 iOS 26.5 Platform Not Installed，退出1；没有 Storyboard 产品。现继续定位原版平台组件发现与运行时需求，最终构建成功尚未成立。

附件仅含UTF-8开发源码、日志和报告；Apple/Unity可执行文件、SDK、XIP、core、证书和私钥均不在附件中。source-history 保存被替换开发输入的精确历史。源码继续发布到既有 kxn/darling-libxpc 的 linuxcode/xcode-x86_64 分支，提交身份仍为 Comman Kang <kangxn@gmail.com>。
