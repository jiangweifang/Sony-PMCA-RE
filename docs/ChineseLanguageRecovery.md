# Chinese language recovery

## Scope and verification status

This is an **experimental, explicit service-shell operation**, not a general
language unlock. It is limited to:

- Camera: ILCE-7CM2.
- Installed firmware: 2.01.
- Backup preset: `CX89700_J1`.
- The exact service library identified below.

The ordinary GUI and `tweak` command retain their existing Japanese-camera
language restriction. Other models, firmware versions and modified service
libraries are not accepted by this recovery.

The transaction has offline tests, including simulated deletion of fonts on
every preset read/write. **A real-camera Chinese language switch and cold restart
are still required to verify the repair.** Static firmware analysis does not
establish that missing fonts are the only possible cause of a reboot.

## Evidence and repair mechanism

The analyzed update has these identifiers:

| Item | Value |
| --- | --- |
| Update size | 1,139,929,560 bytes |
| Update SHA-256 | `eb4943e6099754d64deaef5047942e9bfe258f232d0b7bc39fa23b3cd10e1e31` |
| FDAT model / version | `0x20030014` / `2.01` |
| Decoder | `CXD90057_k8` |
| `libsencore.so` SHA-256 | `3362d4b6e03dc517b04f1eb04d4199ff16d33f6e8f1bfddce657a375778d79e7` |

REA 6.4.0 with Ghidra 12.1.4 on Linux identified a branch in
`ReceiveOsalMessage` in `libsencore.so`. With Ghidra's image base of `0x100000`,
the function entry is `0x10f1b0` (ELF-relative `0xf1b0`).
For OSAL command `0x3e0166` and response byte `0xff`, it removes six files under
`/tmp/images`, including the Simplified and Traditional Chinese fonts, then
changes that response byte to `1`.

The library's command tables associate service backup commands, including
`0x0603/0x0004` (`PDT_WRITE`) and `0x0603/0x0005` (`PDT_READ`), with that OSAL
command. This establishes a conditional destructive side effect, **not** that
every backup request always deletes fonts.

The application's `fontlist.dat` uses:

- `FONT_S_CHINESE`: `/tmp/images/MYingHeiC-GB18030-SJ_wIcon.ltt`
- `FONT_T_CHINESE`: `/tmp/images/MYingHeiC-Big5-SJ_wIcon.ltt`

The boot filesystem table mounts `/dev/nflasha10` at `/tmp` as writable,
synchronous VFAT. These files are on persistent storage despite the directory
name. The update contains the original fonts in
`0800_appli/tmp/images`, as well as Chinese menu resources in its application
partition.

The implementation therefore captures available fonts **before** issuing any
preset-backup command, saves the original backup locally, modifies only
properties `0x010d0096` and `0x010d0097`, and restores and reads back the fonts
**after** all backup operations. It does not patch machine code, change the
camera's region, or copy another camera's preset/calibration data.

## Preparation

Use a charged battery, a reliable USB data cable, and the service-mode drivers
described in the main README. Do not interrupt power or USB during recovery.
The settings and font writes are separate operations: power loss cannot be made
atomic or automatically rolled back after the connection disappears.

