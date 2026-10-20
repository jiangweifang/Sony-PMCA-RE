# ILCE-7CM2 2.01 中文修复：离线交付与操作说明

> **更新：当前交付包仅用于离线预览，不要连接机身执行检测、修复或恢复。**
> 进一步分析原始 2.01 固件后，发现三张内置服务命令表均未包含当前 PMCA
> 文件访问使用的 `0xFF01`。固件确有另一套 Jiritsu 普通文件接口，其字体读写路径
> 可以与自定义代码加载分开，但尚未完成本工具的接口适配及实机验证。
> 之前的模拟测试不能验证这一通信兼容性。下面的界面和操作步骤是实验设计说明，
> 不是当前版本可以用于机身的批准。
>
> 后续只考虑不获取额外 root、不注入载荷的固定字库文件访问。
> 不修改或刷写 DAT，不使用 Firmware Updater，不改地区，不开启 Telnet 或 ADB。

## 当前状态与适用范围

这是 Sony-PMCA-RE 的实验性专用修复，不是官方固件，也不是“保证不会变砖”的工具。

- 仅支持 **ILCE-7CM2、固件 2.01、CX89700_J1 日版预设**。
- 会核对机身型号、版本、服务库和原始字体的哈希。
- 不修改启动程序、核心固件代码、地区或校准参数。
- 如果两个中文语言位已经开启，**不会回写设置备份**。
- 如果中文语言位未开启，现有接口需要回写设置备份；不能把这一情况称为“只写两个字节”。
- 原有 GUI 的语言解锁逻辑未改动，不会自动触发修复。
- 新增独立的按钮式中文恢复界面，不提供 Firmware Updater、地区修改、Telnet 或 ADB 入口。

已通过离线测试，但**尚未连接相机验证中文菜单及冷启动**。目前只能称为有静态证据、
有失败回滚测试的实验性修复，不能称为已确认解决了实机重启。

## 交付文件

新增的 Windows x64 专用图形界面位于：

```text
dist\chinese-recovery-gui\pmca-gui-chinese-recovery\
```

双击其中的 `pmca-gui-chinese-recovery.exe` 即可打开窗口，不需要输入命令。
程序打开后不会连接相机，也不会加载应用商店。
它只显示恢复页面，不显示原有程序的固件更新、Tweaks 或应用安装页面。
专用 GUI 版本标识为 `d209a3d-chinese-recovery-gui-experimental-20261020`，
与之前的命令行包分开交付。请使用新的 GUI 包，不要把旧版通用界面当作这个受限窗口。

之前交付的命令行版本仍位于：

```text
dist\chinese-recovery\pmca-console-chinese-recovery\
```

必须保留整个文件夹，特别是 `_internal`，不要只复制里面的 EXE。
该目录包含 Python 运行时和 libusb 用户态库，无需另外安装 Python 才能启动程序，
但**不替你安装或更换相机 USB 驱动**。

之前命令行版本的标识为：

```text
d209a3d-chinese-recovery-experimental-20261020
```

构建未使用代码签名。若系统拦截，请核对来源和校验值，或改为从已审阅的源码运行；
不要为了运行它关闭安全防护。

交付不包含相机固件、Sony 字体、个人机身备份或自动写入脚本。

## 按钮界面怎么用

界面沿用原程序的英文控件，含以下三行目录选择和三个操作按钮：

| 控件 | 含义 |
| --- | --- |
| Original font directory / Browse... | 选择从匹配固件中提取的原始字体目录 |
| New repair backup directory / Choose parent... | 选择备份的父目录；程序生成一个尚不存在的备份子目录名称 |
| Existing backup to restore / Browse... | 仅在撤销修复时，选择已有的恢复备份 |
| 1. Check (no writes) | 先检查机型、版本、中文字库和两个语言位；不需要选择目录 |
| 2. Repair Chinese... | 校验选定的字库与新备份路径，确认后执行修复 |
| Restore from backup... | 确认后，根据选定的本机备份恢复原中文语言位 |

每个操作都会弹出确认框，默认选择“否”。检测也需要进入服务模式；修复和恢复则明确
提示持久化写入、断电风险与实机验证尚未完成。取消确认不会连接相机。

运行期间，按钮及目录输入会禁用，窗口的普通关闭操作也会被阻止。
后台工作不会阻塞日志滚动；错误会显示在日志和弹窗中，不会伪装成成功。
完成后会自动退出该次服务模式操作，不打开交互式 shell、Telnet 或 ADB。

**固件更新、地区修改、Telnet 和 ADB 不属于本修复流程，不要调用它们。**
字体修复仍应在其他调整之后进行，避免后续预设备份操作再次删掉字体。

从源码启动相同的受限窗口：

```powershell
python .\pmca-gui.py --chinese-recovery-only
```

下面的命令行步骤作为备选方式保留；使用专用 GUI 时，无需手动输入这些命令。

## 第一步：只做离线检查

在交付目录打开 PowerShell：

```powershell
.\pmca-console-chinese-recovery.exe --version
.\pmca-console-chinese-recovery.exe --help
.\pmca-console-chinese-recovery.exe serviceshell --help
```

