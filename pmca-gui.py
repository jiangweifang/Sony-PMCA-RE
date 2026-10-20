#!/usr/bin/env python3
"""A simple gui interface"""
import sys
import argparse
import os
import time
import traceback
import webbrowser
from tkinter.filedialog import askdirectory
from tkinter.messagebox import askyesno, showerror, showinfo, showwarning

import config
from pmca.commands.usb import *
from pmca.platform.backend.senser import *
from pmca.platform.backend.usb import *
from pmca.platform.chinese import ChineseLanguageRepair
from pmca.platform.tweaks import *
from pmca.ui import *

if getattr(sys, 'frozen', False):
 import frozenversion
 from frozenversion import version
 recoveryOnly = getattr(frozenversion, 'recovery_only', False)
else:
 version = None
 recoveryOnly = False

class PrintRedirector(object):
 """Redirect writes to a function"""
 def __init__(self, func, parent=None):
  self.func = func
  self.parent = parent
 def write(self, str):
  if self.parent:
   self.parent.write(str)
  self.func(str)
 def flush(self):
  if self.parent:
   self.parent.flush()


class CameraTask(BackgroundTask):
 def run(self):
  self.root = self.ui.winfo_toplevel()
  if not self.root.beginCameraTask():
   return
  started = False
  try:
   super(CameraTask, self).run()
   started = True
  finally:
   if not started:
    self.root.endCameraTask()

 def _onThread(self, arg):
  try:
   result = self.do(arg)
  finally:
   self.ui.run(self.root.endCameraTask)
  self.ui.run(lambda: self.doAfter(result))


class AppLoadTask(BackgroundTask):
 def doBefore(self):
  self.ui.setAppList([])
  self.ui.appLoadButton.config(state=DISABLED)

 def do(self, arg):
  try:
   print('')
   return list(listApps().values())
  except Exception:
   traceback.print_exc()

 def doAfter(self, result):
  if result:
   self.ui.setAppList(result)
  self.ui.appLoadButton.config(state=NORMAL)


class InfoTask(BackgroundTask):
 """Task to run infoCommand()"""
 def doBefore(self):
  self.ui.infoButton.config(state=DISABLED)

 def do(self, arg):
  try:
   print('')
   infoCommand()
  except Exception:
   traceback.print_exc()

 def doAfter(self, result):
  self.ui.infoButton.config(state=NORMAL)


class InstallTask(BackgroundTask):
 """Task to run installCommand()"""
 def doBefore(self):
  self.ui.installButton.config(state=DISABLED)
  return self.ui.getMode(), self.ui.getSelectedApk(), self.ui.getSelectedApp()

 def do(self, args):
  (mode, apkFilename, app) = args
  try:
   print('')
   if mode == self.ui.MODE_APP and app:
    installCommand(appPackage=app.package)
   elif mode == self.ui.MODE_APK and apkFilename:
    with open(apkFilename, 'rb') as f:
     installCommand(apkFile=f)
   else:
    installCommand()
  except Exception:
   traceback.print_exc()

 def doAfter(self, result):
  self.ui.installButton.config(state=NORMAL)


class FirmwareUpdateTask(BackgroundTask):
 """Task to run firmwareUpdateCommand()"""
 def doBefore(self):
  self.ui.fwUpdateButton.config(state=DISABLED)
  return self.ui.getSelectedDat()

 def do(self, datFile):
  try:
   if datFile:
    print('')
    with open(datFile, 'rb') as f:
     firmwareUpdateCommand(f)
  except Exception:
   traceback.print_exc()

 def doAfter(self, result):
  self.ui.fwUpdateButton.config(state=NORMAL)


class StartPlatformShellTask(BackgroundTask):
 def doBefore(self):
  self.ui.startUpdaterShellButton.config(state=DISABLED)
  self.ui.startSenserShellButton.config(state=DISABLED)

 def do(self, arg):
  try:
   print('')
   self.start()
  except Exception:
   traceback.print_exc()

 def start(self):
  pass

 def launchShell(self, backend):
  backend.start()
  tweaks = TweakInterface(backend)

  if next(tweaks.getTweaks(), None):
   endFlag = threading.Event()
   root = self.ui.master
   root.run(lambda: root.after(0, lambda: TweakDialog(root, tweaks, endFlag)))
   endFlag.wait()
  else:
   print('No tweaks available')

  backend.stop()

 def doAfter(self, result):
  self.ui.startUpdaterShellButton.config(state=NORMAL)
  self.ui.startSenserShellButton.config(state=NORMAL)


