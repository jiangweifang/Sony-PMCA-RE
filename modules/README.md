# A7C II 2.01：原生 Ubuntu 离线 QEMU / CX89700_J1

`qemu` 是 Git submodule，固定在 `chocotan/a7c2-re` 的提交
`e43c4d0f66698db7640a80d7a680af5ac5e0291a`。本机只签出离线 QEMU 成果，
不使用上游的真机 root、USB 服务或更新工具。J1 改动保存在父仓库的
[`qemu-j1.patch`](qemu-j1.patch)，不创建上游 PR、不向作者推送代码。

**准备目标是原生 Ubuntu x86_64 + GUI，不使用 Windows QEMU 或 WSL。**
本次 Windows 侧校验不等于 Ubuntu 编译成功，也不等于 J1 菜单已经启动。
上游菜单验收使用 ALLLANG；J1 的初始化和窗口仍须在目标 Ubuntu 上验证。

## 本地适配内容

- 原始预设改为 `CX89700_J1`，不是给 ALLLANG 改名。
- 导入路径、输入摘要、两个 seed 副本、可信资产清单和清单摘要同步更新。
- `seed_policy=cx89700_j1`；拒绝 ALLLANG 清单及只改标签的输入。
- 打包前重新校验 runtime；删除旧研究设置自动混入的备用分支。
- 原始更新包、型号/版本校验、QEMU 设备模型和原固件输入保持不变。
- J1 原始简/繁语言位均为 `02`；本套件不自动解锁语言，也不自动补中文字库。
- 上游导入器仍会在**独立实验副本**中生成 IMDB 服务掩码变体和虚拟身份卷。
  这些不是原厂完整整机镜像，不能写回相机。

J1 原始输入为 2,390,264 字节，SHA-256：

```text
e02f7bba71d8fe9ecabfd8d0eb8b92cb8046e36d4783a70ad6e7a1c283edc811
```

## 带到 Ubuntu 的内容

保留以下相对布局，并放在支持 Unix 权限和符号链接的 Linux 文件系统中：

```text
Sony-PMCA-RE/
├── modules/                      本说明、J1 补丁与补丁应用脚本
├── qemu/                         submodule 工作目录，应用本地 J1 补丁
│   └── report/2026-10-17-qemu-native-camera/
│       ├── source/vendor/qemu-11.1.2.tar.xz
│       ├── build-qemu.sh
│       ├── import-assets.sh
│       ├── start.sh
│       └── runtime/
└── .firmware/analysis-201/        自己携带，禁止公开上传
    ├── extraction-manifest.json
    ├── firmware.fdat
    └── firmware.tar_unpacked/
```

Git submodule 本身只记录上游提交，父仓库中的补丁负责保存本地改动。
本次没有创建任何提交或推送；同步到其他机器前，需要由使用者决定如何保存和同步这些变更。
在包含本地补丁的父仓库根目录执行：

```bash
git submodule update --init -- qemu
bash modules/apply-qemu-patch.sh
```

脚本核对固定提交；已应用时直接报告，不重复打补丁。版本不匹配或冲突时停止，
不自动 reset、checkout、stash 或覆盖用户改动。不要仅在 Ubuntu clone 上游后直接启动，
那样得到的仍是 ALLLANG。

也可以直接复制本机已经修改过的 `qemu/`、`modules/` 和私有 `.firmware/`，
用于离线构建；只复制 submodule 工作目录不代表携带了父仓库的 Git 历史。
Sony 素材、生成的 runtime 和日志不属于开源代码，不得随公开源码发布。

所需 QEMU 原版源码已放在上面的 `source/vendor/`，摘要必须为：

```text
731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016
```

该归档不由 Git 传输。如果通过 Git 取回后缺少它，请另行复制本机归档，
或在成果目录从 `https://download.qemu.org/qemu-11.1.2.tar.xz` 下载到
`source/vendor/qemu-11.1.2.tar.xz`。构建器仍会强制核验上述摘要，不替换其他版本。

