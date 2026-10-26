#!/usr/bin/env python3
"""Save only reviewed UTF-8 source and evidence for Intel simulator loading."""
from pathlib import Path
import argparse,hashlib,json,shutil
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--storyboard',required=True);a=p.parse_args()
repo=root/'distribution/linuxcode';overlay=repo/'dev/resource-runtime';folder=overlay/'research/simulator-dyld-registration';assert not folder.exists();folder.mkdir(parents=True)
sha=lambda b:hashlib.sha256(b).hexdigest();mapping={}
def attach(name,payload=False):
    if name in mapping:return
    source=root/name;data=source.read_bytes();text=data.decode('utf-8')
    relative=('payload/' if payload else 'reference/')+name+('' if payload or name.endswith('.json') else '.json')
    target=folder/relative;target.parent.mkdir(parents=True,exist_ok=True)
    if payload:shutil.copy2(source,target)
    elif name.endswith('.json'):target.write_bytes(data)
    else:target.write_text(json.dumps(dict(original_path=name,original_sha256=sha(data),encoding='utf-8',text=text),ensure_ascii=True,indent=2)+'\n')
    mapping[name]=dict(sha256=sha(data),attachment=relative,wrapped_utf8=not payload and not name.endswith('.json'))
sources=[
 'scripts/extract-dyld-version-map.py','scripts/build-libdyld-source.py','scripts/probe-dyld-version-sets.py','scripts/runnable-archs-profile.py',
 'fixtures/hello/dyld-version-sets.c','vendor/darling/src/external/dyld/dyld3/DarlingVersionMap.h',
 'scripts/build-simulator-signature-server.py','scripts/test-simulator-dyld-signature-host.py','scripts/probe-simulator-dyld-signature.py','scripts/build-dyld-bootstrap-fcntl.py','scripts/stage-dyld-bootstrap-fcntl.py',
 'fixtures/hello/simulator-dyld-signature-host.cpp','fixtures/hello/simulator-dyld-signature-native.c','fixtures/hello/simulator-dyld-signature-bootstrap.c',
 'vendor/darlingserver/CMakeLists.txt','vendor/darlingserver/scripts/generate-rpc-wrappers.py','vendor/darlingserver/src/call.cpp','vendor/darlingserver/src/file-signatures.cpp','vendor/darlingserver/internal-include/darlingserver/file-signatures.hpp','vendor/darlingserver/internal-include/darlingserver/apple-code-signing-roots.hpp',
 'vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/fcntl/fcntl.c',str(Path(__file__).relative_to(root))]
for name in sources:attach(name,True)
attach('vendor/darling/src/external/dyld/dyld3/APIs.cpp')
evidence=[
 'artifacts/dyld-modern-version-map-reference-v1.json','artifacts/dyld-modern-version-sets-source-publication-v1.json','artifacts/libdyld-modern-version-sets-v1-build.json',
 'artifacts/simulator-signature-server-source-publication-v1.json','artifacts/simulator-signature-kernel-source-publication-v1.json','artifacts/simulator-signature-kernel-v1-build.json',
 'runtime/simulator-signature-server-j6wjzv8k/stage.json','runtime/dyld-sim-signature-reference-v1/metadata.json','runtime/dyld-bootstrap-fcntl-component-v3/build.json',
 'artifacts/dyld-bootstrap-fcntl-launcher-v1-stage.json','artifacts/dyld-bootstrap-fcntl-launcher-v2-stage.json',
 'config/direct-resource-tool-environment-v145.json','config/direct-resource-tool-environment-v146.json','config/direct-resource-tool-environment-v147.json',
 'artifacts/private-procfs-auditsession33-stage.json','artifacts/private-procfs-auditsession34-stage.json',
 'runtime/dyld-version-sets-3wekolsl/result.json','runtime/original-storyboard-2kru1viv/result.json',
 'runtime/simulator-dyld-signature-controls-k2_2l60y/result.json','runtime/simulator-dyld-signature-native-xoh00e6n/result.json',
 'runtime/original-storyboard-1yriecnx/result.json','runtime/original-storyboard-qdkfe_98/result.json',
 'runtime/simulator-dyld-signature-native-opa54kqq/result.json','runtime/simulator-dyld-signature-native-o6f189s3/result.json',a.storyboard]
for name in evidence:
    attach(name)
    record=json.loads((root/name).read_text())
    if isinstance(record,dict) and isinstance(record.get('log'),str) and (root/record['log']).is_file():attach(record['log'])
for name in ['runtime/simulator-signature-server-j6wjzv8k/build.log','logs/simulator-dyld-signature-host-controls-v1.log','logs/simulator-signature-kernel-v1-driver.log','logs/dyld-bootstrap-fcntl-component-v2-driver.log','logs/dyld-bootstrap-fcntl-component-v3-driver.log','logs/simulator-dyld-signature-bootstrap-native-v1-driver.log',
 'runtime/dyld-bootstrap-fcntl-launcher-v1/darling','runtime/dyld-bootstrap-fcntl-launcher-v1/runtime-ns.sh','runtime/dyld-bootstrap-fcntl-launcher-v2/darling','runtime/dyld-bootstrap-fcntl-launcher-v2/runtime-ns.sh']:attach(name)
