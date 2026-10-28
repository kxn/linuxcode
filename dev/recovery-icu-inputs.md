# 显式导入 Recovery ICU 输入

这个入口只补一个已确认的冷装配缺口：成功 Unity v12/stage101 链使用的既有 `stage-icu-data-runtime.py` 要求 Recovery 的 `icudt78l.dat` 和 `icutzformat.txt`，而旧 `prepare-recovery.sh` 的选择提取只覆盖 dyld 缓存、SystemVersion 和 codesign，没有导入这两个数据文件。Xcode XIP 也不含这些完整 OS 数据。新入口复用 Linux 7zip 的精确选择提取，不另写下载器、压缩格式或 ICU 实现。

已经使用本机显式提供的 26.6.2 / 25G83 `BaseSystem.dmg`，在全新的私有 runtime 目录完成真实提取。7zip 退出 0；两个 ICU 文件的长度和 SHA 与既有已验证阶段完全一致，附带的 SystemVersion 也匹配。没有运行旧 staging 脚本、Darling、Apple 工具或任何原生运行候选，没有占用会话锁，也没有读取身份库、私钥、授权或激活文件。

需要用户自己的准确 Recovery 镜像，以及 Linux 7zip。先查看选择，再执行：

```bash
python3 dev/import-recovery-icu.py \
  --image /path/to/BaseSystem.dmg \
  --sevenzip /usr/lib/7zip/7z \
  --output /path/to/NEW-WORKSPACE/runtime/recovery --plan

python3 dev/import-recovery-icu.py \
  --image /path/to/BaseSystem.dmg \
  --sevenzip /usr/lib/7zip/7z \
  --output /path/to/NEW-WORKSPACE/runtime/recovery
```

`--sevenzip` 指向实际 Linux ELF 可执行文件；若 `/usr/bin/7z` 只是发行版 shell 包装器，应使用其指向的 `/usr/lib/7zip/7z`。也可指向按已有 recovery 流程解包的 `.../runtime/tools/7zip/usr/lib/7zip/7z`。本次使用现有锁定 7zip 25.01，不需要额外解码库或运行中的 Darling。工具使用 `-mmt=1`，只请求锁文件中三个明确路径。

输出目录必须尚不存在，并位于 distribution checkout 之外。镜像长度和整文件 SHA 在创建输出或启动提取之前核验；不匹配就停止，不尝试使用新版“latest”替代。提取后再次核验每个文件的长度、SHA 和系统版本，拒绝选定路径中的符号链接和初次提取出现的额外文件。失败的私有输出和记录保留用于诊断；不会合并或覆盖已有 Recovery 树。

输出保留完整目录布局，能够直接喂给既有 consumer：

```text
NEW-WORKSPACE/runtime/recovery/
  macOS Base System/
    usr/share/icu/icudt78l.dat
    usr/share/icu/icutzformat.txt
    System/Library/CoreServices/SystemVersion.plist
  recovery-icu-import.json
  extract-7zip.log
```

因此在一个新工作区中，可先把尚不存在的 `runtime/recovery` 交给此入口；旧 `prepare-recovery.sh` 的 `mkdir -p` 和后续选择提取不会删除这两个 ICU 文件。它原有的下载、缓存提取和 Darling 步骤没有被本改动执行或修改；其 `latest` 查询仍可能获得不同版本，继续使用旧流程之前仍须解决该流程的准确输入和运行前提。不能把这份 ICU 导入记录当作完整 recovery、共享缓存或原生工具装配成功。不要向冻结候选的已有 `runtime/recovery`、prefix 或 App 合并测试输出。

只读复查已经导入的数据：

```bash
python3 dev/import-recovery-icu.py \
  --output /path/to/NEW-WORKSPACE/runtime/recovery --inspect
```

只读复查检查收据和三个锁定路径，不扫描或拒绝旧 recovery 流程后来添加的其他输入。它不会重新提取，也不会检查、执行或安装配套 `libicucore`。既有 stage 的完整资源版本配对、其他来源映像及运行库仍有各自的校验和装配前提。

[精确输入锁](locks/recovery-icu-25G83.lock.json)记录 960,530,321 字节镜像的 SHA256、两个 ICU 文件和版本元数据的 SHA/长度。建立这份 pin 时，复用了已有固定 OpenCore `macrecovery.py` 的原始离线验证代码：92 个 image chunk 和 Apple RSA 签名的 chunklist 均通过。普通导入每次核验的是同一镜像的固定 SHA，不下载 chunklist，也不声称每次重新验证签名；收据明确区分这两种证据。旧 recovery 公共 URL 探测曾出现 TLS 主机名或 chunklist HTTP 错误，完整准确下载仍未被这个入口解决。

[公开验证摘要](../validation/recovery-icu-explicit-import-2026-10-28.json)只保存 SHA、版本、命令、状态和边界。原镜像、ICU 数据、Apple plist 原件和提取日志仅保留在私有目录，不进入 source 包。此入口不更改 XIP 安装器、旧 `prepare-recovery.sh`、冻结的 v12/stage101 候选或默认运行选择；它不表示 XIP 单独足够，也不表示完整 Darling/Xcode 冷装配、Unity 重建或 UE App 构建已经通过。