class StartUpdaterShellTask(StartPlatformShellTask):
 """Task to run updaterShellCommand() and open TweakDialog"""
 def start(self):
  updaterShellCommand(complete=lambda dev: self.launchShell(UsbPlatformBackend(dev)))


class StartSenserShellTask(StartPlatformShellTask):
 """Task to run senserShellCommand() and open TweakDialog"""
 def start(self):
  senserShellCommand(complete=lambda dev: self.launchShell(SenserPlatformBackend(dev)))


class TweakApplyTask(BackgroundTask):
 """Task to run TweakInterface.apply()"""
 def doBefore(self):
  self.ui.setState(DISABLED)

 def do(self, arg):
  try:
   print('Applying tweaks...')
   self.ui.tweakInterface.apply()
  except Exception:
   traceback.print_exc()

 def doAfter(self, result):
  self.ui.setState(NORMAL)
  self.ui.cancel()


class ChineseRecoveryTask(CameraTask):
 def __init__(self, ui, operation):
  super(ChineseRecoveryTask, self).__init__(ui)
  self.operation = operation

 def run(self):
  if self.ui.winfo_toplevel().cameraBusy:
   showwarning('Camera busy', 'Wait for the current camera operation to finish.', parent=self.ui)
   return
  try:
   self.arguments = self.ui.getArguments(self.operation)
  except ValueError as error:
   showerror('Chinese recovery', str(error), parent=self.ui)
   return
  if self.operation == 'check':
   message = ('Switch to service mode and check ILCE-7CM2 2.01 fonts and Chinese flags?\n\n'
              'This check issues no preset-backup commands and writes no camera files or settings. '
              'Entering service mode still requires the correct USB driver and is not risk-free.')
  else:
   message = ('EXPERIMENTAL: this operation writes persistent camera files'
              ' and may write a settings backup.\n\n'
              'Only ILCE-7CM2 2.01 / CX89700_J1 is supported. Hardware validation is still pending. '
              'Do not disconnect USB or power. A local settings backup is not a complete unbrick image.\n\n'
              'No firmware updater, region changes, telnet or ADB are used.\n\n'
              'Recovery directory: %s\n\nContinue?' % self.arguments[-1])
  if not askyesno('Confirm Chinese recovery', message, parent=self.ui, icon='warning', default='no'):
   return
  super(ChineseRecoveryTask, self).run()

 def doBefore(self):
  self.ui.status.set('Running %s... Do not disconnect USB or power.' % self.operation)
  return self.arguments

 def do(self, args):
  try:
   print('\nChinese recovery: %s' % self.operation)
   results = []
   def connected(device):
    backend = SenserPlatformBackend(device)
    try:
     backend.start()
     recovery = ChineseLanguageRepair(backend)
     if self.operation == 'check':
      result = recovery.check()
     elif self.operation == 'repair':
      result = recovery.repair(*args)
     elif self.operation == 'restore':
      result = recovery.restore(*args)
     else:
      raise ValueError('Unknown Chinese recovery operation')
    finally:
     backend.stop()
    results.append(result)
   senserShellCommand(complete=connected)
   if not results:
    raise RuntimeError('No camera operation completed. Check the USB connection, mass-storage mode and service-mode driver.')
   return True, results[0]
  except Exception as error:
   traceback.print_exc()
   return False, str(error)

 def doAfter(self, result):
  success, value = result
  if not success:
   self.ui.status.set('Operation failed. Read the log before taking further action.')
   showerror('Chinese recovery failed', value, parent=self.ui)
  elif self.operation == 'check':
   if value:
    self.ui.status.set('Fonts verified. Review the Chinese language flags in the log.')
    showinfo('Check completed', 'Fonts match the verified firmware. Review the language flags in the log.\nNo repair was performed.', parent=self.ui)
   else:
    self.ui.status.set('Font issues found. No repair was performed; review the log.')
    showwarning('Check completed', 'Some fonts could not be verified. Review the log before deciding whether to repair.\nNo repair was performed.', parent=self.ui)
  else:
   self.ui.status.set('%s completed and read back. Hardware restart testing is still required.' % self.operation.capitalize())
   showwarning('Camera operation completed',
               'File/settings readback completed; this is not proof of a successful hardware fix.\n\n'
               'Do not run ordinary tweaks or preset-backup commands afterwards. '
               'Test the menu and a cold restart before considering the repair verified.',
               parent=self.ui)


