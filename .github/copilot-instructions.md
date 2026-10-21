# Sony-PMCA-RE：中文语言问题的只读交接指引

更新日期：2026-10-20。当前目标是调查 **ILCE-7CM2（A7C II）2.01** 能否在不获取额外 root 的情况下恢复中文字库。用户已经做过多语言解锁，准备换机器后进行只读诊断。不要扩展到 FL2/FL3、滤镜、快门声或其他功能。

## 当前授权边界：只读，不修复

- 禁止修改、重打包或刷写 DAT；禁止调用 Firmware Updater、`firmware`、`updatershell` 或更新版本门槛相关流程。
- 禁止修改地区代码、地区预设、校准数据、启动程序、系统共享库或机身设置。多语言已解锁不代表两个中文位一定开启，但只能读取确认，不能改写。
- 禁止获取额外 root、注入载荷、放置或加载自定义 `libJit.so`、修改 `ld.so.preload`、发送 DEBUG 或执行任意机内命令。
- 禁止开启或使用 Telnet、ADB、交互式 shell；不要另换 SSH、其他执行入口或隐蔽方式规避这些限制。
- 禁止向相机写入、删除、重命名文件，禁止创建“测试文件”、做写权限探测、格式化或执行修复/恢复。主机上的源码、测试和诊断输出可以写入。
- 不能因报错而自动写回备份、执行“清理”写入、改变权限或切换到上述禁止路径。
- 用户同意只读检测，不等于同意写入。若只能靠禁止操作继续，停止并明确报告，不擅自放宽边界。
- 使用相机原有服务权限不等于获得 root shell；不额外 root 也不代表访问低权限或没有风险。

## 先读这些状态说明

- [当前中文操作说明](../docs/ChineseRecoveryOffline.zh-CN.md)：顶部警告优先于下方历史操作示例。
- [技术证据与测试边界](../docs/ChineseLanguageRecovery.md)。
- **之前交付的命令行和 GUI 包只能离线预览，不能连接机身运行 `chinese check`、`repair` 或 `restore`。** GUI 显示“no writes”不能替代对实际通信链的审查。
- 现有代码曾通过 47 项离线测试，包括 17 项 Tk GUI 测试，以及 38 个通信失败注入位置；没有任何实机中文字库读取、修复或冷启动验收。模拟设备无法证明真实 USB 协议兼容。

## 2026-10-21 结论修正：改地区无效，区分 dat3 / 预设 / 语言位（chocotan 报告核对）

读了 chocotan `report/2026-10-21-developer-modes/`（README 的"两个坑"+ REPORT），与本仓库离线证据互相印证，修正并补充如下：

1. **改"区域码"不能解锁语言**（代码证实）：区域码 `dat3`（nflasha1 根目录，本机明文 `00000000`）唯一闭合调用链只用于**更新包匹配比较**（`libupdaterufp.so@0x1f34`）。语言可用性读 **Backup 区**（`backup_get_language_dst@0x35aa6bc`），与 dat3 无调用链。改 dat3/dat2（`modmod/modreg`）属更新器匹配层、且会动机型码（本机 `dat2=20030014`），**不要走这条路**。
2. **三个不能混的概念**：
   - 区域码 `dat3`（文件，仅更新匹配）
   - 地区预设名 `CX89700_J1`（Backup 预设，决定出厂语言默认值，官方 `J1.bin` 简/繁位=2）
   - 语言位 `0x010d0096/97`（Backup 区，运行时真正控制中文菜单项）