这三条命令不连接 USB，也不会进入服务模式。
`OFFLINE-TEST-RESULTS.txt` 记录源码测试结果，`SHA256SUMS.txt` 记录交付文件校验值。

如需重新运行模拟测试，在源码目录使用已安装项目依赖的 Python：

```powershell
$env:PMCA_TEST_FIRMWARE_ROOT = 'D:\GitHub\Sony-PMCA-RE\.firmware\analysis-201'
python -m unittest discover -s tests -p 'test_chinese*.py' -v
Remove-Item Env:\PMCA_TEST_FIRMWARE_ROOT
```

不设置环境变量时，只运行不需要固件的测试，真实固件数据测试会跳过。
模拟器使用内存中的设备状态和临时文件，不实例化 USB 驱动，不执行提取出的固件程序。
它覆盖备份操作删除字体、已解锁但字体丢失、通信失败、校验失败以及回滚失败等场景。

这些测试不模拟突然断电后的闪存状态、完整 BIONZ XR 硬件或 Sony 的全部启动校验。
**设置备份不是完整救砖镜像。**

## 第二步：以后连接机身时，先诊断

确认机身为 2.01，使用有数据功能的 USB 线，保证电量充足。
服务模式需要项目原有的驱动配置；不要未经确认就替换其他设备的驱动。
如果从未成功进入服务模式，先停止在这里，不尝试固件刷写命令。

从交付目录运行：

```powershell
.\pmca-console-chinese-recovery.exe serviceshell
```

进入 `>` 提示符后，仅执行：

```text
chinese check
exit
```

`chinese check` 会显示两个中文语言位和三个字体的状态，不发送预设备份读写命令，
也不主动写文件或设置。但进入服务模式本身不能被承诺为零风险。

判断原则：

| 诊断结果 | 下一步 |
| --- | --- |
| 型号、版本或服务库不匹配 | 停止，不绕过检查 |
| 中文位已开启，字体不可读取或哈希不符 | 与本修复针对的问题一致，但仍需明确同意写入后才能继续 |
| 中文位未开启 | 不能假定之前的多语言解锁包含中文；修复将涉及设置写入 |
| 中文位已开启，字体全部正确，但切换仍重启 | 停止重复修复，需要进一步分析，不能认定缺字库是唯一原因 |
| USB 或读取报错 | 保留错误输出，不将通信错误当作文件不存在 |

不要把常规 `info`、`tweak` 或任意预设备份读取当作本命令的等价替代：
固件的某些备份操作本身就可能删除中文字库。

## 第三步：仅在明确接受写入风险后修复

这一节不是要求现在执行。先完成诊断并审阅结果。

从你自己的匹配固件提取出的字体目录应包含：

- `MYingHeiC-GB18030-SJ_wIcon.ltt`
- `MYingHeiC-Big5-SJ_wIcon.ltt`
- `Sony_DI_Icons.ttf`

本次已提取的目录为：

```text
D:\GitHub\Sony-PMCA-RE\.firmware\analysis-201\firmware.tar_unpacked\0800_appli\tmp\images
```

在服务 shell 中执行，备份目录必须尚不存在：

```text
chinese repair "D:\GitHub\Sony-PMCA-RE\.firmware\analysis-201\firmware.tar_unpacked\0800_appli\tmp\images" "D:\GitHub\Sony-PMCA-RE\.firmware\camera-recovery-001"
exit
```

执行期间不要拔线或断电。修复会先保存原设置和可读取的受影响字体，再完成设置操作，
最后恢复字体并回读校验。已开启的语言位不会重复写入设置。

**修复必须放在其他调整操作之后，完成后立即退出服务模式。**
此后再次使用普通 `tweak` 或其他工具读写预设备份，仍可能重新触发固件删字体的路径；
本专用命令不拦截其他工具。

若有错误，先保存输出和备份，不继续选择中文。`rollback_failed` 表示回滚未能验证，
不是成功状态；不要反复尝试刷写或跨机型、跨地区替换备份。

## 第四步：实机验收与撤销

只有完成以下检查，才能确认这台机身上的修复有效：

1. 退出服务模式后关机，再正常开机。
2. 选择简体中文，不重启。
3. 检查多页菜单，确认文字正常。
4. 关机、等待、再开机，确认中文仍正常。
5. 验证拍照、录像和正常 USB 使用。

成功回读文件不等于通过这些测试。

撤销本次对两个中文语言位的修改：

```text
chinese restore "D:\GitHub\Sony-PMCA-RE\.firmware\camera-recovery-001"
exit
```

此操作会验证备份属于同一机身，保留之后改变的其他设置，并在备份目录下新建
`restore` 子目录保存撤销前状态。该子目录不能已经存在。
原来无法读取的字体会保留匹配的替换文件，不会为了“恢复原状”把它们删除。

请勿使用 `firmware` 或 `updatershell` 命令来执行本修复，也不要把字体或设置备份
当作整机固件写入。

完整的机制、哈希、失败处理与测试边界见
[技术说明](ChineseLanguageRecovery.md)。