class MainUi(UiRoot):
 """Main window"""
 def __init__(self, title, recoveryOnly=False):
  UiRoot.__init__(self)

  self.title(title)
  self.geometry('720x760' if recoveryOnly else '450x500')
  if recoveryOnly:
   self.minsize(680, 650)
  self['menu'] = Menu(self)
  self.cameraBusy = False
  self._disabledControls = []
  self.protocol('WM_DELETE_WINDOW', self.close)

  tabs = self.tabs = Notebook(self, padding=5)
  tabs.pack(fill=X)

  if recoveryOnly:
   self.chineseRecovery = ChineseRecoveryFrame(self, padding=10)
   tabs.add(self.chineseRecovery, text='Chinese recovery')
  else:
   tabs.add(InfoFrame(self, padding=10), text='Camera info')
   tabs.add(InstallerFrame(self, padding=10), text='Install app')
   tabs.add(UpdaterShellFrame(self, padding=10), text='Tweaks')
   tabs.add(FirmwareFrame(self, padding=10), text='Update firmware')

  docsLink = Label(self, text='Camera compatibility', foreground='blue', cursor='hand2')
  docsLink.bind('<Button-1>', lambda e: webbrowser.open_new(config.docsUrl + '/devices.html'))
  docsLink.pack(pady=(0, 5))

  self.logText = ScrollingText(self)
  self.logText.text.configure(state=DISABLED)
  self.logText.pack(fill=BOTH, expand=True)

  self.redirectStreams()

 def beginCameraTask(self):
  if self.cameraBusy:
   showwarning('Camera busy', 'Wait for the current camera operation to finish.', parent=self)
   return False
  self.cameraBusy = True
  self._disabledControls = []
  def disable(parent):
   for widget in parent.winfo_children():
    if isinstance(widget, Toplevel):
     continue
    if isinstance(widget, (Button, Entry, Combobox, Radiobutton, Checkbutton)) and not widget.instate(['disabled']):
     self._disabledControls.append(widget)
     widget.state(['disabled'])
    disable(widget)
  disable(self)
  return True

 def endCameraTask(self):
  for widget in self._disabledControls:
   widget.state(['!disabled'])
  self._disabledControls = []
  self.cameraBusy = False

 def close(self):
  if self.cameraBusy:
   showwarning('Camera operation in progress',
               'Keep the application open and do not disconnect the camera until the operation finishes.',
               parent=self)
   return
  self.destroy()

 def log(self, msg):
  self.logText.text.configure(state=NORMAL)
  self.logText.text.insert(END, msg)
  self.logText.text.configure(state=DISABLED)
  self.logText.text.see(END)

 def redirectStreams(self):
  for stream in ['stdout', 'stderr']:
   setattr(sys, stream, PrintRedirector(lambda str: self.run(lambda: self.log(str)), getattr(sys, stream)))


class InfoFrame(UiFrame):
 def __init__(self, parent, **kwargs):
  UiFrame.__init__(self, parent, **kwargs)

  self.infoButton = Button(self, text='Get camera info', command=InfoTask(self).run, padding=5)
  self.infoButton.pack(fill=X)


class InstallerFrame(UiFrame):
 MODE_APP = 0
 MODE_APK = 1

 def __init__(self, parent, **kwargs):
  UiFrame.__init__(self, parent, **kwargs)

  self.modeVar = IntVar(value=self.MODE_APP)

  appFrame = Labelframe(self, padding=5)
  appFrame['labelwidget'] = Radiobutton(appFrame, text='Select an app from the app list', variable=self.modeVar, value=self.MODE_APP)
  appFrame.columnconfigure(0, weight=1)
  appFrame.pack(fill=X)

  self.appCombo = Combobox(appFrame, state='readonly')
  self.appCombo.bind('<<ComboboxSelected>>', lambda e: self.modeVar.set(self.MODE_APP))
  self.appCombo.grid(row=0, column=0, sticky=W+E)
  self.setAppList([])

  self.appLoadButton = Button(appFrame, text='Refresh', command=AppLoadTask(self).run)
  self.appLoadButton.grid(row=0, column=1)

  appListLink = Label(appFrame, text='Source', foreground='blue', cursor='hand2')
  appListLink.bind('<Button-1>', lambda e: webbrowser.open_new('https://github.com/' + config.githubAppListUser + '/' + config.githubAppListRepo))
  appListLink.grid(columnspan=2, sticky=W)

  apkFrame = Labelframe(self, padding=5)
  apkFrame['labelwidget'] = Radiobutton(apkFrame, text='Select an apk', variable=self.modeVar, value=self.MODE_APK)
  apkFrame.columnconfigure(0, weight=1)
  apkFrame.pack(fill=X)

  self.apkFile = Entry(apkFrame)
  self.apkFile.grid(row=0, column=0, sticky=W+E)

  self.apkSelectButton = Button(apkFrame, text='Open apk...', command=self.openApk)
  self.apkSelectButton.grid(row=0, column=1)

  self.installButton = Button(self, text='Install selected app', command=InstallTask(self).run, padding=5)
  self.installButton.pack(fill=X, pady=(5, 0))

  self.run(AppLoadTask(self).run)

 def getMode(self):
  return self.modeVar.get()

 def openApk(self):
  fn = askopenfilename(filetypes=[('Apk files', '.apk'), ('All files', '.*')])
  if fn:
   self.apkFile.delete(0, END)
   self.apkFile.insert(0, fn)
   self.modeVar.set(self.MODE_APK)

 def getSelectedApk(self):
  return self.apkFile.get()

 def setAppList(self, apps):
  self.appList = apps
  self.appCombo['values'] = [''] + [app.name for app in apps]
  self.appCombo.current(0)

 def getSelectedApp(self):
  if self.appCombo.current() > 0:
   return self.appList[self.appCombo.current() - 1]


