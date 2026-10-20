"""Opt-in, offline-only integration tests using an extracted Sony update."""

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest

from pmca.backup import BackupFile
from pmca.platform.chinese import ChineseLanguageRepair
from test_chinese import FakeBackend


FIRMWARE_ROOT = os.environ.get('PMCA_TEST_FIRMWARE_ROOT')


class FaultBackend(FakeBackend):
 def __init__(self, fonts, core, failAt=None):
  super(FaultBackend, self).__init__(fonts, core)
  self.calls = 0
  self.failAt = failAt

 def _fault(self):
  self.calls += 1
  if self.calls == self.failAt:
   raise IOError('Injected lost response at operation %d' % self.calls)

 def readBackup(self, id):
  result = super(FaultBackend, self).readBackup(id)
  self._fault()
  return result

 def getBackupData(self):
  result = super(FaultBackend, self).getBackupData()
  self._fault()
  return result

 def setBackupData(self, data):
  super(FaultBackend, self).setBackupData(data)
  self._fault()

 def readFile(self, path, output, sizeCb=None):
  super(FaultBackend, self).readFile(path, output, sizeCb)
  self._fault()

 def writeFile(self, path, source):
  super(FaultBackend, self).writeFile(path, source)
  self._fault()


@unittest.skipUnless(FIRMWARE_ROOT, 'Set PMCA_TEST_FIRMWARE_ROOT to opt into offline firmware tests')
class FirmwareRecoveryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  root = os.path.join(FIRMWARE_ROOT, 'firmware.tar_unpacked')
  cls.fontDirectory = os.path.join(root, '0800_appli', 'tmp', 'images')
  cls.fonts = {}
  for name, (size, digest) in ChineseLanguageRepair.FONTS.items():
   with open(os.path.join(cls.fontDirectory, name), 'rb') as source:
    data = source.read()
   if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
    raise ValueError('Firmware font mismatch: %s' % name)
   cls.fonts[name] = data
  with open(os.path.join(root, '0700_part_image', 'dev', 'nflasha15_unpacked', 'lib', 'libsencore.so'), 'rb') as source:
   cls.core = source.read()
  if hashlib.sha256(cls.core).hexdigest() != ChineseLanguageRepair.CORE_SHA256:
   raise ValueError('Firmware service library mismatch')
  with open(os.path.join(root, '0110_backup', 'SYSIPSX-DSLR', 'PP', 'CX89700_J1.bin'), 'rb') as source:
   cls.preset = source.read()
  BackupFile(io.BytesIO(cls.preset))

 def runRecovery(self, unlocked, failAt=None):
  backend = FaultBackend(self.fonts, self.core, failAt)
  data = io.BytesIO(self.preset)
  backup = BackupFile(data)
  if unlocked:
   for i in range(35):
    backup.setProperty(0x010d008f + i, b'\x01')
   backup.updateChecksum()
  backend.data = data.getvalue()
  original = backend.data
  with tempfile.TemporaryDirectory() as temporary:
   directory = os.path.join(temporary, 'recovery')
   with contextlib.redirect_stdout(io.StringIO()):
    if failAt is None:
     ChineseLanguageRepair(backend).repair(self.fontDirectory, directory)
    else:
     with self.assertRaises(IOError):
      ChineseLanguageRepair(backend).repair(self.fontDirectory, directory)
   if failAt is not None:
    self.assertEqual(backend.data, original)
   elif unlocked:
    self.assertEqual(backend.data, original)
   else:
    expected = io.BytesIO(original)
    backup = BackupFile(expected)
    for id in ChineseLanguageRepair.LANGUAGE_IDS:
     backup.setProperty(id, b'\x01')
    backup.updateChecksum()
    self.assertEqual(backend.data, expected.getvalue())
   for name, expected in self.fonts.items():
    self.assertEqual(backend.files[ChineseLanguageRepair.FONT_PATH + name], expected)
   if unlocked:
    self.assertFalse(any(event[0] == 'setBackupData' for event in backend.events))
   if failAt is None:
    with open(os.path.join(directory, 'manifest.json')) as source:
     self.assertEqual(json.load(source)['status'], 'complete')
  return backend.calls

 def test_actual_preset_and_fonts(self):
  self.runRecovery(False)

 def test_already_unlocked_never_writes_settings(self):
  self.runRecovery(True)

 def test_each_operation_failure_rolls_back_locked_preset(self):
  count = self.runRecovery(False)
  for operation in range(1, count + 1):
   with self.subTest(operation=operation):
    self.runRecovery(False, operation)

 def test_each_operation_failure_preserves_unlocked_preset(self):
  count = self.runRecovery(True)
  for operation in range(1, count + 1):
   with self.subTest(operation=operation):
    self.runRecovery(True, operation)

 def test_actual_missing_fonts_are_restored_without_settings_writes(self):
  backend = FakeBackend({}, self.core)
  data = io.BytesIO(self.preset)
  backup = BackupFile(data)
  for i in range(35):
   backup.setProperty(0x010d008f + i, b'\x01')
  backup.updateChecksum()
  backend.data = data.getvalue()
  with tempfile.TemporaryDirectory() as temporary:
   with contextlib.redirect_stdout(io.StringIO()):
    ChineseLanguageRepair(backend).repair(self.fontDirectory, os.path.join(temporary, 'recovery'))
  self.assertEqual(backend.data, data.getvalue())
  self.assertFalse(any(event[0] == 'setBackupData' for event in backend.events))
  for name, expected in self.fonts.items():
   self.assertEqual(backend.files[ChineseLanguageRepair.FONT_PATH + name], expected)


if __name__ == '__main__':
 unittest.main()