3. **菜单中文 = 改 Backup 语言位**，原生可回滚写入（PMCA `LanguageTweak` 同路线），不需要 root。本机实测两位=`0x02`（关闭）。
4. **真正难点仍是字体**：开语言位后中文菜单项会出现，但 `/tmp/images/*.ltt` 若已删，选中文仍重启。恢复字体只能写 `/tmp/images`，USB 服务模式无此路径（`0xFF01/0xFF03` 不在 A/B/C 权限表；`0x20 FirmwareUpdate` 空实现；`TERM_MODE`/内存命令被分派器拒绝），**唯一已验证途径是 libJit root**。
5. **删字体分支绑定 Backup 子系统**（本仓库 OSAL 表证实）：`libsencore.so` 的 `ReceiveOsalMessage` 在 OSAL 命令 `0x3e0166`、响应字节 `0xFF` 时 `remove` 六个 `/tmp/images` 字体。表项 `66 01 3e 00 | 03 06 NN` 对应 `0x603/NN`（02=WRITE,03=SAVE,04=PDT_WRITE,05=PDT_READ）。即**改语言位所做的 Backup 写入本身就可能再次触发删字体**；这解释了"先解锁全部语言、选中文后重启"。

**三方案对比（均在当前红线内，不执行）：**

| 方案 | 实质 | 更新后保留 | 变砖上限 | 红线 |
| --- | --- | --- | --- | --- |
| 防删除（拦截固件行为） | root 或 DAT 补丁常驻 | 需每次更新后重做 | 高（取决于实现） | root / DAT |
| root 写字体 + 开语言位 | libJit 代码执行 | 否（更新会重置+再删） | 中（取决于载荷正确性与写入安全） | root |
| 改地区 `dat3` | 更新匹配层，不控语言 | — | 牵涉机型码/换族，更危险 | 改地区，且**无效** |

区域码族说明：预设前缀=机型码。同机型码（CX89700）含中文地区有 E38/KR2/UC2/ALLLANG；CN1 属 CX897**01**（换族）。但按第 1 条，改 dat3 根本不解锁语言，此路否决。

## 2026-10-21 离线定论：2.01 无额外 root 无法读取/恢复字库

用专用环境独立复核了 `libJiritsu.so` 与 `libsencore.so` 的完整字符串表与路径映射，结论互相印证：

1. **旧文件接口不存在**：2.01 `libsencore.so` 的 pFunc 分发表只含 `0x10/0x20/0x30/0x40/0xff00/0xff02`，没有 `0xFF01`（FileControl）也没有 `0xff03`（MemoryDump）。旧 `readFile/writeFile` 与旧 `chinese check/repair` 在这台机身上不可用。
2. **唯一无 root 文件 I/O 被沙箱限制**：AdjustControl(`0x40`) 内的 Jiritsu `adj_cmd_get_file2`（读）、`adj_cmd_set_file`（写）、`adj_cmd_get_file_list`，路径经 `get_access_filename`/`get_jiritsu_area_filename` 按选择子映射到**固定清单**，基路径只有 `/tmp/jiritsu`（`/dev/nflasha6`）和 `/mnt`（存储卡）。`adj_cmd_set_file` 写入只允许 `/tmp/jiritsu/{jit.log,history.txt,libJit.so}`。
3. **libJiritsu.so 全字符串表无字体路径**：61 条绝对路径全部在 `/tmp/jiritsu/*` 或 `/mnt`，**不含任何 `/tmp/images` 或 `.ltt`**。字体路径只出现在 `libsencore.so`（6 条 `/tmp/images/*.ltt` 与图标字体），由应用按 `fontlist.dat` 加载，没有对应的"读文件"服务命令。
4. **字体在可写持久分区、删除永久**：`0100_config\mount.conf` 显示 `/dev/nflasha10 /tmp vfat`（约 12 MB，可写）。字体来自 `0800_appli` 应用镜像，在固件更新时写入 nflasha10，普通开机不重新复制。因此若被删除，重启不会自动恢复，需重刷固件或 root 写入。
5. **`libJit.so` 分支就是 root/代码执行路径**：`adj_cmd_set_file` 写 `/tmp/jiritsu/libJit.so` 后 `dlopen` 加载——正是 chocotan 的 root 机制，属红线，不采用。
6. **KikiLog 接口只读使用日志**（`libInfraKikiLogSender.so` 的 `InitKikiLog/ReadKikiLog`），不能读任意文件。

