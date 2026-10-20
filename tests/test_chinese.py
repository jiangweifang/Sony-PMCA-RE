import contextlib
import hashlib
import io
import json
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

from pmca.backup import BackupFile, BackupHeader, PropertyTableEntryV4, SubsystemTableEntry
from pmca.platform import CameraShell
from pmca.platform.backend import PlatformBackend
from pmca.platform.backend.senser import SenserPlatformBackend
from pmca.platform.chinese import ChineseLanguageRepair
from pmca.usb import SenserFileControlError
from pmca.usb.sony import SonySenserCamera


def makeBackup():
 properties = {
  0x003e0005: b'ILCE-7CM2'.ljust(16, b'\0'),
  0x00e70000: b'\x01\x02\x03\x04\x05',
  0x00e70003: b'\x10\x20\x30\x40',
 }
 properties.update((0x010d008f + i, b'\x02') for i in range(35))
 counts = [0] * 0x10e
 for id in properties:
  counts[id >> 16] = max(counts[id >> 16], (id & 0xffff) + 1)
 numProperties = sum(counts)
 dataOffset = BackupHeader.size + len(counts) * SubsystemTableEntry.size + numProperties * PropertyTableEntryV4.size
 data = bytearray(dataOffset)
 struct.pack_into('<4sIIIII', data, 12, b'BK4\0', len(counts), numProperties, dataOffset, sum(map(len, properties.values())), 0)
 data[0xc0:0xe0] = b'CX89700_J1'.ljust(32, b'\0')
 index = 0
 for subsystem, count in enumerate(counts):
  offset = BackupHeader.size + subsystem * SubsystemTableEntry.size
  data[offset:offset + SubsystemTableEntry.size] = SubsystemTableEntry.pack(numProperties=count, ptr=index)
  for number in range(count):
   id = subsystem << 16 | number
   value = properties.get(id)
   ptr = 0xffffffff
   if value is not None:
    ptr = len(value) << 24 | len(data)
    data.extend(value)
   offset = BackupHeader.size + len(counts) * SubsystemTableEntry.size + index * PropertyTableEntryV4.size
   data[offset:offset + PropertyTableEntryV4.size] = PropertyTableEntryV4.pack(attr=1, ptr=ptr)
   index += 1
 struct.pack_into('<I', data, 0x20, sum(data[:0x20] + data[0x24:]))
 return bytes(data)


class FakeBackend(SenserPlatformBackend):
 def __init__(self, fonts, core):
  self.data = makeBackup()
  self.files = dict((ChineseLanguageRepair.FONT_PATH + name, data) for name, data in fonts.items())
  self.files[ChineseLanguageRepair.CORE_PATH] = core
  self.files['/setting/updater/dat4'] = ChineseLanguageRepair.VERSION
  self.events = []
  self.failSet = False
  self.failFont = None
  self.corruptFont = None
  self.failPresetRead = False

 def _deleteFonts(self):
  for name in ChineseLanguageRepair.REMOVED_FONTS:
   self.files.pop(ChineseLanguageRepair.FONT_PATH + name, None)

 def readBackup(self, id):
  return BackupFile(io.BytesIO(self.data)).getProperty(id).data

 def readFile(self, path, output, sizeCb=None):
  self.events.append(('readFile', path))
  if path not in self.files:
   raise SenserFileControlError(0, path)
  output.write(self.files[path])

 def writeFile(self, path, source):
  self.events.append(('writeFile', path))
  if self.failFont == path:
   self.failFont = None
   raise IOError('Injected font write failure')
  data = source.read()
  if self.corruptFont == path:
   self.corruptFont = None
   data = b'corrupt'
  self.files[path] = data

 def getBackupData(self):
  self.events.append(('getBackupData',))
  self._deleteFonts()
  if self.failPresetRead:
   self.failPresetRead = False
   raise IOError('Injected preset read failure')
  return self.data

 def setBackupData(self, data):
  self.events.append(('setBackupData',))
  self._deleteFonts()
  self.data = bytes(data)
  if self.failSet:
   self.failSet = False
   raise IOError('Injected backup write failure')