class FirmwareFrame(UiFrame):
 def __init__(self, parent, **kwargs):
  UiFrame.__init__(self, parent, **kwargs)

  datFrame = Labelframe(self, padding=5)
  datFrame['labelwidget'] = Label(datFrame, text='Firmware file')
  datFrame.pack(fill=X)

  self.datFile = Entry(datFrame)
  self.datFile.pack(side=LEFT, fill=X, expand=True)

  self.datSelectButton = Button(datFrame, text='Open...', command=self.openDat)
  self.datSelectButton.pack()

  self.fwUpdateButton = Button(self, text='Update firmware', command=FirmwareUpdateTask(self).run, padding=5)
  self.fwUpdateButton.pack(fill=X, pady=(5, 0))

 def openDat(self):
  fn = askopenfilename(filetypes=[('Firmware files', '.dat'), ('All files', '.*')])
  if fn:
   self.datFile.delete(0, END)
   self.datFile.insert(0, fn)

 def getSelectedDat(self):
  return self.datFile.get()


class UpdaterShellFrame(UiFrame):
 def __init__(self, parent, **kwargs):
  UiFrame.__init__(self, parent, **kwargs)

  self.startUpdaterShellButton = Button(self, text='Start tweaking (updater mode)', command=StartUpdaterShellTask(self).run, padding=5)
  self.startUpdaterShellButton.pack(fill=X)

  self.startSenserShellButton = Button(self, text='Start tweaking (service mode)', command=StartSenserShellTask(self).run, padding=5)
  self.startSenserShellButton.pack(fill=X, pady=(5, 0))


