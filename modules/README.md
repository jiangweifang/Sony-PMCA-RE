# QEMU：使用自己的 J1 fork

`qemu` 子模块使用
[jiangweifang/a7c2-re 的 qemu-cx89700-j1 分支](https://github.com/jiangweifang/a7c2-re/tree/qemu-cx89700-j1)。
J1 改动已经提交在 fork 内；父仓库用 gitlink 固定具体提交，不再依赖外部补丁。
本次父仓库变更也在 `qemu-cx89700-j1` 专用分支，不修改任一仓库的 `main`/`master`，
不向原作者推送或创建 PR。

## 获取或更新

首次 clone 时选择父仓库的专用分支，然后只初始化本任务的子模块：

```bash
git clone --branch qemu-cx89700-j1 https://github.com/jiangweifang/Sony-PMCA-RE.git
cd Sony-PMCA-RE
git submodule update --init -- qemu
```

已有父仓库工作目录时：

```bash
git fetch origin
git switch qemu-cx89700-j1
git pull --ff-only origin qemu-cx89700-j1
git submodule sync -- qemu
git submodule update --init -- qemu
```

`sync` 将旧的上游 URL 更新为自己的 fork。不要使用 `--remote` 代替固定提交更新。
如果子模块中已有未提交改动，先自行保存；冲突时停止，不用 `--force`、reset 或清理覆盖它们。

## 旧脚本入口

历史入口保留，**现在只做版本与 J1 预设校验**：

```bash
bash modules/apply-qemu-patch.sh
```

它检查子模块是否初始化、是否匹配父仓库索引记录的提交，以及该提交是否包含 J1 预设。
它不会应用补丁、更新子模块、切换分支或覆盖文件。
旧 `qemu-j1.patch` 的全部改动已保存在 fork 的提交历史中，因此移除重复补丁。

## 在原生 Ubuntu 运行

独立安装、原始输入、构建和运行说明现位于 fork 内：

- [本地 Ubuntu 使用说明](../qemu/README.ubuntu.zh-CN.md)
- [GitHub 上的 Ubuntu 使用说明](https://github.com/jiangweifang/a7c2-re/blob/qemu-cx89700-j1/README.ubuntu.zh-CN.md)

原始固件、私有日志、生成的 runtime 和大体积 QEMU 源码归档仍不由 Git 传输，
需要另外准备。不要把它们公开上传。

WSL Ubuntu 24.04 已完成离线构建、QMP 输入自测、J1 资产校验和 UTC+9 虚拟时钟读回/推进。
使用原始 J1 seed 的受控菜单入口已取得英文菜单截图，窗口正常退出；
这不是日版自然开机/日语首设或中文恢复通过。原始语言可用位与当前语言字段的区别、
已验证修正及保留的黑帧失败记录见上述本地 Ubuntu 使用说明，不沿用上游 ALLLANG 验收结论。
J1 两个中文位仍为原始关闭状态，不自动解锁或补字库。
不连接相机、不使用机身 root、不将任何实验产物写回机身。

用户后续批准的本机 TCP Backup 实验已由 PMCA 调用原生 API 验证
1/35 → 35/35，未改 seed、地区、字体或当前语言。
这不是 USB 服务认证或中文恢复；步骤、代码入口与有限结果见
[PMCA TCP Backup 实验记录](../qemu/report/2026-10-17-qemu-native-camera/PMCA-BACKUP-TCP-EXPERIMENT.md)。

2026-10-27 用户重新选择 Windows PMCA 与原生 Sony USB 服务链。
PMCA QEMU USB 客户端已补服务类和控制请求，并通过 Windows 离线测试；
这不是 USB 设备端实现，也不会创建 Windows 虚拟相机。
原 DWC3/gadget、枚举、认证与语言写入仍未接通，不采用 Backup RPC 代理冒充通过。
详见 [原生 USB 分层状态](../qemu/report/2026-10-17-qemu-native-camera/QEMU-USB-SERVICE-CHECK.md)。
