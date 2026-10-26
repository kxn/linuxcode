# 工作区间实例的真实元数据与后端错误

原版模拟器 libdispatch 缺少 work_interval_instance_set_complexity。Darling 原有 instance 函数是返回空对象/预设成功的占位实现，本次按完整方法组补齐16个分配、清理、时间/复杂度、读取、遥测、开始/更新/结束入口，继续保持纯 Linux x86_64、原版工具及原工程/CI 参数。

Apple 公开 XNU 头提供工作区间的公开契约，但没有这组私有 instance 方法的完整实现。这里依据已有 Intel 原版参考库核对96字节载荷、64位字段、偏移、操作码6/7/8及条件行为，独立实现兼容代码。参考摘要和有限范围反汇编记录保留；没有打包参考二进制。clear保留所属工作区间、标志和遥测；读取指标在实例ID为零时返回零；finish在真正调用后清理指标并保留后端返回值。这些具体行为均由参考核对，未自行设计另一套生命周期。

ASan/UBSan 单元测试验证分配、超过32位的字段、96字节载荷、回写实例ID、遥测边界、inactive/ignored分支、参数错误与后端失败传播。单元后端是明确的测试替身，不作为实际内核调度成功证据。原生测试另行验证全部导出及真实 work_interval_create 的未实现能力错误：BSD499内核性能控制后端仍未实现，没有将它转换成成功，也不声称提供 Apple 性能调度。

首次完整内核构建因基础内核库不提供calloc而链接失败，后续改用已有malloc和明确清零；失败日志保留。修正后的881单元构建与原生检查通过。新增 include 的内容摘要也写入构建记录，避免只记录外层翻译单元。源码发布到 kxn/darling-xnu 原有 linuxcode/xcode-x86_64 分支，提交身份为 Comman Kang <kangxn@gmail.com>。

原版 Storyboard 现已越过这组接口，下一处是原版模拟器 libdispatch 的 __pthread_workqueue_add_cooperativethreads 缺失，真实记录为 runtime/original-storyboard-reicage7/result.json，仍以255退出。完整资源编译与 Unity App 仍未完成，默认安装候选未提升。

开发者需要此前研究基线与自行提供的 Xcode/SDK/运行时。附件仅含 UTF-8 源码、报告、日志和摘要，没有 Apple/Unity 二进制、SDK、XIP、core、CMS 或私钥。未重跑未受影响的旧 Unity、Swift 或签名测试。
