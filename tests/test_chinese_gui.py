import contextlib
import hashlib
import importlib.util
import io
import os
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from test_chinese import FakeBackend


spec = importlib.util.spec_from_file_location('pmca_gui_tests', os.path.join(os.path.dirname(__file__), '..', 'pmca-gui.py'))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


class ChineseGuiTests(unittest.TestCase):
 def setUp(self):
  self.contexts = contextlib.ExitStack()
  self.addCleanup(self.contexts.close)
  self.contexts.enter_context(patch.object(gui.AppLoadTask, 'run'))
  self.contexts.enter_context(patch.object(gui.MainUi, 'redirectStreams'))
  for name in ('showerror', 'showinfo', 'showwarning'):
   self.contexts.enter_context(patch.object(gui, name))
  self.confirm = self.contexts.enter_context(patch.object(gui, 'askyesno', return_value=False))
  self.connect = self.contexts.enter_context(patch.object(gui, 'senserShellCommand'))
  try:
   self.root = gui.MainUi('Chinese recovery GUI tests', recoveryOnly=True)
  except gui.TclError as error:
   self.skipTest('Tk display unavailable: %s' % error)
  self.root.withdraw()
  self.addCleanup(self.destroyUi, self.root)
  self.frame = self.root.chineseRecovery
  self.temporary = tempfile.TemporaryDirectory()
  self.addCleanup(self.temporary.cleanup)

 @staticmethod
 def destroyUi(root):
  for timer in root.tk.call('after', 'info'):
   root.after_cancel(timer)
  root.destroy()

 def prepareRepairPaths(self):
  fonts = os.path.join(self.temporary.name, 'fonts')
  os.mkdir(fonts)
  for name in gui.ChineseLanguageRepair.FONTS:
   with open(os.path.join(fonts, name), 'wb') as output:
    output.write(('fixture-' + name).encode())
  backup = os.path.join(self.temporary.name, 'new-backup')
  self.frame.fontDirectory.set(fonts)
  self.frame.backupDirectory.set(backup)
  return fonts, backup

 def test_launch_does_not_open_camera(self):
  self.root.update()
  self.connect.assert_not_called()
  self.assertEqual(['Chinese recovery'], [self.root.tabs.tab(tab, 'text') for tab in self.root.tabs.tabs()])
  gui.AppLoadTask.run.assert_not_called()

 def test_check_requires_confirmation_and_no_paths(self):
  self.frame.checkButton.invoke()
  self.confirm.assert_called_once()
  self.assertEqual(self.confirm.call_args[1]['default'], 'no')
  self.connect.assert_not_called()
  self.assertFalse(self.root.cameraBusy)
  self.assertEqual(self.frame.getArguments('check'), ())

 def test_cancelled_repair_does_not_start_or_create_backup(self):
  fonts, backup = self.prepareRepairPaths()
  self.frame.repairButton.invoke()
  self.confirm.assert_called_once()
  self.connect.assert_not_called()
  self.assertFalse(os.path.exists(backup))
  self.assertFalse(self.root.cameraBusy)

 def test_missing_inputs_fail_before_confirmation_or_camera(self):
  self.frame.repairButton.invoke()
  gui.showerror.assert_called_once()
  self.confirm.assert_not_called()
  self.connect.assert_not_called()

 def test_existing_backup_is_rejected(self):
  fonts, backup = self.prepareRepairPaths()
  os.mkdir(backup)
  with self.assertRaisesRegex(ValueError, 'does not already exist'):
   self.frame.getArguments('repair')

 def test_restore_requires_manifest_and_unused_restore_directory(self):
  with self.assertRaisesRegex(ValueError, 'manifest.json'):
   self.frame.getArguments('restore')
  directory = self.temporary.name
  for name in ('manifest.json', 'backup.bin'):
   with open(os.path.join(directory, name), 'wb') as output:
    output.write(b'fixture')
  self.frame.restoreDirectory.set(directory)
  self.assertEqual(self.frame.getArguments('restore'), (directory,))
  os.mkdir(os.path.join(directory, 'restore'))
  with self.assertRaisesRegex(ValueError, 'will not be overwritten'):
   self.frame.getArguments('restore')

 def test_backup_picker_does_not_create_directory(self):
  with patch.object(gui, 'askdirectory', return_value=self.temporary.name):
   self.frame.chooseBackup()
  path = self.frame.backupDirectory.get()
  self.assertEqual(os.path.dirname(path), self.temporary.name)
  self.assertFalse(os.path.exists(path))

 def test_busy_state_blocks_other_camera_buttons_and_close(self):
  self.assertTrue(self.root.beginCameraTask())
  for button in (self.frame.checkButton, self.frame.repairButton, self.frame.restoreButton):
   self.assertTrue(button.instate(['disabled']))
  with patch.object(self.root, 'destroy') as destroy:
   self.root.close()
   destroy.assert_not_called()
  gui.showwarning.assert_called()
  self.assertFalse(self.root.beginCameraTask())
  self.root.endCameraTask()
  self.assertFalse(self.frame.checkButton.instate(['disabled']))

 def test_legacy_gui_keeps_its_original_tabs(self):
  legacy = gui.MainUi('Legacy GUI')
  try:
   legacy.withdraw()
   self.assertEqual(['Camera info', 'Install app', 'Tweaks', 'Update firmware'],
                    [legacy.tabs.tab(tab, 'text') for tab in legacy.tabs.tabs()])
   self.assertFalse(hasattr(legacy, 'chineseRecovery'))
  finally:
   self.destroyUi(legacy)

 def test_setup_failure_releases_camera_gate(self):
  task = gui.CameraTask(self.frame)
  with patch.object(task, 'doBefore', side_effect=ValueError('setup failed')):
   with self.assertRaisesRegex(ValueError, 'setup failed'):
    task.run()
  self.assertFalse(self.root.cameraBusy)
  self.assertFalse(self.frame.checkButton.instate(['disabled']))

 def test_no_device_is_an_error_not_success(self):
  with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
   result = gui.ChineseRecoveryTask(self.frame, 'check').do(())
  self.assertFalse(result[0])
  self.assertIn('No camera operation completed', result[1])

 def test_check_uses_recovery_not_tweak_preset_reads(self):
  backend = Mock()
  recovery = Mock()
  recovery.check.return_value = False
  self.connect.side_effect = lambda complete: complete(object())
  with patch.object(gui, 'SenserPlatformBackend', return_value=backend), \
       patch.object(gui, 'ChineseLanguageRepair', return_value=recovery), \
       patch.object(gui, 'TweakInterface', side_effect=AssertionError('Unexpected preset path')), \
       patch.object(gui, 'updaterShellCommand', side_effect=AssertionError('Updater forbidden')) as updater, \
       patch.object(gui, 'firmwareUpdateCommand', side_effect=AssertionError('Firmware update forbidden')) as firmware, \
       contextlib.redirect_stdout(io.StringIO()):
   result = gui.ChineseRecoveryTask(self.frame, 'check').do(())
  self.assertEqual(result, (True, False))
  recovery.check.assert_called_once_with()
  recovery.repair.assert_not_called()
  backend.start.assert_called_once_with()
  backend.stop.assert_called_once_with()
  backend.interactiveShell.assert_not_called()
  updater.assert_not_called()
  firmware.assert_not_called()

 def test_restore_dispatch_and_backend_cleanup(self):
  backend = Mock()
  recovery = Mock()
  self.connect.side_effect = lambda complete: complete(object())
  with patch.object(gui, 'SenserPlatformBackend', return_value=backend), \
       patch.object(gui, 'ChineseLanguageRepair', return_value=recovery), \
       contextlib.redirect_stdout(io.StringIO()):
   result = gui.ChineseRecoveryTask(self.frame, 'restore').do(('saved-backup',))
  self.assertTrue(result[0])
  recovery.restore.assert_called_once_with('saved-backup')
  backend.stop.assert_called_once_with()

 def test_operation_error_still_stops_backend(self):
  backend = Mock()
  recovery = Mock()
  recovery.repair.side_effect = IOError('write failed')
  self.connect.side_effect = lambda complete: complete(object())
  with patch.object(gui, 'SenserPlatformBackend', return_value=backend), \
       patch.object(gui, 'ChineseLanguageRepair', return_value=recovery), \
       contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
   result = gui.ChineseRecoveryTask(self.frame, 'repair').do(('fonts', 'backup'))
  self.assertEqual(result, (False, 'write failed'))
  backend.stop.assert_called_once_with()
  gui.ChineseRecoveryTask(self.frame, 'repair').doAfter(result)
  gui.showerror.assert_called_once()
  gui.showinfo.assert_not_called()

 def test_check_warning_does_not_claim_repair_success(self):
  gui.ChineseRecoveryTask(self.frame, 'check').doAfter((True, False))
  self.assertIn('No repair was performed', self.frame.status.get())
  gui.showwarning.assert_called_once()
  gui.showinfo.assert_not_called()

 def test_repair_button_runs_real_recovery_against_fake_device(self):
  fontsPath, backupPath = self.prepareRepairPaths()
  fonts = {}
  for name in gui.ChineseLanguageRepair.FONTS:
   with open(os.path.join(fontsPath, name), 'rb') as source:
    fonts[name] = source.read()
  core = b'fixture-core'
  backend = FakeBackend(fonts, core)
  backend.start = Mock()
  backend.stop = Mock()
  profile = dict((name, (len(data), hashlib.sha256(data).hexdigest())) for name, data in fonts.items())
  self.confirm.return_value = True
  self.connect.side_effect = lambda complete: complete(object())
  with patch.object(gui, 'SenserPlatformBackend', return_value=backend), \
       patch.object(gui.ChineseLanguageRepair, 'FONTS', profile), \
       patch.object(gui.ChineseLanguageRepair, 'CORE_SHA256', hashlib.sha256(core).hexdigest()), \
       contextlib.redirect_stdout(io.StringIO()):
   self.frame.repairButton.invoke()
   self.assertTrue(self.root.cameraBusy)
   deadline = time.monotonic() + 10
   while self.root.cameraBusy and time.monotonic() < deadline:
    self.root.update()
    time.sleep(.01)
  self.assertFalse(self.root.cameraBusy, 'GUI recovery worker did not finish')
  self.assertFalse(self.frame.repairButton.instate(['disabled']))
  self.assertTrue(os.path.isfile(os.path.join(backupPath, 'backup.bin')))
  for id in gui.ChineseLanguageRepair.LANGUAGE_IDS:
   self.assertEqual(backend.readBackup(id), b'\x01')
  for name, data in fonts.items():
   self.assertEqual(backend.files[gui.ChineseLanguageRepair.FONT_PATH + name], data)
  backend.stop.assert_called_once_with()
  self.assertIn('Hardware restart testing', self.frame.status.get())

 def test_windowed_stdout_flush_without_parent(self):
  output = io.StringIO()
  redirector = gui.PrintRedirector(output.write)
  redirector.write('message')
  redirector.flush()
  self.assertEqual(output.getvalue(), 'message')


if __name__ == '__main__':
 unittest.main()