## Ubuntu 依赖

建议 Ubuntu 24.04 LTS 或更新版本，Python 3.12+、X11/Xwayland 桌面。
建议 32 GiB 以上 RAM、20–30 GiB 以上空闲空间；这不是测得的最低配置。
仅安装依赖时需要管理员权限，构建和运行使用普通用户。

在 Ubuntu 安装构建依赖，不要在 Windows 执行：

```bash
sudo apt update
sudo apt install build-essential clang lld ninja-build meson flex bison \
  pkg-config patch git python3 python3-venv python3-pip python3-setuptools \
  python3-wheel libgtk-3-dev libsdl2-dev libpixman-1-dev libglib2.0-dev \
  libseccomp-dev bubblewrap util-linux cpio e2fsprogs dosfstools
```

在本机复制后的仓库根目录打开终端，然后：

```bash
cd qemu/report/2026-10-17-qemu-native-camera
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

构建器会在无网络 namespace 中构建。QEMU 的 Meson 至少需要 1.5；
已核对原版源码归档自带 Meson 1.11.1、pycotap 1.3.1 和 qemu.qmp 0.0.6 wheel。
configure 可以使用其本地 wheel，不依赖在构建沙箱中联网下载，具体以输出为准。
若 bubblewrap/user namespace 被系统策略阻止，停止并保留错误；
不要关闭 AppArmor/安全策略，不要用 sudo 或 privileged 模式绕过隔离。

## 构建、导入、运行

以下命令仍在上述成果目录中执行。输入目录不应由其他进程同时改写。

```bash
FW_ROOT="$(realpath ../../../.firmware/analysis-201)"

# 先检查原始输入；只读文件，不构建、不导入、不启动 VM。
SONY_TEST_FIRMWARE_ROOT="$FW_ROOT/firmware.tar_unpacked" \
SONY_TEST_FDAT="$FW_ROOT/firmware.fdat" \
python3 runtime/analysis/test-assets.py \
  AssetsTest.test_actual_j1_inputs AssetsTest.test_actual_fdat_header -v

bash build-qemu.sh
bash import-assets.sh \
  --firmware-root "$FW_ROOT/firmware.tar_unpacked" \
  --fdat "$FW_ROOT/firmware.fdat"
bash import-assets.sh --check-runtime
python3 runtime/analysis/test-assets.py -v
bash start.sh
```

`--check-runtime` 成功时应明确输出
`CHECK_RUNTIME_PASS ILCE-7CM2 2.01 CX89700_J1`。
已有 ALLLANG runtime 不能覆盖升级，不要通过删除摘要检查来导入。
发生失败时停止，不自动清理旧目录，不换用真机备份。

GUI 默认 GTK。方向键导航，Enter 确认，M/Esc 返回，Delete 为已验证的帮助操作，
PageUp/PageDown 为后拨盘，F12 保存界面截图。截图不是固件拍摄的照片。
退出最外层菜单可能进入上游尚未恢复的拍摄初始化，不是完整实时取景。

## 验收边界

1. Ubuntu 上必须先确认构建自测和 `--check-runtime` 成功，再启动窗口。
2. 记录 J1 初始化能否完成、实际菜单语言、导航和退出结果；不能沿用 ALLLANG 验收结论。
3. 中文位默认关闭是 J1 原始状态，不是导入失败。中文显示与缺字体对照实验尚未实现。
4. 不连接相机、不直通 USB/实体 SD/物理磁盘，不将任何生成文件写回机身。
5. 模拟器结果不能证明机身字体状态、USB 接口可达性或实机修复安全。

更多上游设计限制见 [实验 README](../qemu/report/2026-10-17-qemu-native-camera/README.md)、
[构建说明](../qemu/report/2026-10-17-qemu-native-camera/BUILD.md) 和
[资产说明](../qemu/report/2026-10-17-qemu-native-camera/runtime/analysis/ASSET-IMPORT.md)。