history=json.loads((root/'runtime/source-input-history/manifest.json').read_text());selected={n:history[n] for n in sources+['vendor/darling/src/external/dyld/dyld3/APIs.cpp'] if n in history}
for record in selected.values():
    for snapshot in set([record['snapshot'],*record.get('revisions',{}).values()]):attach(snapshot)
(folder/'reference/source-history.json').write_text(json.dumps(selected,indent=2)+'\n')
(folder/'reference/original-file-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
(folder/'README.md').write_text('''# Intel 模拟器加载器版本与文件签名登记

原版 Xcode / Storyboard 流程继续在纯 Linux x86_64 Darling 中运行，工程与 CI 参数保持。尚未生成最终 Unity App，不提升默认安装候选。

现代 dyld 版本集合原先只有截至 2021 年的表，SimLaunchHost 触发未知集合断言。新生成器从已有 Intel 参考 dyld 的实际 mapper 推导 40 字节步长和 61 条边界，核对两份表完全一致；源码库使用这些数值事实，未知未来集合返回零。完整 29 单元 libdyld 已重建，真实加载的三个不同 min/SDK 映像和主程序快速路径测试通过。该修改已经发布到 kxn/darling-dyld 原有分支。

下一步原版加载器需要 F_ADDFILESIGS_FOR_DYLD_SIM（83）。新服务通过 SCM_RIGHTS 接收实际描述符，读取调用者 LP64 参数，验证 Mach-O 的 LC_CODE_SIGNATURE、SuperBlob 边界/唯一槽位、Apple CMS 证书链、软件签名叶标记及用途、CodeDirectory、每个代码页和存在的特殊槽位，最后才记录签名和返回覆盖范围。信任锚为 Apple 开源 Security 中的三份公开根证书。按 AppleSoftwareSigning 的 Basic X509 / 默认代码签名语义，不单凭证书过期拒绝；未声称实现联网吊销查询、完整 AMFI、内核逐页执行约束或全部 CodeDirectory 形式。

真实 iOS 26.5 Intel dyld_sim 返回覆盖长度 639920。ASan/UBSan 下的真实文件及 13 个损坏/错误输入对照通过；原生动态库调用还验证了 SCM_RIGHTS、空/错误指针、错误范围、坏描述符和只读返回地址。源服务与完整 879 单元内核库已重建，代码分别发布到 kxn/darlingserver 和 kxn/darling-xnu 的 linuxcode/xcode-x86_64 分支，提交身份为 Comman Kang <kangxn@gmail.com>。

原版 Darling 主加载器静态带有另一份旧 fcntl，所以更新动态内核库不能覆盖启动阶段。新增构建脚本把同一份已测试 fcntl 源码及生成 RPC 链接成无动态导入、无重定位的 RX 组件，追加到固定版本的开源 Darling 加载器，并将原 syscall 入口的五个字节跳转到新实现。保留原有段、C++ 对象布局、符号地址和其他代码字节，逐字节限制允许变动的入口、头部和新增段；这是源码组件更新，尚非完整主加载器源码重建。未修改 Apple 工具或 Apple 模拟器加载器的内容。

首次把文件绑定到 overlay 的底层目录后，真实进程仍加载旧入口；失败记录保留。后续在 darlingserver 的实际挂载命名空间中绑定到合并视图，直接调用主加载器静态入口的七组原生测试全部通过，并读回新的入口字节。只影响当前私有会话。最新原版 Storyboard 的实际输出、退出码与未完成原因见 reference/original-file-map.json 中指定的最后一次 result.json；没有把局部成功当作完整构建成功。

复现先应用此前研究基线，再使用 payload 中的脚本与源码；主机服务新增依赖 libssl-dev / OpenSSL::Crypto，宿主校验使用 g++ 的 ASan/UBSan。build-dyld-bootstrap-fcntl.py 接收完整内核构建清单；stage-dyld-bootstrap-fcntl.py 创建独立挂载入口和新配置。开发者自行提供 Xcode、SDK 和运行时。附件只含 UTF-8 源码、公开根证书文本、摘要及报告，不含 Apple/Unity 可执行文件、SDK、XIP、CMS 输入或私钥。原始日志与历史源码用 UTF-8 JSON 包装保存。

本次复用未受影响的既有 Unity 编译和签名结果，只运行新版本判断、签名接口、启动入口及受影响原版资源工具。
''')
for name,row in mapping.items():
    data=(folder/row['attachment']).read_bytes()
    if row['wrapped_utf8']:data=json.loads(data)['text'].encode('utf-8')
    assert sha(data)==row['sha256'],name
manifest=overlay/'overlay.json';d=json.loads(manifest.read_text())
for path in folder.rglob('*'):
    if path.is_file():d['research_files'][str(path.relative_to(overlay))]=sha(path.read_bytes())
manifest.write_text(json.dumps(d,indent=2)+'\n')
print('PACKAGED',len(mapping),'attachments',folder)
