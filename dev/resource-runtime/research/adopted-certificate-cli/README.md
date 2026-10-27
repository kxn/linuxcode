# 可复用的原版 xcodebuild 证书入口

完整 Unity/CocoaPods 证书构建现在已通过整合 CLI 的 PATH 入口运行：`xcodebuild` 由 Linuxcode 启动原版 Xcode，保留 CI 参数并转换明确的主机路径。测试换用了新生成的 RSA 私钥与证书，七次原版 CodeSign 均完成，原生/外层退出码为 0，七个产物全部通过独立 CMS、CodeDirectory、页面与资源封装验证。本轮没有 CompileC 重编译，原来验证过的产物与工程保持完整。

## 使用

在已经组装好的完整实验工作区中：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt \
  --certificate-candidate config/native-certificate-candidate-v4.json \
  --identity-store runtime/my-signing/store.plist
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
```

随后保留原 CI 的 `xcodebuild` 命令。启动器不改签名身份、profile 要求、目标工程或构建动作；本次自签验证关闭 profile 要求的两个参数明确属于测试命令。主机工程仍须在工作区内。只读 RSA PKCS1 DER 身份库格式、私有文件权限和预览命令见整合工程的 `docs/install.md`。

`config/native-certificate-candidate-v4.json` 在原来六项运行组件之外，明确关联完整 Unity 原生构建、七项严格签名验证、独立验证及成功日志，并锁定之前已实测的私有目录映射启动器。选择其他未验证组件或更改成功证据会失败。adopt 与 dry-run 只选择配置，不创建签名服务或依赖旧测试私钥；实际构建按本次身份库生成独立的 SecurityServer/trustd 服务配置。

服务失败仍会中止启动，真实原生命令状态仍会传回。每次调用不再重复 UTI smoke 或列出全部服务。新产物仍验证所有 CMS、签名的 Apple hash-agility v1/v2、备用 CodeDirectory、页面与资源；未改动验证器的篡改控制复用上一轮证据，没有在本次重复执行。

## 文件与证据

- 整合入口：仓库根目录 `linuxcode/cli.py`、`linuxcode/certificates.py`。
- 独立运行准备：`scripts/native-certificate-runtime.py`；先选择配置，再为实际 invocation 创建服务。
- 完整 PATH 构建证据：`artifacts/unity-adopted-certificate-cli-milestone-v1.json`。
- 实际调用：`runtime/linuxcode-cli/20261027T133504-2447b81a/plan.json`、`result.json` 和 `output.log`。
- 七项独立新证书验证：`artifacts/unity-adopted-certificate-products-v1.json`。
- 四项新增入口检查覆盖其他组件冒充成功候选、缺失产品的绿色报告、预览创建服务、沿用旧身份库环境。

附件 `payload/` 与 `reference/original-file-map.json` 保留源码、精确配置及证据；参考附件为历史记录，不含证书、私钥、身份库内容或 Apple 二进制。

## 剩余范围

这仍是已有完整实验环境的入口，不是干净 Linux/XIP 的完整重建。身份库暂只支持 RSA，不提供 P12 通用导入、任意 keychain 写入或 provisioning 安装。真实 Apple 开发者凭据和设备信任尚未验证。原版 archive 正在单独推进；本入口的成功 build 不等于 archive/export 或 UE 已完成。
