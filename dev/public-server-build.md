# 从公开固定源码构建 Linux darlingserver 组件

当前入口已在全新私有工作区，从网络获取六个公开仓库的准确提交，使用原有 `dev/linuxcode-dev build server --jobs 2` 和已公开的 `build-support/darlingserver` 成功构建含后续 S2C lifecycle 修复的 `577b168` server（stage108 所用源码）。29 个命令全部退出 0，没有复用已有目标文件。产物是 Linux ELF64/x86_64；六个源码仓库的实际 HEAD 均匹配所选提交，包含未跟踪文件的 Git 状态均为空。没有从本机原 vendor 或受保护 build 复制源码或生成头，没有修改这些公开源码。较早 `ed13f21` 的源码和产物证明保留；原版 UE/Unity 的运行验证仍由独立候选和证据描述。

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
| kxn/darlingserver：含既有 VM 统计、等待交接、S2C 中断与后续 lifecycle 修复的 server | `577b168d4c9a3af676fd4c9e859d70d2f56924ee` |

前三个 Darling 子仓库的 SHA 和 URL 均按公开主仓库的 gitlink 与 `.gitmodules` 校验。`Developer/Platforms/.../MacOSX.sdk/usr/include` 在这里是 Darling Git 仓库内的公开源码头文件/符号链接布局，不是从 Xcode 拷贝的私有 SDK。最初的稀疏取源遗漏这个布局、XNU 和 pthread 后，MIG 编译分别报缺 `mach/boolean.h`、`sys/_pthread/_pthread_types.h`；补取相应公开提交后完成编译，没有用本机未发布头文件填补。没有下载其余不参与该组件构建的全部 Darling 子模块。

生成的 Linux server 位于 `WORKSPACE/runtime/developer/server/darlingserver/darlingserver`。原有开发工具在该目录写入 `build.json`，其中 `milestone` 固定为旧 `375e52e` 标签；它不能代表这里的全部源码选择。新入口另写 `WORKSPACE/runtime/public-server-build/result.json`，明确列出六个所选 commit、实际 HEAD、tree、origin、dirty 状态、Git 对象是否借用本地 alternates、完整命令/状态及输出 SHA；源码锁和构建支持也检查 SHA。该记录才是这条入口的源码选择依据，不声明旧 `doctor` 的 17 仓库 exact checkpoint 已通过。

对已完成的构建，只读重新核对即可：

```bash
python3 dev/build-public-server.py --workspace /path/to/EXISTING-public-server --inspect
```

检查会重新核对公开 commit、干净源码、子模块 URL/gitlink、Linux ELF 头和原构建收据，并审计 Ninja 记录的绝对及相对编译依赖。依赖必须属于已跟踪的公开源、该私有 build 的生成文件或系统宿主头；不能悄悄引入工作区里未跟踪的私有头。检查不会重新编译、执行 server 或判断它能够启动完整用户态。

[stage108 源码构建摘要](../validation/public-server-stage108-source-build-2026-10-28.json)保存当前实际产物、六仓库来源与干净状态，编译依赖审计包含 731 个公开源码、116 个本次生成文件和 533 个系统宿主头。较早的 [ed13f21 验证摘要](../validation/public-server-source-build-2026-10-28.json)及对应工作区 HEAD/ELF 保持原样；它对应当时的锁，不能用当前新锁重新解释。旧次构建在发现头文件依赖闭包遗漏后，曾只复用同一个新工作区内先前尝试生成的对象；当前这次使用完整已知依赖闭包在另一全新目录一次构建。

原有 UE/Xcode 构建、系统运行前缀和受保护 server build 保持独立。这份新公开源码构建没有执行 server 或重复 lifecycle 原生回归，也不证明新产物已运行 UE/Unity。成功的 Linux 组件编译不等于完整运行候选已装配、UE App 已完成或完整冷 Darling/Xcode 重建已解决。
