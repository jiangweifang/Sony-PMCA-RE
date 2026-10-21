"""Read-only ILCE-7CM2 2.01 Chinese-language diagnostic probe.

This standalone tool is intentionally limited. It NEVER reads files, NEVER reads
preset backup (getBackupPresetData / PDT_READ 0x603/5), NEVER writes settings or
files, and NEVER enters the firmware updater, region, telnet or ADB paths.

On the verified 2.01 firmware the only safe service reads are:
  * AdjustControl backup property read  (pFunc 0x40, block 0x603, code 1)
  * ProductInfo HASP read               (pFunc 0x10)
The destructive font-deletion branch is tied to preset-data read/write
(0x603/4 and 0x603/5), which this probe does not issue.

Usage (run with the dedicated env python):
  D:\\miniconda3\\envs\\pmca-a7c2\\python.exe tools_chinese_readonly_probe.py
  D:\\miniconda3\\envs\\pmca-a7c2\\python.exe tools_chinese_readonly_probe.py --read
"""

import os
import sys
import time

# Make pyusb's default usb.core.find() resolve the bundled libusb-1.0.dll.
try:
 import libusb_package
 _dll_dir = os.path.dirname(str(libusb_package.get_library_path()))
 os.environ['PATH'] = _dll_dir + os.pathsep + os.environ.get('PATH', '')
except Exception as error:
 print('Warning: could not configure libusb-package DLL path: %s' % error)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pmca.commands.usb import importDriver, listDevices
from pmca.usb.driver.generic import GenericUsbDriver
from pmca.usb.sony import (
 SonyMscExtCmdDevice,
 SonySenserDevice,
 SonySenserAuthDevice,
 SonySenserCamera,
)

# Backup property IDs (plain AdjustControl 0x603/1 reads; no preset backup).
BACKUP_MODEL_NAME = 0x003e0005
BACKUP_MODEL_CODE = 0x00e70000
BACKUP_SERIAL = 0x00e70003
LANGUAGE_IDS = (0x010d0096, 0x010d0097)


def enumerate_devices():
 """Host-side only: list Sony USB devices and whether libusb can open them."""
 print('== Host-side enumeration (no camera command sent) ==')
 import usb.core
 present = []
 try:
  for dev in usb.core.find(find_all=True, idVendor=0x054c):
   present.append((dev.idVendor, dev.idProduct))
   print('USB device present: VID_%04X PID_%04X' % (dev.idVendor, dev.idProduct))
 except Exception as error:
  print('Low-level enumeration error: %s' % error)
 if not present:
  print('No Sony (VID_054C) USB device is present. Check the cable/connection.')
  return []

 openable = []
 for vid, pid in present:
  dev = usb.core.find(idVendor=vid, idProduct=pid)
  try:
   dev.get_active_configuration()
   openable.append((vid, pid))
   print('  PID_%04X: libusb can open it (libusb-compatible driver bound).' % pid)
  except NotImplementedError:
   print('  PID_%04X: libusb CANNOT open it -> still on the Windows usbstor/native')
   print('           driver. A libusb-win32 / WinUSB driver (Zadig) is required')
   print('           before service mode.')
  except Exception as error:
   print('  PID_%04X: open check failed: %s' % (pid, error))
 return openable


def _safe_reads(camera):
 """Issue only plain backup-property reads. No files, no preset backup."""
 result = {}
 try:
  result['model_name'] = camera.readBackup(BACKUP_MODEL_NAME).rstrip(b'\0').decode('ascii', 'replace')
 except Exception as error:
  result['model_name'] = 'ERROR: %s' % error
 try:
  result['model_code'] = camera.readBackup(BACKUP_MODEL_CODE).hex()
 except Exception as error:
  result['model_code'] = 'ERROR: %s' % error
 try:
  result['serial'] = camera.readBackup(BACKUP_SERIAL).hex()
 except Exception as error:
  result['serial'] = 'ERROR: %s' % error
 for lang_id in LANGUAGE_IDS:
  try:
   raw = camera.readBackup(lang_id)
   result['lang_0x%08x' % lang_id] = '%s (raw=%s)' % (
    'enabled' if raw == b'\x01' else ('disabled' if raw == b'\x02' else 'unknown'),
    raw.hex(),
   )
  except Exception as error:
   result['lang_0x%08x' % lang_id] = 'ERROR: %s' % error
 return result


def read_diagnostics():
 """Authenticate, switch to service mode, and read identity + language flags."""
 with importDriver('libusb') as driver:
  devices = list(listDevices(driver))
  if len(devices) != 1:
   print('Expected exactly one Sony device, found %d. Stopping.' % len(devices))
   return
  device = devices[0]

  if isinstance(device, SonyMscExtCmdDevice):
   if not isinstance(device.driver, GenericUsbDriver):
    print('Error: mass storage device is not on a libusb driver. Run Zadig first.')
    return
   print('Mass storage camera found. Switching to service mode...')
   auth = SonySenserAuthDevice(device.driver)
   auth.start()
   auth.authenticate()
   device = None
   for _ in range(10):
    time.sleep(0.5)
    try:
     candidates = list(listDevices(driver, True))
     if len(candidates) == 1 and isinstance(candidates[0], SonySenserDevice):
      device = candidates[0]
      break
    except Exception:
     pass
   if device is None:
    print('Timed out waiting for the camera to switch to service mode.')
    return

  if not isinstance(device, SonySenserDevice):
   print('Camera is not in service mode. Switch to mass storage mode and retry.')
   return
  if not isinstance(device.driver, GenericUsbDriver):
   print('Error: service-mode device is not on a libusb driver. Run Zadig first.')
   return

  print('Authenticating service mode...')
  auth = SonySenserAuthDevice(device.driver)
  auth.start()
  auth.authenticate()
  try:
   camera = SonySenserCamera(device)
   print('== Read-only diagnostics (backup property reads only) ==')
   for key, value in _safe_reads(camera).items():
    print('  %-16s %s' % (key + ':', value))
   print('No files, preset backup, or writes were issued.')
  finally:
   auth.stop()


def main():
 do_read = '--read' in sys.argv[1:]
 openable = enumerate_devices()
 if not do_read:
  print('\nEnumerate-only mode. Pass --read to authenticate and read identity +')
  print('language flags (still no files, no preset backup, no writes).')
  return
 if not openable:
  print('\nCannot proceed with --read: no libusb-openable Sony device. Run Zadig.')
  return
 read_diagnostics()


if __name__ == '__main__':
 main()
