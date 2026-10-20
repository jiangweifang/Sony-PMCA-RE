"""Opt-in Chinese font recovery for the verified ILCE-7CM2 2.01 firmware."""

import hashlib
import io
import json
import os

from .backend.senser import SenserPlatformBackend
from .backup import BackupFileDataInterface, BackupInterface, BackupPatchDataInterface
from ..usb import SenserFileControlError


class ChineseLanguageRepair:
 MODEL = 'ILCE-7CM2'
 VERSION = b'\x01\x02'
 REGION = 'CX89700_J1'
 CORE_PATH = '/usr/lib/libsencore.so'
 CORE_SHA256 = '3362d4b6e03dc517b04f1eb04d4199ff16d33f6e8f1bfddce657a375778d79e7'
 FONT_PATH = '/tmp/images/'
 FONTS = {
  'MYingHeiC-GB18030-SJ_wIcon.ltt': (2054740, 'a8afccc2e226d5a519f3698796c2a76a0ad6e163f7e5fc9e35d5e89d58db3276'),
  'MYingHeiC-Big5-SJ_wIcon.ltt': (1150740, '25f3afa8008c6d038e5bf61582c06539a70786a2de1c74fe63e73814d468ab9f'),
  'Sony_DI_Icons.ttf': (622344, 'f4957fda675cad6c118c91297ed53828fbe4ef0ea28bc50ae2db3458bc5341c2'),
 }
 REMOVED_FONTS = (
  'MYingHeiC-Big5HKSCS-SJ_wIcon.ltt',
  'MYingHeiC-Big5-SJ_wIcon.ltt',
  'MYingHeiC-GB18030-SJ_wIcon.ltt',
  'MYingHeiC-GB2312-SJ_wIcon.ltt',
  'UniversOTS-SJ_wIcon.ltt',
  'Sony_DI_Icons.ttf',
 )
 LANGUAGE_IDS = (0x010d0096, 0x010d0097)

 def __init__(self, backend):
  if not isinstance(backend, SenserPlatformBackend):
   raise ValueError('Chinese recovery requires the service-mode backend')
  self.backend = backend

 @staticmethod
 def _hash(data):
  return hashlib.sha256(data).hexdigest()

 def _readFile(self, path):
  output = io.BytesIO()
  self.backend.readFile(path, output)
  return output.getvalue()

 def _identity(self):
  model = self.backend.readBackup(0x003e0005).rstrip(b'\0').decode('ascii')
  if model != self.MODEL or self._readFile('/setting/updater/dat4') != self.VERSION:
   raise ValueError('Chinese recovery supports only ILCE-7CM2 firmware 2.01')
  if self._hash(self._readFile(self.CORE_PATH)) != self.CORE_SHA256:
   raise ValueError('Unrecognized libsencore.so; refusing camera writes')
  return {
   'model': model,
   'version': '2.01',
   'core_sha256': self.CORE_SHA256,
   'serial': self.backend.readBackup(0x00e70003).hex(),
   'model_code': self.backend.readBackup(0x00e70000).hex(),
  }

 def _captureFonts(self):
  fonts, unavailable = {}, {}
  for name in self.REMOVED_FONTS:
   try:
    fonts[name] = self._readFile(self.FONT_PATH + name)
   except SenserFileControlError as error:
    unavailable[name] = str(error)
    print('Warning: cannot back up %s: %s' % (name, error))
  return fonts, unavailable

 def _writeFonts(self, fonts):
  for name, data in fonts.items():
   self.backend.writeFile(self.FONT_PATH + name, io.BytesIO(data))
   if self._readFile(self.FONT_PATH + name) != data:
    raise IOError('Font readback failed: %s' % name)

 def _validateBackup(self, data, identity):
  backup = BackupInterface(BackupFileDataInterface(io.BytesIO(data)))
  if backup.getRegion() != self.REGION:
   raise ValueError('Chinese recovery supports only the CX89700_J1 preset')
  if (backup.readProp('modelName').rstrip(b'\0').decode('ascii') != identity['model']
      or backup.readProp('serialNumber').hex() != identity['serial']
      or backup.readProp('modelCode').hex() != identity['model_code']):
   raise ValueError('Backup does not match this camera')
  if any(value not in (1, 2) for value in backup.readProp('language')):
   raise ValueError('Unrecognized language settings')
  return backup

 @staticmethod
 def _save(path, data):
  with open(path, 'xb') as output:
   output.write(data)
   output.flush()
   os.fsync(output.fileno())

 @staticmethod
 def _saveManifest(directory, manifest):
  path = os.path.join(directory, 'manifest.json')
  with open(path + '.tmp', 'w') as output:
   json.dump(manifest, output, indent=2, sort_keys=True)
   output.flush()
   os.fsync(output.fileno())
  os.replace(path + '.tmp', path)

 def check(self):
  self._identity()
  for id in self.LANGUAGE_IDS:
   value = self.backend.readBackup(id)
   if value not in (b'\x01', b'\x02'):
    raise ValueError('Unrecognized language setting: 0x%08x' % id)
   print('Chinese flag 0x%08x: %s' % (id, 'enabled' if value == b'\x01' else 'disabled'))
  fonts, unavailable = self._captureFonts()
  valid = True
  for name, (size, digest) in self.FONTS.items():
   if name in unavailable:
    status = 'unreadable (not proof that the file is absent)'
   elif len(fonts[name]) == size and self._hash(fonts[name]) == digest:
    status = 'verified'
   else:
    status = 'does not match the verified firmware'
   print('%s: %s' % (name, status))
   valid = valid and status == 'verified'
  print('No camera writes or preset-backup commands were issued.')
  return valid

 def repair(self, fontDirectory, backupDirectory):
  fonts = {}
  for name, (size, digest) in self.FONTS.items():
   with open(os.path.join(fontDirectory, name), 'rb') as source:
    data = source.read(size + 1)
   if len(data) != size or self._hash(data) != digest:
    raise ValueError('Font does not match ILCE-7CM2 2.01: %s' % name)
   fonts[name] = data
  self._change(fonts, [1, 1], backupDirectory, self._identity())
  print('Chinese language flags and original fonts verified on the camera.')
  print('Exit service mode and test Chinese and a cold restart. Run recovery last after other tweaks.')

 def restore(self, backupDirectory):
  identity = self._identity()
  with open(os.path.join(backupDirectory, 'manifest.json')) as source:
   manifest = json.load(source)
  if manifest.get('format') != 1 or manifest.get('identity') != identity:
   raise ValueError('Recovery manifest does not match this camera')
  with open(os.path.join(backupDirectory, 'backup.bin'), 'rb') as source:
   original = source.read()
  if self._hash(original) != manifest['backup_sha256']:
   raise ValueError('Recovery backup checksum mismatch')
  backup = self._validateBackup(original, identity)
  fonts = {}
  for category in ('replacement', 'original'):
   for name, digest in manifest[category].items():
    if name not in self.REMOVED_FONTS:
     raise ValueError('Unexpected recovery font name')
    with open(os.path.join(backupDirectory, category, name), 'rb') as source:
     data = source.read()
    if self._hash(data) != digest:
     raise ValueError('Recovery font checksum mismatch: %s' % name)
    fonts[name] = data
  if not all(name in fonts for name in self.FONTS):
   raise ValueError('Recovery font set is incomplete')
  values = [backup.dataInterface.readProp(id)[0] for id in self.LANGUAGE_IDS]
  self._change(fonts, values, os.path.join(backupDirectory, 'restore'), identity)
  print('Original Chinese language flags restored; unrelated current settings were preserved.')
  print('Fonts unreadable before the original repair are retained, not deleted.')

 def _change(self, replacement, values, directory, identity):
  os.mkdir(directory)
  original, unavailable = self._captureFonts()
  rollbackFonts = dict(replacement)
  rollbackFonts.update(original)
  targetFonts = dict(original)
  targetFonts.update(replacement)
  manifest = {
   'format': 1, 'identity': identity, 'status': 'prepared',
   'original': {}, 'replacement': {}, 'unreadable_original': unavailable,
  }
  for category, fonts in (('original', original), ('replacement', replacement)):
   os.mkdir(os.path.join(directory, category))
   for name, data in fonts.items():
    self._save(os.path.join(directory, category, name), data)
    manifest[category][name] = self._hash(data)
  self._saveManifest(directory, manifest)
  snapshot = None
  attempted = False
  completed = False
  try:
   # Preset reads can delete fonts too; capture all affected files before this.
   patch = BackupPatchDataInterface(self.backend)
   snapshot = patch.file.getvalue()
   self._validateBackup(snapshot, identity)
   self._save(os.path.join(directory, 'backup.bin'), snapshot)
   manifest['backup_sha256'] = self._hash(snapshot)
   manifest['status'] = 'applying'
   self._saveManifest(directory, manifest)
   for id, value in zip(self.LANGUAGE_IDS, values):
    data = bytes([value])
    if patch.readProp(id) != data:
     patch.writeProp(id, data)
   attempted = bool(patch.getPatch())
   manifest['settings_written'] = attempted
   if attempted:
    patch.apply()
   else:
    print('Chinese flags already match; no settings backup will be written.')
   for id, value in zip(self.LANGUAGE_IDS, values):
    if self.backend.readBackup(id) != bytes([value]):
     raise IOError('Language setting readback failed: 0x%08x' % id)
   # No backup operation may follow this restoration before reporting success.
   self._writeFonts(targetFonts)
   manifest['status'] = 'complete'
   self._saveManifest(directory, manifest)
   completed = True
  finally:
   if not completed:
    print('Recovery failed. Attempting rollback; keep the local backup at %s.' % directory)
    rolledBack = False
    try:
     try:
      if attempted:
       self.backend.setBackupData(snapshot)
       restored = self.backend.getBackupData()
       size = BackupFileDataInterface(io.BytesIO(snapshot)).getSize()
       if restored[0x100:size] != snapshot[0x100:size]:
        raise IOError('Backup rollback readback failed; manual recovery is required')
     finally:
      self._writeFonts(rollbackFonts)
     rolledBack = True
    finally:
     manifest['status'] = 'rolled_back' if rolledBack else 'rollback_failed'
     self._saveManifest(directory, manifest)
     if not rolledBack:
      print('Rollback could not be verified. Do not select Chinese; manual recovery is required.')