**结论（在"不额外 root、不加载 libJit.so、不改 DAT、不用 Updater、不改地区"的红线内）：**
- 无法通过现有服务接口**读取**这台机身的 `/tmp/images/*.ltt` 字体状态——读文件只有 `0xFF01`（不存在）或 Jiritsu（够不到该分区）。确认字体是否完好本身就需要越过 root 红线。
- 无法**恢复**被删字体到 `/tmp/images`——唯一无 root 写路径沙箱在 `/tmp/jiritsu`。
- 能读写的是语言位（备份属性 `0x603`，非文件）。本机实测两位均为 `0x02`（关闭）。
- 因此"无 root 恢复中文字库"在 2.01 上**不可行**；之前关闭简繁中文规避重启，在红线内其实是唯一的非 root 选项。若将来授权写入且字体恰好完好，把 `0x010d0096/97` 置 `0x01` 可开启中文（2 字节备份写，可回滚）；但字体是否完好无法在不 root 的情况下先行确认，若字体已删则选择中文仍会重启（断电重开可恢复，不致变砖）。

## 已验证的离线事实与未解决问题

1. 用户提供的原始更新包解析为 **2.01**，不是早先提到的 2.00；机身版本由用户报告已升级到 2.01，换机诊断时仍需读取确认。
2. 原固件含中文菜单资源和两个中文字库。应用字体配置分别指向 `/tmp/images/MYingHeiC-GB18030-SJ_wIcon.ltt` 和 `/tmp/images/MYingHeiC-Big5-SJ_wIcon.ltt`。
3. `libsencore.so` 的 `ReceiveOsalMessage` 在特定备份命令响应下会删除这些字体并改写内部响应。**“读取预设备份”可能有删文件副作用，不是本阶段允许的只读方式。**
4. 2.01 的三张内置服务命令表均未发现当前 PMCA 使用的 `0xFF01` 文件接口。不能继续依赖旧 `readFile`/`writeFile` 路径进行机身验证。
5. 原始 `libJiritsu.so` 确有路径选择、普通文件读取及写入处理函数。普通字体文件路径与自定义代码加载分支可以区分，支持“不另行 root”的可行性研究，但尚未完成本工具的接口适配或实机验证。
6. 外部 2.01 实现使用 Jiritsu 的 `0x40` 功能号、`0x1001` 分组，路径选择与读取分别使用 `0x0f`、`0x11`。这些是待核对的协议线索，不是可直接发送的批准；必须核对数据格式、普通文件子模式、响应和副作用。
7. `/tmp` 在本固件中是持久化 VFAT 挂载，不是可随意使用的内存临时目录。普通写入有截断语义；Work 目录配额不能证明字体所在卷有足够剩余空间。未解决空间与失败语义前，不进入写入阶段。
8. 尚未取得这台机身的真实字体状态或崩溃日志；不能把“缺字库”说成已证实的唯一重启原因。

用于核对原始参考文件的 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `BODYDATA.DAT`，1,139,929,560 字节 | `eb4943e6099754d64deaef5047942e9bfe258f232d0b7bc39fa23b3cd10e1e31` |
| `libsencore.so` | `3362d4b6e03dc517b04f1eb04d4199ff16d33f6e8f1bfddce657a375778d79e7` |
| `libJiritsu.so` | `87dc24912938be8dd59965e62306e79fdd8c672e10ed6f9734c88454b1d144a8` |

两个中文字库的大小和摘要见技术说明。文件名或版本字符串相同不等于内容匹配。

## 换机器时先准备