Extract your own matching Sony update offline. One public unpacker supporting
this exact package is
[ChambersXDU/sony-a7c2-research](https://github.com/ChambersXDU/sony-a7c2-research),
based on [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py) and
David Buchanan's CXD90057 decoder. Extraction does not flash the camera.
Do not download replacement fonts from an untrusted source.

`FONTDIR` must contain all three files:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `MYingHeiC-GB18030-SJ_wIcon.ltt` | 2,054,740 | `a8afccc2e226d5a519f3698796c2a76a0ad6e163f7e5fc9e35d5e89d58db3276` |
| `MYingHeiC-Big5-SJ_wIcon.ltt` | 1,150,740 | `25f3afa8008c6d038e5bf61582c06539a70786a2de1c74fe63e73814d468ab9f` |
| `Sony_DI_Icons.ttf` | 622,344 | `f4957fda675cad6c118c91297ed53828fbe4ef0ea28bc50ae2db3458bc5341c2` |

The last file is included because the destructive branch also removes the
temporary icon font. Other affected fonts are preserved when readable.
File-control failures are reported as **unreadable**, not assumed to prove
absence. Transport failures abort rather than being treated as missing files.

Keep recovery directories private and outside version control: they contain
device-specific settings and identifiers. Each recovery requires a **new**
directory; existing backups are never overwritten.

## Commands

Start the current source version, not an older downloaded executable:

```powershell
python .\pmca-console.py serviceshell
```

Inside the service shell:

```text
chinese check
chinese repair "<FONTDIR>" "<NEW_BACKUPDIR>"
exit
```

For example, with the extraction used in this investigation:

```text
chinese repair "D:\GitHub\Sony-PMCA-RE\.firmware\analysis-201\firmware.tar_unpacked\0800_appli\tmp\images" "D:\GitHub\Sony-PMCA-RE\.firmware\camera-recovery-001"
```

`chinese check` checks model, firmware, library and font identities without
issuing preset-backup commands or writing to the camera. Preset-region and
settings validation occurs during repair, with font restoration protected by
the transaction.

If both Chinese flags are already enabled, repair skips **all settings-backup
writes**, including rollback writes. It still captures a preset backup (which
can itself trigger the deletion branch) and restores the fonts afterwards.
An earlier "all languages" unlock does not prove the two Chinese flags remain
enabled: the restricted Japanese profile disables them. `chinese check` reports
their individual current values without issuing preset-backup commands.

**Run recovery last, then exit service mode.** Subsequent ordinary service-mode
backup reads, tweaks or third-party tools may trigger the firmware's deletion
branch again; they are not intercepted by this opt-in command. Repeat recovery
with a new backup directory if necessary.

## Recovery and rollback

Before modifying settings, repair saves:

- `backup.bin`: the original complete backup.
- `original/`: affected fonts that could be read before any preset operation.
- `replacement/`: the supplied recovery fonts.
- `manifest.json`: device identity, hashes, unreadable-file warnings and status.

Any failure during the transaction attempts to restore the original backup
when settings writes have begun, then restores the captured fonts. If an
original font was unreadable, the validated replacement is retained rather
than deleting a possibly needed file. All writes are read back and checked.
A rollback failure is an error, not a successful recovery; retain the local
files and do not switch to Chinese until the fonts have been verified.

To undo a completed repair's two Chinese language flags:

```text
chinese restore "<BACKUPDIR>"
exit
```

Restore validates device identity and file hashes, uses only the original two
language values, and preserves unrelated current settings. It restores
captured fonts and keeps replacements for previously unreadable originals.
Its own safety backup is saved in a new `restore/` subdirectory. This directory
must not already exist. Never write `backup.bin` from a different camera.

## Hardware acceptance checklist

After the command succeeds:

1. Exit service mode and power the camera off and on.
2. Confirm Simplified Chinese appears and can be selected without a reboot.
3. Check several menu pages for correctly rendered characters.
4. Power off, wait, and restart; confirm Chinese still works.
5. Verify normal recording and USB operation.

Do not interpret successful USB readback alone as passing this checklist.

## Offline tests

```powershell
python -m unittest discover -s tests -p test_chinese.py -v
```

These use synthetic settings and fonts. No Sony firmware, fonts, user backup,
or camera connection is required.

### Offline tests with the actual 2.01 files

Set the extraction root, then run both suites:

```powershell
$env:PMCA_TEST_FIRMWARE_ROOT = 'D:\GitHub\Sony-PMCA-RE\.firmware\analysis-201'
python -m unittest discover -s tests -p 'test_chinese*.py' -v
Remove-Item Env:\PMCA_TEST_FIRMWARE_ROOT
```

Without that environment variable, the actual-firmware tests are skipped.
They verify the real service-library and font hashes and use the update's
Japanese preset, not the user's live settings. All device access goes through
an in-memory fake backend; no USB driver is instantiated and no extracted
binary is executed. Recovery files are written only to temporary directories.
The original extracted firmware is read-only throughout.

The suite covers:

- Original Japanese flags and previously enabled multilingual flags.
- Already unlocked settings with missing Chinese fonts, with **zero settings
  writes** and byte-for-byte unchanged settings.
- Firmware-like font deletion on every preset read and write.
- A lost response injected after each successful device-operation position.
- Byte-for-byte settings rollback and original font restoration.
- Persistent write failures, which must report `rollback_failed`, not success.
- Source hashes, version/library gates, existing backup directories, and
  restoration that preserves unrelated settings changed after repair.

The failure injection models a recoverable communication error: the simulated
device remains accessible for rollback. It does **not** model power being lost
for good, VFAT corruption, flash wear, Sony boot validation, or all camera
drivers. QEMU's generic ARM64 machines do not emulate the full BIONZ XR camera,
so booting some extracted code in QEMU would not prove that this camera cannot
be bricked.

The lowest-risk next hardware step is `chinese check`, after confirming service
mode access. It deliberately avoids preset operations, but entering service
mode itself is not a zero-risk operation. Do not run `repair` merely because
the offline tests pass; keep the local recovery files, understand the remaining
power/storage risks, and perform the hardware checklist only with explicit
approval.
