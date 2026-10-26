# 原版磁盘服务：控制器枚举、注册表迭代与服务名所有权

沿用先前 Swift 与 IOKit 检查点，所有操作在 Linux x86_64 / Darling。未提升默认安装环境，原版 Storyboard 和完整 Unity App 仍未生成。

真实 DiskImages2 的两代枚举会查找 AppleDiskImagesController 和 IOHDIXController。两者现为 Darling 管理映像的注册表命名空间，尚无 attach 后端，空媒体和 unsupported 打开错误有真实检查。原版旧代枚举进一步暴露 iokitd 迭代器错误：起点本身被作为第一个结果，控制器被误作磁盘项，因缺少 IOHDIXHDDriveNub 报153。没有伪造这个磁盘节点。对照现有 XNU 开源 IORegistryIterator 实现后，迭代从子/父关联条目开始，遵守父方向与递归选项，并去重已访问条目。真实原版 DI1、DI2 均已返回非空数组对象、零个媒体、零错误；父方向及未知选项拒绝也通过。

原版 simdiskimaged 创建 listener 时服务名正确，随后 launchd 却出现 ImageManager.eventQueue 这个意外服务名。源码发现 initForService 保存了借用的 const char 指针，Swift 临时 CString 释放后内存被复用。现在连接保存 strdup 副本，并在连接销毁时释放。原生客户端/监听端两个对照在旧库中均能复现覆盖；新库中覆盖和释放调用者缓冲后原名均保留。完整40文件库重建，真实原版磁盘服务现在以正确名字进入 activate，意外服务名消失。

激活以后，原版服务实际收到连接和请求。最新诊断明确记录 Dropping request ... was not awaiting a reply，因此当前重点是请求/应答能力与回复端口传递；不再把这个等待归因于没有激活或 Swift 任务未执行。授权会话仍有 -60008 日志，但当前日志已证明请求先在回复能力判断处被丢弃，不能据此直接把所有 Security 功能列为当前必做项。

只重测改动影响的路径。已通过且未改动的签名、Swift并发、框架原始字节及格式验证均复用；后续完整构建准备复用现有 Unity DD76 的 DerivedData。82个环境选择器的摘要缓存把一次环境选择从带cProfile测得的约41秒降到另一进程复用时的约4.5秒，详见 runtime-verification-cache。

源码提交见 reference，身份保持 Comman Kang <kangxn@gmail.com>，继续使用现有仓库和分支。payload/reference 只包含UTF-8开发源码、日志和报告，不含 Apple/Unity 二进制、SDK、XIP、core、证书或私钥；仍依赖先前检查点与用户自行提供的 Apple 输入。
