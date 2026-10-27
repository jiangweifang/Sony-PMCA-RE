"""Backend selection tests without enumerating or opening host USB devices."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pmca.usb.driver import USB_CLASS_MSC, USB_CLASS_PTP, USB_CLASS_VENDOR_SPECIFIC
from pmca.usb.driver.generic.libusb import MscContext, MtpContext, VendorSpecificContext


class DescriptorDevice:
 def __init__(self, classType):
  self.idVendor = 0x054c
  self.idProduct = 0x0336 if classType == USB_CLASS_VENDOR_SPECIFIC else 0x0e8a
  self.config = [SimpleNamespace(bInterfaceClass=classType)]

 def __iter__(self):
  return iter([self.config])


class LibusbBackendTests(unittest.TestCase):
 def test_explicit_backend_is_used_for_each_interface_class_without_opening(self):
  backend = object()
  devices = [DescriptorDevice(kind) for kind in (USB_CLASS_MSC, USB_CLASS_PTP, USB_CLASS_VENDOR_SPECIFIC)]
  for contextClass, expected in zip((MscContext, MtpContext, VendorSpecificContext), devices):
   with self.subTest(context=contextClass.__name__):
    with patch('usb.core.find', return_value=devices) as find:
     with contextClass(backend=backend) as context, patch.object(context, 'openDevice') as openDevice:
      result = list(context.listDevices(0x054c))
      self.assertEqual(len(result), 1)
      self.assertIs(result[0].handle, expected)
      find.assert_called_once_with(find_all=True, idVendor=0x054c, backend=backend)
      openDevice.assert_not_called()

 def test_default_preserves_pyusb_backend_selection(self):
  with patch('usb.core.find', return_value=[]) as find:
   self.assertEqual(list(MscContext().listDevices(0x054c)), [])
  find.assert_called_once_with(find_all=True, idVendor=0x054c, backend=None)

 def test_backend_error_is_not_replaced_with_another_backend_or_empty_result(self):
  backend = object()
  with patch('usb.core.find', side_effect=OSError('enumeration failed')) as find:
   with self.assertRaisesRegex(OSError, 'enumeration failed'):
    list(MscContext(backend=backend).listDevices(0x054c))
  find.assert_called_once_with(find_all=True, idVendor=0x054c, backend=backend)

 def test_contexts_keep_backend_selection_independent(self):
  first, second = object(), object()
  firstContext, secondContext = MscContext(backend=first), MscContext(backend=second)
  with patch('usb.core.find', return_value=[]) as find:
   for context in (firstContext, secondContext, firstContext):
    list(context.listDevices(0x054c))
   self.assertEqual([call.kwargs['backend'] for call in find.call_args_list],
                    [first, second, first])


if __name__ == '__main__':
 unittest.main()
