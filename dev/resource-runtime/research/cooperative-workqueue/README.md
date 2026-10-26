# 协作工作线程与完整 pthread 源码构建

原版 iOS libdispatch 需要 `_pthread_workqueue_add_cooperativethreads`。本次补齐实际 op0x30 请求，将 cooperative 标记从新建/复用工作线程传到 dispatch 回调；TSD 的 QoS 保持普通线程编码，回调单独增加0x08000000。原有线程信用、停车、超时和唤醒机制继续复用。没有宣称实现 Apple 的完整协作调度策略，也没有新增能力位。

新增完整13个翻译单元的 pthread 构建器，采用原有 CMake 源列表、别名定义和 Apple 链接器，保留原194个导出并新增协作入口。前两次构建因私有 System 头路径、缺少 PLATFORM_MacOSX 而失败；日志保留。完整内核881单元并行构建通过，私有版本均未替换默认安装环境。

原生检查执行256次新旧请求交替，两个 QoS 类别，准确校验回调标记、TSD、计算结果、EPERM/EBUSY 与255次线程复用。另行验证 pthread 三个上游别名和真实创建/等待，以及9216个GCD任务、停车复用和17秒空闲回收。没有重复运行未修改的签名、Swift或Unity全量检查。

原版 ibtool 随后越过此处，下一处为 pthread_install_workgroup_functions_np；实际报告 runtime/original-storyboard-1s96ve5w/result.json 仍以255退出，没有 Storyboard 或完整 Unity App 成功声明。

内核源码提交到 kxn/darling-xnu 原有 linuxcode/xcode-x86_64 分支；pthread 与独立构建/验证工具的源码保存在本整合仓库附件中，提交身份为 Comman Kang <kangxn@gmail.com>。附件仅包含 UTF-8 源码、报告、日志和摘要，不含 Apple/Unity 二进制、SDK、XIP 或私钥。