1. 确认操作系统、仓库位置、Python 和 USB 驱动状态；不要沿用旧机器的盘符、Copilot session 路径、虚拟环境或 REA 安装位置。
2. 先检查 `git status`，确认拿到了包含本指令、GUI、文档和 GUI 测试的完整提交。只拉取旧分支或尚未推送的本地提交，不能让另一台机器自动获得新文件。由用户决定如何同步，不自动提交或推送。
3. **用户最终决定排除整个 `.firmware` 目录，自己携带到新机器。** 原始 DAT、解包产物和该目录内的分析证据都不随 Git clone/pull 迁移，也不再通过本仓库的 Git LFS 传输。仓库只同步代码、测试、文档和本指令文件。
4. 用户手动复制后，本机解包参考布局为 `.firmware\analysis-201`。重点保留 `extraction-manifest.json`、相关原始库和字体配置，以及 `service-dispatch-tables.json`、`rea-direct-file-access`、`rea-jiritsu-file-semantics`、`rea-jiritsu-path-proof`、`rea-jiritsu-read-proof`。不存在时应报告缺失，不能假装已加载。
5. 被忽略的 `dist` 和 Copilot 会话目录也需按需另行准备。不要提交机身私有备份、凭据、序列号或未脱敏诊断日志；用户持有解包素材不等于获得公开分发许可，不自动向外部服务上传或推送。

变更原因：当前远端是 public fork，GitHub 拒绝向其上传新的 LFS 对象。旧 LFS 提交仅在本地 `backup/chinese-handoff-with-lfs-20261020` 分支保留；不要用 `git push --all` 把它重新推送。按手动复制文件的实际大小和 SHA-256 确认素材完整后再做离线分析。

## 下一阶段的只读操作顺序

### A. 离线审查和测试

- 审查 [现有 USB 文件接口](../pmca/usb/sony.py)、[服务后端](../pmca/platform/backend/senser.py) 和 [中文恢复实现](../pmca/platform/chinese.py)。不要直接调用后者的修复流程来“测试连接”。
- 先实现或审阅一个**独立的只读 Jiritsu 适配器/探针**，再考虑连接。限制为已核准的路径选择和普通文件读取，不提供通用命令发送、任意路径浏览或写入接口。
- 审查初始化和退出流程，不能只看主函数名称。不要调用 `getBackupPresetData`、`getBackupData`、预设备份状态/保存/写入、保护开关或普通 `tweak`；也不能直接复用会自动读取预设备份的外部 `Session`。
- 路径映射仍需核对，只允许固定诊断路径；不要暴力尝试目录遍历。普通读取子模式须与日志刷新、特殊内存访问、执行或加载分支隔离。
- 使用模拟传输测试报文序列、长度、超时、短包和非成功状态；断言没有文件写/删、预设备份、DEBUG、Updater 或执行请求。
- 文件读取失败不能一律当成“不存在”；只有明确且已验证的文件状态才可这样分类。超时、断连、序列不符或响应不明时停止，不自动重试或发送后续探测。

### B. 经确认后，进行有限机身读取

- 先进行主机侧设备枚举，不打开相机进行操作、不更换驱动。参考身份是 `054C:0E8A`（普通模式）和 `054C:0336`（服务模式），但不能仅凭 VID/PID 确认机型。
- 进入服务模式前，说明将执行的认证、模式切换及读取范围，确认用户已授权本轮操作。服务模式不是固件更新模式，但切换本身也不能保证零风险。
- 第一次只读取最小版本/型号信息。随后按已核准的文件接口读取 `/usr/lib/libsencore.so`、`/usr/lib/libJiritsu.so`、`/usr/share/app/fontlist.dat` 并核对身份。`/setting/updater/dat4` 如被采用，仅作为版本文件读取，不能调用任何更新功能。
- 只有兼容性确认后，才读取上面的两个中文 `.ltt` 文件，记录大小及 SHA-256。图标字体的位置以实际 `fontlist.dat` 为准；`/tmp/images/Sony_DI_Icons.ttf` 副本缺失不能单独证明中文菜单故障。
- 如需确认语言启用位，只评估已审查的单属性读取，不能为此读取整份预设备份。当前关注 `0x010d0096`、`0x010d0097`，不改值。
- 不读取与语言问题无关的私有数据、校准内容或完整分区。保存输出只落在主机的用户指定私有目录。
- 不发送测试写入来证明可写，不因读到了文件就推定可以安全写入。不要为了复现故障在本轮切换相机菜单语言。

