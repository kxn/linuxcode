# 模拟器工作组、平台零值比较和目录相对节点操作

保持纯 Linux x86_64、无图形界面、原版 ibtool/IBAgent 与原始 Unity Storyboard。此检查点连续跨过三个实际加载阻塞，源码、可重复构建工具和失败记录都保存在独立整合仓库。

工作组回调注册及创建转发直接移植自 Apple 开源 libpthread，保留未安装或重复安装时的客户端错误行为。原生检查验证实际 pthread 创建/等待、参数原样转发、提供者错误和两个错误进程；工作组成员资格由实际 libdispatch 提供者负责，此探针的提供者是明确的测试实现。`_pthread_workqueue_allow_send_signals` 入口明确返回 ENOTSUP；没有沿用旧 bsdthread_ctl 的通用成功占位，也不声称支持该信号能力。

原版 libsystem_malloc 所需 `_platform_memcmp_zero_aligned8` 采用 Apple 开源的通用实现，生产文件与上游逐字节相同。完整48单元平台库源码构建保留原168个导出；宿主 ASan/UBSan 与 Darling 原生分别完成543616次独立字节、8字节对齐、零长度和保护页边界检查。宿主首次因 clang19 缺少 sanitizer 库链接失败，改用已安装 GCC；失败日志保留。完整平台库变化后另测9216个GCD任务与17秒线程回收，通过。

批量静态检查40个原版系统库，先核对模拟器包装库自有导出，再合并宿主内核/pthread/platform 导出，避免把包装库已实现的函数误报缺失。最终这三组命名导入缺口为零；这不等于全运行时ABI或行为正确，也不包括所有上层框架。随后真实运行进入 libarchive，继续发现 mkfifoat/mknodat。

节点操作实际调用 Linux mknodat，保留目录描述符、路径展开、创建权限检查、mode/umask 与 errno，转换 Darwin 设备号编码。两个入口均通过 FIFO 实际字节读写，另测相对/绝对路径、忽略绝对路径的无效dirfd、重复创建、空路径、无效指针、长路径、非目录等。首轮发现无效dirfd被旧解析器误报ENOENT，现已在新入口明确验证并修正；首轮失败保留。设备节点创建及完整 Darwin 特权策略未验证，不作为此里程碑的已支持能力。完整884单元内核构建通过。

新增系统调用还保存真实 gen/bsdsyscalls 文件和 syscalls.master 定义；通过上游生成器重新生成x86_64条目，避免只保存指向生成目录的符号链接。源码已推到 kxn/darling-xnu 原有 linuxcode/xcode-x86_64 分支，身份仍为 Comman Kang <kangxn@gmail.com>。

原版运行越过这些导入，下一处为原版 iOS Security 对 openat_authenticated_np 的需求，记录 runtime/original-storyboard-skx4sn9f/result.json，仍以255退出。完整 Storyboard、Unity App 和开发者证书签名仍未完成；默认安装环境未提升。

上游来源：[libpthread](https://github.com/apple-oss-distributions/libpthread/tree/42d026df5b07825070f60134b980a1ec2552dfee)、[libplatform](https://github.com/apple-oss-distributions/libplatform/tree/2512ffd8bb5c6caff3c8ea83331ab8a0adc820c3)。开发者需要此前研究基线和自行提供的Xcode/SDK/运行时。附件只有UTF-8源码、日志、报告和摘要，不含Apple/Unity二进制、SDK、XIP、core或私钥。