class ChineseRecoveryFrame(UiFrame):
 def __init__(self, parent, **kwargs):
  UiFrame.__init__(self, parent, **kwargs)
  Label(self, text='ILCE-7CM2 | firmware 2.01 | Japanese CX89700_J1 preset').pack(anchor=W)
  Label(self, text='Experimental - not hardware-verified. Check first. A settings backup is not a full unbrick image.',
        foreground='#965000', wraplength=640).pack(fill=X, pady=(3, 8))
  Label(self, text='Service mode only. No firmware updater, region changes, telnet or ADB.',
        wraplength=640).pack(fill=X, pady=(0, 5))

  self.fontDirectory = StringVar(self)
  self.backupDirectory = StringVar(self)
  self.restoreDirectory = StringVar(self)
  self.status = StringVar(self, value='Not connected. No camera operation starts automatically.')
  self.addDirectory('Original font directory', self.fontDirectory, self.chooseFonts, 'Browse...')
  self.addDirectory('New repair backup directory (must not exist)', self.backupDirectory, self.chooseBackup, 'Choose parent...')
  self.addDirectory('Existing backup to restore', self.restoreDirectory, self.chooseRestore, 'Browse...')

  actions = Frame(self)
  actions.pack(fill=X, pady=(8, 5))
  self.checkButton = Button(actions, text='1. Check (no writes)', command=ChineseRecoveryTask(self, 'check').run, padding=5)
  self.repairButton = Button(actions, text='2. Repair Chinese...', command=ChineseRecoveryTask(self, 'repair').run, padding=5)
  self.restoreButton = Button(actions, text='Restore from backup...', command=ChineseRecoveryTask(self, 'restore').run, padding=5)
  for button in (self.checkButton, self.repairButton, self.restoreButton):
   button.pack(side=LEFT, fill=X, expand=True, padx=2)
  Label(self, textvariable=self.status, wraplength=640).pack(fill=X)
  Label(self, text='Repair runs last, then exits service mode. Later ordinary tweaks can delete the fonts again.',
        wraplength=640).pack(fill=X, pady=(5, 0))

 def addDirectory(self, title, variable, command, buttonText):
  frame = Labelframe(self, text=title, padding=5)
  frame.pack(fill=X, pady=2)
  frame.columnconfigure(0, weight=1)
  Entry(frame, textvariable=variable).grid(row=0, column=0, sticky=W+E, padx=(0, 5))
  Button(frame, text=buttonText, command=command).grid(row=0, column=1)

 def chooseFonts(self):
  path = askdirectory(parent=self, title='Select the matching firmware font directory', mustexist=True)
  if path:
   self.fontDirectory.set(path)

 def chooseBackup(self):
  parent = askdirectory(parent=self, title='Select the parent of a NEW recovery directory', mustexist=True)
  if parent:
   path = os.path.join(parent, 'camera-recovery-' + time.strftime('%Y%m%d-%H%M%S'))
   candidate, index = path, 1
   while os.path.exists(candidate):
    candidate = path + '-%d' % index
    index += 1
   self.backupDirectory.set(candidate)

 def chooseRestore(self):
  path = askdirectory(parent=self, title='Select an existing recovery backup', mustexist=True)
  if path:
   self.restoreDirectory.set(path)

 def getArguments(self, operation):
  if operation == 'check':
   return ()
  if operation == 'repair':
   fonts, backup = self.fontDirectory.get().strip(), self.backupDirectory.get().strip()
   if not fonts or not os.path.isdir(fonts):
    raise ValueError('Select the original font directory first.')
   if not all(os.path.isfile(os.path.join(fonts, name)) for name in ChineseLanguageRepair.FONTS):
    raise ValueError('The font directory must contain both original Chinese .ltt files and Sony_DI_Icons.ttf.')
   if not backup or os.path.exists(backup):
    raise ValueError('Choose a new backup directory that does not already exist.')
   if not os.path.isdir(os.path.dirname(os.path.abspath(backup))):
    raise ValueError('The backup directory parent must exist.')
   return fonts, backup
  if operation == 'restore':
   directory = self.restoreDirectory.get().strip()
   if not directory or not all(os.path.isfile(os.path.join(directory, name)) for name in ('manifest.json', 'backup.bin')):
    raise ValueError('Select a recovery directory containing manifest.json and backup.bin.')
   if os.path.exists(os.path.join(directory, 'restore')):
    raise ValueError('This backup already contains a restore directory; it will not be overwritten.')
   return (directory,)
  raise ValueError('Unknown Chinese recovery operation')


class TweakDialog(UiDialog):
 def __init__(self, parent, tweakInterface, endFlag=None):
  self.tweakInterface = tweakInterface
  self.endFlag = endFlag
  UiDialog.__init__(self, parent, "Tweaks")

 def body(self, top):
  tweakFrame = Labelframe(top, padding=5)
  tweakFrame['labelwidget'] = Label(tweakFrame, text='Tweaks')
  tweakFrame.pack(fill=X)

  self.boxFrame = Frame(tweakFrame)
  self.boxFrame.pack(fill=BOTH, expand=True)

  self.applyButton = Button(top, text='Apply', command=TweakApplyTask(self).run, padding=5)
  self.applyButton.pack(fill=X)

  self.updateStatus()

 def updateStatus(self):
  for child in self.boxFrame.winfo_children():
   child.destroy()
  for id, desc, status, value in self.tweakInterface.getTweaks():
   var = IntVar(value=status)
   c = Checkbutton(self.boxFrame, text=desc + '\n' + value, variable=var, command=lambda id=id, var=var: self.setTweak(id, var.get()))
   c.pack(fill=X)

 def setTweak(self, id, enabled):
  self.tweakInterface.setEnabled(id, enabled)
  self.updateStatus()

 def setState(self, state):
  for widget in self.boxFrame.winfo_children() + [self.applyButton]:
   widget.config(state=state)

 def cancel(self, event=None):
  UiDialog.cancel(self, event)
  if self.endFlag:
   self.endFlag.set()


def main():
 """Gui main"""
 parser = argparse.ArgumentParser(description='OpenMemories camera GUI')
 parser.add_argument('--chinese-recovery-only', action='store_true', default=recoveryOnly,
                     help='show only the guarded Chinese recovery controls')
 if version:
  parser.add_argument('--version', action='version', version=version)
 args = parser.parse_args()
 title = 'Chinese recovery' if args.chinese_recovery_only else 'OpenMemories: pmca-gui'
 ui = MainUi(title + (' ' + version if version else ''), recoveryOnly=args.chinese_recovery_only)
 ui.mainloop()


if __name__ == '__main__':
 main()
