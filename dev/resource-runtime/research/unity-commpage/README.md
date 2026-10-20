# Unity 编译器启动与固定 commpage 地址

DD75 中原版 Clang 在 libmalloc 初始化时除零。core 中故障为 `_malloc_initialize+0x3e`，读取固定地址的物理 CPU 数为零；真正含16个 CPU 和 commpage 签名的页面却位于别处。Linux 初始栈因 ASLR 占住 Darwin 固定地址，Darling 原来的 mmap 只把该地址作为提示，未检查返回地址，随后 macOS 库仍读取固定地址。

修复保留原来的 commpage_setup 接口。只有碰到 Linux 初始栈、且目标页面完全低于初始 argc/argv/env/auxv 区时，才保留临时 commpage。加载器切换到已准备的 Darwin 栈后，用真实 mremap 将该页面放到固定地址，然后恢复精确的入口栈指针并进入原版 dyld。其他冲突显式失败，不能覆盖仍活跃的数据或无关映像。没有修改 Apple 二进制、伪造 CPU 数或吞掉算术异常。

使用真实 Linux mmap/mremap 的测试强制地址冲突，旧实现返回12，固定地址仍为空；新实现通过空闲地址、可退役初始栈、无关映射拒绝、活跃参数区拒绝和精确入口栈指针检查。仅 /proc/self/maps 的碰撞元数据由测试提供；不能把它称为原生 Darling 强制碰撞复现。原有动态描述符限制回归（256个并发往返）仍通过。完整5单元 loader 源码构建完成，新候选单独放在 auditsession10，不覆盖正在使用的文件。

此前失败的原版 Clang 命令在新候选下重放，CMVideoSampling.mm 已成功生成目标文件。它使用原有参数和响应文件，仅将输出写到独立目录。完整 Unity 构建正在用 v84 / DD76 参数重新验证；最终 Unity App 与实际 Storyboard 输出尚未证明。

已产出的 DD74 UnityFramework 和两个 CocoaPods 静态库另经原版 codesign --verify --strict --verbose=2 全部返回0，独立内容哈希和资源封印检查也通过。这仍是 ad-hoc 签名，不代表开发者证书、设备信任或最终 App 已验证。

源码提交 ec73ed5ac463f0324c1c167a5c7a30c716789b6c 已推送至 kxn/darling 原有 linuxcode/xcode-x86_64 分支，作者和提交者均为 Comman Kang <kangxn@gmail.com>。参考输入和逐字节摘要在 reference/original-file-map.json；UTF-8 包装的历史内容需按原始路径恢复。source-history 应合并保存。stage 摘要是研究记录，不是可直接启动的完整 stage；完整重建仍依赖前序检查点。默认安装候选没有升级。

```bash
python3 scripts/build-mldr-source.py
python3 scripts/test-mldr-fixed-commpage.py --build runtime/新构建目录/build.json
python3 scripts/test-mldr-dynamic-rlimit.py --build runtime/新构建目录/build.json
python3 scripts/stage-fixed-commpage-runtime.py --parent-stage artifacts/private-procfs-auditsession9-stage.json --loader-build runtime/新构建目录/build.json --tag 新标签
```

Darling 原生运行与 Apple 原生链接须串行。公开附件没有 Apple/Unity 二进制、SDK、XIP、core、证书或私钥；core 仅留在本地诊断。