### C. 读完只做判断

- 报告机型/版本、实际接口、读取状态、字体大小/摘要、语言位及仍未知的事项。
- 若字体和语言位正常但仍有重启历史，停止“补字库”假设，需要额外证据。
- 若缺失或不匹配，也只报告结果；**不自动恢复、解锁、改地区或开启新权限**。
- 若无法在这些限制下取得证据，明确说明阻碍并停止。任何后续写入阶段需要单独讨论，不在当前授权中。

## 本机运行环境（2026-10-21 记录）

换机后在这台 Windows 机器上专门建立了隔离环境，不要污染 base 或其他 conda 环境：

- 专用环境：`conda` 环境 **`pmca-a7c2`**，解释器 `D:\miniconda3\envs\pmca-a7c2\python.exe`（Python 3.11）。
  - 用 `D:\Program Files\miniconda3\Scripts\conda.exe` 创建，但环境实际落在 `D:\miniconda3\envs\pmca-a7c2`（该机有两个 miniconda：`D:\Program Files\miniconda3` 是 base，`D:\miniconda3` 存放 envs）。
  - 已按 [requirements.txt](../requirements.txt) 安装 `pyusb`、`pycryptodomex`、`axmlparserpy`、`pywin32` 等；pmca 可正常导入。
- libusb 原生后端由 `pip` 包 **`libusb-package`** 提供，DLL 位于 `D:\miniconda3\envs\pmca-a7c2\Lib\site-packages\libusb_package\libusb-1.0.dll`。
  - pyusb 默认 `usb.core.find` 需要该 DLL 可被发现；运行前把其所在目录前置到进程 `PATH`，或显式用 `libusb_package.get_libusb1_backend()`。
- 系统自带的 `python`（WindowsApps 的 `python.exe` 占位）不可用，base miniconda 也没有这些依赖；一律用上面的专用解释器。
- 不要把该环境、`libusb-1.0.dll` 或任何构建产物提交到仓库。

### 2026-10-21 实机只读结果与驱动状态

