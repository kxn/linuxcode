# Unity Data 完整复制、线程池竞态和原版 PNG 工具

完整 Unity/CocoaPods 工作区 DD74 已在 Linux x86_64 / Darling 中再次完成58项 C/C++ 编译、UnityFramework 链接和三次原版 CodeSign。此前 NFC/NFD 文件名问题已在实际 builtin-copy 中解决：2880个文件、160个目录全部复制，独立 SHA256 比对没有缺失、多余或内容不同；1018个文件名的规范化拼写不同。原始资源没有被我们重命名或修改。最终 App 尚未构建成功；本次返回65的实际失败是 CopyPNGFile。

DD73 的 core 最初停在收到重发信号的主线程，不能把这个 PC 当作原始异常。读取信号处理线程的 Linux ucontext 后，真实故障指令为 sys_workq_kernreturn+0x133，写入一个已经无效的停泊线程栈条目。core 中锁导入实际指向正常平台锁，没有选择同名空弱函数。源码中的信号量先原子减计数、再非原子写回 -1，会覆盖两步之间到达的 post；也会把 FUTEX_WAIT 的 EAGAIN/EINTR 当成超时。重复移除栈条目是与该 core 一致的因果推断，不是声称已证明所有线程池生命周期问题。

从真实生产函数原样提取的 Linux 测试在第2484轮握手失败，计数为 request=-1、reply=2。修复使用非负原子 token、futex 比较后等待，每次 post 唤醒一个等待者，重试被打断或值变化的等待，并用单调时钟保持原定超时。50000轮握手、512次并行等待、信号中断和一秒期限均通过。Darling 中真实 GCD 完成9216个回调及17秒空闲退出后的再次工作。旧后端同一 GCD 样本也通过；它是非确定性竞态的回归检查，不能伪装成确定复现。完整879单元内核仅 workq 对象变化，原有导出保留。源码提交 4d20a63011c1d7caf22ad4915e1ec7dc5c6f9c83 位于 kxn/darling-xnu 原分支，作者和提交者仍为 Comman Kang <kangxn@gmail.com>。

DD74 的原版 copypng 调用原版 pngcrush 时仍落入旧 CoreGraphics overlay，因缺 CGDataProviderCreateWithURL 失败。这个函数已存在于现有原版 CoreGraphics 候选，所以新配置 v131 仅将 copypng/pngcrush 加入精确可执行路径的资源环境选择；没有修改工具、图像内容、工程或 CI 操作。三个真实启动图和一个17×11彩色样本全部退出0；独立 PNG CRC、deflate、过滤和通道解码与 Pillow 源像素比较，190个像素全部相同。输入工具字节与 XIP 相同。样本均为不透明8位图，不能据此宣称所有颜色空间或 UIKit 输出正确。

## 开发验证

继承之前的 Unity 编译与 Unicode 路径检查点；默认安装候选没有升级。payload 相对于完整研究工作区，reference/original-file-map.json 提供原始 SHA256、UTF-8 包装位置及摘要标记。历史源输入应合并保存。摘要不是可直接启动的 stage，重建应选新目录和 tag，不能覆盖映射中的文件。Darling 原生执行和原生链接须串行。

```bash
python3 scripts/test-workqueue-semaphore-host.py
python3 scripts/probe-workqueue-recycling.py --configuration config/direct-resource-tool-environment-v131.json --stage artifacts/private-procfs-auditsession9-stage.json
python3 scripts/probe-original-copypng.py --configuration config/direct-resource-tool-environment-v131.json --stage artifacts/private-procfs-auditsession9-stage.json
```

像素核验脚本另需 Pillow 13.0.0，可安装在单独 venv；它只是 Linux 验证依赖，不参与 Xcode 的 PNG 转换。新完整参数为 v83 / DD75，结果须另行核验；Storyboard 输出、最终 App 和开发者证书签名仍未证明。公开附件没有 Apple/Unity 二进制、SDK、XIP、core、证书或私钥。完整候选的干净机器重建仍未完成。
