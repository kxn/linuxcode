# 从公开固定源码构建 Linux darlingserver 组件

当前入口已在全新私有工作区，从网络获取六个公开仓库的准确提交，使用原有 `dev/linuxcode-dev build server --jobs 2` 和已公开的 `build-support/darlingserver` 成功构建 `de357b0` server。该提交在原有 lifecycle、完成等待保留修复上实现 x86 Mach debug-state get/set。29 个命令全部退出 0，没有复用已有目标文件；产物为 Linux ELF64/x86_64，六个源码仓库实际 HEAD 均匹配所选提交，包含未跟踪文件的 Git 状态均为空。源码锁仅将 server 从 `4328b801` 更新到 `de357b0`，其他五仓库和构建工具固定值不变。新增 `linux-debug-registers.hpp` 和 `thread-debug-state.h` 均是已跟踪公开源码，并出现在真实编译依赖中。没有从本机 vendor 或受保护 build 复制源码或私有头，没有修改这些公开源码。此前 stage109/108 和 `ed13f21` 的源码、产物及成功证明保留；新编译的 ELF 未执行，原版 Mach API、UE/Unity 的运行验证仍引用独立候选及证据。

这是一个可复用的 Linux 组件源码构建入口，不是完整 Darling/Xcode 冷安装器。它不执行 server、Darling、Apple 链接器或任何原版工具，不获取全局 `runtime/session.lock`，不替换默认 server、prefix、运行候选或其他构建目录。

从整合仓库或公开 source 包根目录执行：

```bash
python3 dev/build-public-server.py --workspace /path/to/NEW-public-server --jobs 2 --plan
python3 dev/build-public-server.py --workspace /path/to/NEW-public-server --jobs 2
```

`--plan` 只打印命令；实际构建必须使用不存在的新工作区。入口限制并发为 1 或 2，复用现有 CMake/Ninja 构建逻辑，不安装宿主依赖、不应用补丁、不覆盖已有工作区。需要 Linux x86_64，以及[开发环境](README.md)列出的 Git、Python、Clang/LLVM 19、CMake、Ninja、Bison、Flex、M4 和 `libssl-dev` 等宿主依赖。验证机器使用系统 Clang 19.1.7 和 OpenSSL 3.5.7；Bison 3.8.2、Flex 2.6.4、M4 1.4.19 来自已解包的 Debian 工具包。它们是宿主编译依赖，不是未公开的 server 补丁。

如果使用已有的独立 Linux 工具前缀，可以显式指定：

```bash
python3 dev/build-public-server.py --workspace /path/to/ANOTHER-NEW-public-server \
  --jobs 2 --host-tools /path/to/host-tools/usr
```

该前缀应包含 `bin/`；Bison 对应的数据目录为 `share/bison/`。显式前缀优先于系统 PATH，避免 Bison 可执行文件与另一个版本的数据目录混用。入口清除外部 `DYLD_*`、`LINUXCODE_*` 和可能注入私有头文件或库的常用编译环境覆盖变量。所有输出仍在所选的新工作区内。

[独立源码锁](locks/public-server.lock.json)记录本次实际用到的源码，不跟随可变 HEAD：

| 仓库与用途 | 固定提交 |
| --- | --- |
| kxn/linuxcode：已公开的独立 server CMake 支持 | `375e52ea83e0f1a8dba3b16a0600d01292a9fe61` |
| kxn/darling：CMake/MIG 支持、rtsig、libsimple 和源码头布局 | `e6b769a692d6dd709557761369e0afe3964afccf` |
| darlinghq/darling-bootstrap_cmds：Linux 上构建 MIG | `0f300a7a04bb1174a3b7db58b57d738aadc14e13` |
| kxn/darling-xnu：配套公开头文件 | `75eabd3bedadac9873f26002421787d685084d42` |
| darlinghq/darling-libpthread：配套 `_pthread` 头文件 | `f07f265bfbcf071c1adfc808de971e053ea5edc5` |
| kxn/darlingserver：含既有 lifecycle/等待修复及 x86 Mach debug-state get/set | `de357b095584fbe9b24b37a404d691b1e4d872d7` |

前三个 Darling 子仓库的 SHA 和 URL 均按公开主仓库的 gitlink 与 `.gitmodules` 校验。`Developer/Platforms/.../MacOSX.sdk/usr/include` 在这里是 Darling Git 仓库内的公开源码头文件/符号链接布局，不是从 Xcode 拷贝的私有 SDK。最初的稀疏取源遗漏这个布局、XNU 和 pthread 后，MIG 编译分别报缺 `mach/boolean.h`、`sys/_pthread/_pthread_types.h`；补取相应公开提交后完成编译，没有用本机未发布头文件填补。没有下载其余不参与该组件构建的全部 Darling 子模块。

生成的 Linux server 位于 `WORKSPACE/runtime/developer/server/darlingserver/darlingserver`。原有开发工具在该目录写入 `build.json`，其中 `milestone` 固定为旧 `375e52e` 标签；它不能代表这里的全部源码选择。新入口另写 `WORKSPACE/runtime/public-server-build/result.json`，明确列出六个所选 commit、实际 HEAD、tree、origin、dirty 状态、Git 对象是否借用本地 alternates、完整命令/状态及输出 SHA；源码锁和构建支持也检查 SHA。该记录才是这条入口的源码选择依据，不声明旧 `doctor` 的 17 仓库 exact checkpoint 已通过。

对已完成的构建，只读重新核对即可：

```bash
python3 dev/build-public-server.py --workspace /path/to/EXISTING-public-server --inspect
```

检查会重新核对公开 commit、干净源码、子模块 URL/gitlink、Linux ELF 头和原构建收据，并审计 Ninja 记录的绝对及相对编译依赖。依赖必须属于已跟踪的公开源、该私有 build 的生成文件或系统宿主头；不能悄悄引入工作区里未跟踪的私有头。检查不会重新编译、执行 server 或判断它能够启动完整用户态。

[当前 server 源码构建摘要](../validation/public-server-stage113-source-build-2026-10-28.json)保存本次真实产物、六仓库来源与干净状态、29/29 命令结果和受新锁影响的入口测试。编译依赖审计包含 733 个公开源码、116 个本次生成文件和 533 个系统宿主头。本次使用完整已知依赖闭包，在不存在的新工作区内一次完成取源和构建。

较早的 [stage109 摘要](../validation/public-server-stage109-source-build-2026-10-28.json)、[stage108 摘要](../validation/public-server-stage108-source-build-2026-10-28.json)及 [ed13f21 摘要](../validation/public-server-source-build-2026-10-28.json)、对应工作区 HEAD 和 ELF 保持原样；它们对应当时的源码选择，不能用当前新锁重新解释。旧 ed13f21 构建曾在补足公开头文件闭包后复用同一私有工作区内的先前对象，不计入本次全新构建。

原有 UE/Xcode 构建、系统运行前缀和受保护 server build 保持独立。本入口验证公开源码依赖闭包与 Linux 组件编译；新编译产物的启动及 UE/Unity 运行需引用单独候选实测。此入口没有执行 server 或重复 lifecycle 原生回归，完整 Darling/Xcode 冷重建仍未在此验证。