- 用户授权后，用官方 Zadig 2.9（`%USERPROFILE%\Downloads\zadig-portable.exe`，SHA-256 `4ECAA95DF3DA3621486A043AEF8B3050B8BAFE7C901402871E816229EF82039B`）由用户在界面中确认设备并替换驱动：
  - MSC `USB\VID_054C&PID_0E8A\D115100F779A`：`usbstor`（`usbstor.inf`, Microsoft）→ **`libusb0`（`oem88.inf`）**。
  - 服务模式 `USB\VID_054C&PID_0336\...`：无驱动 → **`libusb0`（`oem89.inf`）**。
  - 原绑定属性备份在 `.firmware\driver-backup\`（不入 Git）。
  - **恢复方法（用户要求全部完成后换回）**：在设备管理器中卸载这两个设备并勾选删除驱动，或以管理员执行 `pnputil /delete-driver oem88.inf /uninstall` 与 `pnputil /delete-driver oem89.inf /uninstall`，然后重新插拔；MSC 设备应回到 `usbstor`。执行前先用 `pnputil /enum-drivers` 确认 `oem88/oem89` 仍是 libusb-win32 包，避免误删其他驱动。
- 只读探针：仓库根目录 [tools_chinese_readonly_probe.py](../tools_chinese_readonly_probe.py)（未提交）。默认仅主机枚举；`--read` 做 StartSenser + 认证 → 切服务模式 → 只用 `readBackup`（`0x603/1`）读取 → StopSenser。不读文件、不读预设备份、不写。
- 实机读取结果（ILCE-7CM2）：型号 `ILCE-7CM2`，型号码 `0032856401`；**两个中文语言位 `0x010d0096`、`0x010d0097` 均为 `0x02`（disabled）**。序列号已读取，属私有数据，不写入仓库。
- 结论：当前机身中文菜单项处于关闭状态，与此前移除简繁中文的改动一致；所以现在不会因为选择中文而重启。中文字体文件状态**仍未知**（需要 Jiritsu 读取，尚未适配）；固件版本未通过文件确认（`/setting/updater/dat4` 需要文件接口）。

### 必须先解决的连接前置条件（驱动已于 2026-10-21 解决）

1. **驱动**：相机在 MSC 模式，USB 设备 `VID_054C&PID_0E8A` 仍绑定 Windows `usbstor`（`usbstor.inf`，Provider=Microsoft）。PMCA 进服务模式要求 libusb 驱动（`isinstance(device.driver, GenericUsbDriver)`），需用 Zadig/libusb-win32 换驱动；换前记录原驱动，用户要求全部完成后换回。服务模式设备 `PID_0336` 之后也要换。
2. **旧文件接口不可用**：2.01 的 `libsencore.so` 三张服务命令表（见 `.firmware\analysis-201\service-dispatch-tables.json`）只含 `0x10/0x20/0x30/0x40/0xff00/0xff02`，**没有 `0xFF01`**。现有 `readFile/writeFile` 和 `chinese check` 的身份、字体读取都走 `0xFF01`，在这台机身会被拒绝，不能用于实机。
3. **只读探针**：唯一文件读取路径是 AdjustControl(`0x40`) 内的 Jiritsu `adj_cmd_get_file2`，按选择子字节映射固定路径，且含 `mode==0x300` 的写文件分支（`O_WRONLY|O_CREAT|O_TRUNC`）必须避开；其协议适配尚未验证，字体可达性未确认，本轮不上机。
   - **本轮唯一可安全执行的实机只读** = 认证后用 `readBackup`（AdjustControl `0x603/1`，在分发表内，且不是触发删字体的 `0x603/4、0x603/5` 预设数据分支）读取型号、版本、序列号与两个中文语言位 `0x010d0096`、`0x010d0097`。不读文件、不读预设备份、不写任何内容。

## 离线测试与代码导航

在仓库根目录、已配置项目依赖的本地隔离 Python 环境中运行（本机用上面的 `pmca-a7c2`）：

```powershell
python -m unittest discover -s tests -p 'test_chinese*.py' -v
```

真实固件数据测试需显式设置 `PMCA_TEST_FIRMWARE_ROOT` 为**新机器上**的已解包目录，否则会跳过；没有图形环境时 Tk GUI 测试也可能跳过。报告实际通过/跳过数量，不能沿用旧机器的 47 项结果。

- [核心测试](../tests/test_chinese.py)、[真实固件数据测试](../tests/test_chinese_firmware.py)、[GUI 测试](../tests/test_chinese_gui.py)均使用模拟相机。
- [GUI](../pmca-gui.py)的 `--chinese-recovery-only` 只显示受限页面，启动不连接 USB；当前只允许离线预览，不点击会连接机身的操作按钮。
- 沿用项目现有 Python 风格和共享帮助函数；不要让只读诊断意外经过修复事务或自动回滚写入路径。

## 外部参考的使用边界

- `chocotan/a7c2-re`：仅参考字体打开日志、文件语义及纯离线验证。其默认模拟配置使用 `ALLLANG`，资产清单未列出两个中文 `.ltt`；不能直接套用配置或把菜单能显示视为中文已验证。
- `YuuLuo/a7c2-service-preload`：仅参考服务认证与协议说明，不采用 preload 或机内代码执行链。
- `QAQLeonard/a7c2-fl23-research`：仅参考共享文件传输与失败处理；忽略功能安装部分。已检查的 `Session` 初始化会读取预设备份，不能直接拿来做本阶段的只读探针。
- 外部项目的成功记录、模拟器运行和 USB 返回成功都不是本机身安全或可恢复性的保证。