class ChineseRepairTests(unittest.TestCase):
 def setUp(self):
  self.temp = tempfile.TemporaryDirectory()
  self.addCleanup(self.temp.cleanup)
  self.source = os.path.join(self.temp.name, 'fonts')
  os.mkdir(self.source)
  self.directory = os.path.join(self.temp.name, 'backup')
  self.fonts = dict((name, ('fixture-' + name).encode()) for name in ChineseLanguageRepair.FONTS)
  profile = dict((name, (len(data), hashlib.sha256(data).hexdigest())) for name, data in self.fonts.items())
  self.core = b'fixture-core'
  self.enterContext = contextlib.ExitStack()
  self.addCleanup(self.enterContext.close)
  self.enterContext.enter_context(patch.object(ChineseLanguageRepair, 'FONTS', profile))
  self.enterContext.enter_context(patch.object(ChineseLanguageRepair, 'CORE_SHA256', hashlib.sha256(self.core).hexdigest()))
  self.enterContext.enter_context(contextlib.redirect_stdout(io.StringIO()))
  for name, data in self.fonts.items():
   with open(os.path.join(self.source, name), 'wb') as output:
    output.write(data)
  self.backend = FakeBackend(self.fonts, self.core)
  self.repair = ChineseLanguageRepair(self.backend)

 def assertFonts(self):
  for name, data in self.fonts.items():
   self.assertEqual(self.backend.files[ChineseLanguageRepair.FONT_PATH + name], data)

 def assertOriginalSettings(self, original):
  self.assertEqual(self.backend.data, original)

 def test_check_never_issues_deleting_backup_commands(self):
  self.assertTrue(self.repair.check())
  self.assertFalse(any(event[0] in ('getBackupData', 'setBackupData', 'writeFile') for event in self.backend.events))

 def test_check_reports_missing_fonts_without_writes(self):
  self.backend._deleteFonts()
  self.assertFalse(self.repair.check())
  self.assertFalse(any(event[0] == 'writeFile' for event in self.backend.events))

 def test_repair_changes_only_two_language_properties(self):
  original = self.backend.data
  self.repair.repair(self.source, self.directory)
  expected = io.BytesIO(original)
  backup = BackupFile(expected)
  for id in ChineseLanguageRepair.LANGUAGE_IDS:
   backup.setProperty(id, b'\x01')
  backup.updateChecksum()
  self.assertEqual(self.backend.data, expected.getvalue())
  self.assertFonts()
  with open(os.path.join(self.directory, 'backup.bin'), 'rb') as source:
   self.assertEqual(source.read(), original)
  with open(os.path.join(self.directory, 'manifest.json')) as source:
   self.assertEqual(json.load(source)['status'], 'complete')
  lastBackup = max(i for i, event in enumerate(self.backend.events) if event[0] in ('getBackupData', 'setBackupData'))
  self.assertTrue(all(event[0] in ('writeFile', 'readFile') for event in self.backend.events[lastBackup + 1:]))

 def test_repair_recovers_already_deleted_fonts(self):
  self.backend._deleteFonts()
  self.repair.repair(self.source, self.directory)
  self.assertFonts()

 def test_preserves_additional_font_deleted_by_firmware(self):
  path = ChineseLanguageRepair.FONT_PATH + 'UniversOTS-SJ_wIcon.ltt'
  self.backend.files[path] = b'existing-font'
  self.repair.repair(self.source, self.directory)
  self.assertEqual(self.backend.files[path], b'existing-font')

 def test_repair_is_idempotent_with_new_backup_directory(self):
  self.repair.repair(self.source, self.directory)
  previous = self.backend.data
  self.backend.events = []
  self.repair.repair(self.source, self.directory + '-second')
  self.assertEqual(self.backend.data, previous)
  self.assertFalse(any(event[0] == 'setBackupData' for event in self.backend.events))
  self.assertFonts()

 def test_already_unlocked_missing_fonts_requires_no_settings_writes(self):
  source = io.BytesIO(self.backend.data)
  backup = BackupFile(source)
  for i in range(35):
   backup.setProperty(0x010d008f + i, b'\x01')
  backup.updateChecksum()
  self.backend.data = source.getvalue()
  previous = self.backend.data
  self.backend._deleteFonts()
  self.repair.repair(self.source, self.directory)
  self.assertEqual(self.backend.data, previous)
  self.assertFalse(any(event[0] == 'setBackupData' for event in self.backend.events))
  self.assertFonts()

 def test_invalid_source_stops_before_device_access(self):
  name = next(iter(self.fonts))
  with open(os.path.join(self.source, name), 'wb') as output:
   output.write(b'invalid')
  with self.assertRaisesRegex(ValueError, 'Font does not match'):
   self.repair.repair(self.source, self.directory)
  self.assertEqual(self.backend.events, [])

 def test_wrong_version_refuses_before_backup_commands(self):
  self.backend.files['/setting/updater/dat4'] = b'\x00\x02'
  with self.assertRaisesRegex(ValueError, 'only ILCE-7CM2'):
   self.repair.repair(self.source, self.directory)
  self.assertFalse(any(event[0] in ('getBackupData', 'setBackupData', 'writeFile') for event in self.backend.events))

 def test_wrong_model_refuses_all_file_and_preset_operations(self):
  with patch.object(self.backend, 'readBackup', return_value=b'ILCE-7C\0'):
   with self.assertRaisesRegex(ValueError, 'only ILCE-7CM2'):
    self.repair.repair(self.source, self.directory)
  self.assertEqual(self.backend.events, [])

 def test_wrong_core_refuses_before_backup_commands(self):
  self.backend.files[ChineseLanguageRepair.CORE_PATH] = b'unknown'
  with self.assertRaisesRegex(ValueError, 'Unrecognized libsencore'):
   self.repair.repair(self.source, self.directory)
  self.assertFalse(any(event[0] in ('getBackupData', 'setBackupData', 'writeFile') for event in self.backend.events))

 def test_wrong_region_stops_settings_writes_but_restores_deleted_fonts(self):
  data = bytearray(self.backend.data)
  data[0xc0:0xe0] = b'CX89700_UC2'.ljust(32, b'\0')
  struct.pack_into('<I', data, 0x20, sum(data[:0x20] + data[0x24:]))
  self.backend.data = bytes(data)
  with self.assertRaisesRegex(ValueError, 'CX89700_J1'):
   self.repair.repair(self.source, self.directory)
  self.assertFalse(any(event[0] == 'setBackupData' for event in self.backend.events))
  self.assertFonts()

 def test_transport_failure_is_not_treated_as_missing_font(self):
  with patch.object(self.backend, 'readFile', side_effect=IOError('USB disconnected')):
   with self.assertRaisesRegex(IOError, 'USB disconnected'):
    self.repair.repair(self.source, self.directory)
  self.assertFalse(any(event[0] in ('getBackupData', 'setBackupData', 'writeFile') for event in self.backend.events))

 def test_existing_directory_is_not_overwritten(self):
  os.mkdir(self.directory)
  with self.assertRaises(FileExistsError):
   self.repair.repair(self.source, self.directory)
  self.assertFalse(any(event[0] == 'getBackupData' for event in self.backend.events))

 def test_backup_write_failure_restores_settings_and_fonts(self):
  original = self.backend.data
  self.backend.failSet = True
  with self.assertRaisesRegex(IOError, 'backup write failure'):
   self.repair.repair(self.source, self.directory)
  self.assertOriginalSettings(original)
  self.assertFonts()

 def test_preset_read_failure_still_restores_fonts(self):
  self.backend.failPresetRead = True
  with self.assertRaisesRegex(IOError, 'preset read failure'):
   self.repair.repair(self.source, self.directory)
  self.assertFonts()
  self.assertFalse(any(event[0] == 'setBackupData' for event in self.backend.events))

 def test_font_write_failure_rolls_back_language_flags(self):
  original = self.backend.data
  self.backend.failFont = ChineseLanguageRepair.FONT_PATH + next(iter(self.fonts))
  with self.assertRaisesRegex(IOError, 'font write failure'):
   self.repair.repair(self.source, self.directory)
  self.assertOriginalSettings(original)
  self.assertFonts()

 def test_font_readback_mismatch_rolls_back_language_flags(self):
  original = self.backend.data
  self.backend.corruptFont = ChineseLanguageRepair.FONT_PATH + next(iter(self.fonts))
  with self.assertRaisesRegex(IOError, 'Font readback failed'):
   self.repair.repair(self.source, self.directory)
  self.assertOriginalSettings(original)
  self.assertFonts()

 def test_persistent_write_failure_records_failed_rollback(self):
  with patch.object(self.backend, 'writeFile', side_effect=IOError('Camera storage unavailable')):
   with self.assertRaisesRegex(IOError, 'storage unavailable'):
    self.repair.repair(self.source, self.directory)
  with open(os.path.join(self.directory, 'manifest.json')) as source:
   self.assertEqual(json.load(source)['status'], 'rollback_failed')
  for id in ChineseLanguageRepair.LANGUAGE_IDS:
   self.assertEqual(self.backend.readBackup(id), b'\x02')

 def test_restore_preserves_unrelated_later_changes(self):
  original = self.backend.data
  self.repair.repair(self.source, self.directory)
  current = io.BytesIO(self.backend.data)
  backup = BackupFile(current)
  backup.setProperty(0x010d008f, b'\x01')
  backup.updateChecksum()
  self.backend.data = current.getvalue()
  self.repair.restore(self.directory)
  self.assertEqual(self.backend.readBackup(0x010d008f), b'\x01')
  for id in ChineseLanguageRepair.LANGUAGE_IDS:
   self.assertEqual(self.backend.readBackup(id), BackupFile(io.BytesIO(original)).getProperty(id).data)
  self.assertFonts()

 def test_restore_rejects_tampered_backup_without_writes(self):
  self.repair.repair(self.source, self.directory)
  with open(os.path.join(self.directory, 'backup.bin'), 'ab') as output:
   output.write(b'tampered')
  self.backend.events = []
  with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
   self.repair.restore(self.directory)
  self.assertFalse(any(event[0] in ('getBackupData', 'setBackupData', 'writeFile') for event in self.backend.events))

 def test_restore_rejects_different_camera(self):
  self.repair.repair(self.source, self.directory)
  current = io.BytesIO(self.backend.data)
  backup = BackupFile(current)
  backup.setProperty(0x00e70003, b'\x99\x99\x99\x99')
  backup.updateChecksum()
  self.backend.data = current.getvalue()
  self.backend.events = []
  with self.assertRaisesRegex(ValueError, 'does not match this camera'):
   self.repair.restore(self.directory)
  self.assertFalse(any(event[0] in ('getBackupData', 'setBackupData', 'writeFile') for event in self.backend.events))

 def test_commands_only_exposed_in_service_shell(self):
  self.assertIn('chinese repair', CameraShell(self.backend).commands.help())
  self.assertNotIn('chinese', CameraShell(PlatformBackend()).commands.help())

 def test_file_control_failure_has_specific_exception(self):
  device = unittest.mock.Mock()
  device.sendSenserPacket.return_value = (0, b'')
  with self.assertRaises(SenserFileControlError) as error:
   SonySenserCamera(device).readFile('/tmp/images/missing.ltt')
  self.assertEqual(error.exception.response, 0)
  self.assertIn('/tmp/images/missing.ltt', str(error.exception))

 def test_file_control_success_is_unchanged(self):
  device = unittest.mock.Mock()
  device.sendSenserPacket.return_value = (1, b'data')
  self.assertEqual(SonySenserCamera(device).readFile('/tmp/images/font.ltt'), b'data')


if __name__ == '__main__':
 unittest.main()
