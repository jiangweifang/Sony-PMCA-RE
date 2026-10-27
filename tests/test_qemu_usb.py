"""Host-only USB wire tests; no camera, QEMU guest or authentication emulator."""
from collections import deque
import contextlib
import io
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pmca.commands.usb import importDriver
from pmca.usb.driver import USB_CLASS_VENDOR_SPECIFIC
from pmca.usb.driver.generic import GenericUsbDriver, GenericUsbException
from pmca.usb.driver.generic import qemu
from pmca.usb.sony import SonySenserAuthDevice


def reply(ep, length, flags=0, data=b''):
 return qemu.TcpUsbHeader.pack(flags=flags, ep=ep, length=length) + data


class FakeSocket:
 def __init__(self, chunks=()):
  self.chunks = deque(chunks)
  self.sent = []
  self.closed = False
  self.timeout = 9
  self.timeouts = []
  self.address = None

 def connect(self, address):
  self.address = address

 def settimeout(self, value):
  self.timeout = value
  self.timeouts.append(value)

 def gettimeout(self):
  return self.timeout

 def sendall(self, data):
  if self.closed:
   raise OSError('Closed test socket')
  self.sent.append(data)

 def recv(self, size):
  if not self.chunks:
   return b''
  chunk = self.chunks.popleft()
  if isinstance(chunk, Exception):
   raise chunk
  if len(chunk) > size:
   self.chunks.appendleft(chunk[size:])
  return chunk[:size]

 def close(self):
  self.closed = True


class QemuUsbTests(unittest.TestCase):
 def setUp(self):
  self.sleep = patch.object(qemu.time, 'sleep')
  self.sleep.start()
  self.addCleanup(self.sleep.stop)

 def test_start_stop_use_original_vendor_setup_packets(self):
  wire = FakeSocket([reply(0, 8, 1), reply(0, 0),
                     reply(0, 8, 1), reply(0, 0)])
  backend = qemu.UsbBackend(wire)
  with patch.object(backend, 'reset'):
   device = SonySenserAuthDevice(backend)
  device.start()
  device.stop()
  self.assertEqual(wire.sent[1], bytes.fromhex('4301ff37aad70000'))
  self.assertEqual(wire.sent[5], bytes.fromhex('430100c855280000'))
  self.assertEqual(wire.sent[0], qemu.TcpUsbHeader.pack(flags=1, ep=0, length=8))
  self.assertEqual(wire.sent[2], qemu.TcpUsbHeader.pack(flags=0, ep=0, length=0))
  self.assertEqual(wire.sent[3], b'')
  self.assertFalse(wire.closed)

 def test_control_out_payload_and_class_request(self):
  for method, requestType in (('vendorRequestOut', 0x43), ('classInterfaceRequestOut', 0x21)):
   with self.subTest(method=method):
    wire = FakeSocket([reply(0, 8, 1), reply(0, 3)])
    getattr(qemu.UsbBackend(wire), method)(7, 0x1234, 2, b'abc')
    self.assertEqual(wire.sent[1], qemu.UsbSetupPacket.pack(
     requestType=requestType, request=7, value=0x1234, index=2, length=3))
    self.assertEqual(wire.sent[-1], b'abc')

 def test_fragmented_header_and_payload_are_reassembled(self):
  response = reply(0x81, 5, data=b'abcde')
  wire = FakeSocket([bytes([b]) for b in response])
  self.assertEqual(qemu.UsbBackend(wire).read(0x81, 5), b'abcde')
  self.assertEqual(len(wire.sent), 1)
  self.assertEqual(wire.timeout, 9)

 def test_partial_transfer_continues_only_with_remaining_bytes(self):
  wire = FakeSocket([reply(1, 2), reply(1, 3)])
  qemu.UsbBackend(wire).write(1, b'abcde')
  self.assertEqual(wire.sent[1::2], [b'abcde', b'cde'])
  self.assertEqual([qemu.TcpUsbHeader.unpack(h).length for h in wire.sent[::2]], [5, 3])
  wire = FakeSocket([reply(0x81, 2, data=b'ab'), reply(0x81, 3, data=b'cde')])
  self.assertEqual(qemu.UsbBackend(wire).read(0x81, 5), b'abcde')

 def test_zero_length_in_terminates_short_read(self):
  wire = FakeSocket([reply(0x81, 2, data=b'ab'), reply(0x81, 0)])
  self.assertEqual(qemu.UsbBackend(wire).read(0x81, 5), b'ab')
  self.assertEqual(len(wire.sent), 2)

 def test_only_explicit_nak_is_retried(self):
  wire = FakeSocket([reply(1, qemu.USB_RET_NAK), reply(1, 1)])
  qemu.UsbBackend(wire).write(1, b'a')
  self.assertEqual(wire.sent[1::2], [b'a', b'a'])
  for code in (0xffffffff, 0xfffffffc, 0xfffffffb, 0xfffffffa):
   with self.subTest(code=code):
    wire = FakeSocket([reply(1, code), reply(1, 1)])
    backend = qemu.UsbBackend(wire)
    with self.assertRaisesRegex(RuntimeError, 'QEMU USB error'):
     backend.write(1, b'a')
    self.assertEqual(len(wire.sent), 2)
    self.assertTrue(wire.closed)
    with self.assertRaisesRegex(RuntimeError, 'refusing further'):
     backend.write(1, b'a')
    self.assertEqual(len(wire.sent), 2)

 def test_nak_limit_stops_transport(self):
  wire = FakeSocket([reply(1, qemu.USB_RET_NAK)] * 100)
  with self.assertRaisesRegex(TimeoutError, 'remained NAK'):
   qemu.UsbBackend(wire).write(1, b'a')
  self.assertEqual(len(wire.sent), 200)
  self.assertTrue(wire.closed)

 def test_stall_is_distinct_from_transport_failure(self):
  wire = FakeSocket([reply(1, qemu.USB_RET_STALL), reply(1, 1)])
  backend = qemu.UsbBackend(wire)
  with self.assertRaises(GenericUsbException):
   backend.write(1, b'a')
  self.assertFalse(wire.closed)
  backend.write(1, b'a')

 def test_timeout_and_disconnect_are_not_swallowed_by_start(self):
  for chunks in ([socket.timeout('lost response')], [b'\0\0'], []):
   with self.subTest(chunks=chunks):
    wire = FakeSocket(chunks)
    backend = qemu.UsbBackend(wire)
    with patch.object(backend, 'reset'):
     device = SonySenserAuthDevice(backend)
    with self.assertRaises(OSError):
     device.start()
    self.assertTrue(wire.closed)
    self.assertEqual(len(wire.sent), 2)
    with self.assertRaises(RuntimeError):
     backend.write(1, b'a')

 def test_malformed_response_stops_without_followup(self):
  for response in (reply(2, 1), reply(1, 1, flags=1), reply(1, 2), reply(1, 0)):
   with self.subTest(response=response):
    wire = FakeSocket([response])
    backend = qemu.UsbBackend(wire)
    with self.assertRaises((ValueError, RuntimeError)):
     backend.write(1, b'a')
    self.assertTrue(wire.closed)
    self.assertEqual(len(wire.sent), 2)

 def test_payload_disconnect_latches(self):
  wire = FakeSocket([reply(0x81, 3, data=b'a')])
  backend = qemu.UsbBackend(wire)
  with self.assertRaises(ConnectionError):
   backend.read(0x81, 3)
  self.assertTrue(wire.closed)
  with self.assertRaises(RuntimeError):
   backend.read(0x81, 3)
  self.assertEqual(len(wire.sent), 1)

 def test_timeout_is_bounded_and_restored(self):
  wire = FakeSocket([reply(0x81, 1, data=b'a')])
  self.assertEqual(qemu.UsbBackend(wire).read(0x81, 1, timeout=100), b'a')
  self.assertTrue(all(0 < value <= .1 for value in wire.timeouts[:-1]))
  self.assertEqual(wire.timeouts[-1], 9)
  wire = FakeSocket()
  with patch.object(qemu.time, 'monotonic', side_effect=[0, 1]):
   with self.assertRaises(TimeoutError):
    qemu.UsbBackend(wire).read(0x81, 1, timeout=100)
  self.assertEqual(wire.sent, [])
  self.assertTrue(wire.closed)

 def test_invalid_timeout_is_rejected_before_io(self):
  for timeout in (0, -1, float('inf'), float('nan'), '100'):
   with self.subTest(timeout=timeout):
    wire = FakeSocket()
    with self.assertRaises(ValueError):
     qemu.UsbBackend(wire).read(0x81, 1, timeout)
    self.assertEqual(wire.sent, [])

 def test_qemu_driver_registers_service_class_without_usb_fallback(self):
  with patch('socket.socket', side_effect=AssertionError('Unexpected socket open')):
   with contextlib.redirect_stdout(io.StringIO()):
    drivers = importDriver('qemu')
  self.assertEqual([type(c) for c in drivers._contexts],
                   [qemu.MscContext, qemu.MtpContext, qemu.VendorSpecificContext])
  self.assertEqual(drivers._contexts[-1].classType, USB_CLASS_VENDOR_SPECIFIC)

 def test_service_descriptor_and_driver_keep_original_endpoints(self):
  backend = Mock()
  eps = [SimpleNamespace(bmAttributes=2, bEndpointAddress=0x81),
         SimpleNamespace(bmAttributes=2, bEndpointAddress=0x02)]
  backend.getConfigurationDescriptor.return_value = (None, [
   (SimpleNamespace(binterfaceClass=USB_CLASS_VENDOR_SPECIFIC), eps)])
  backend.getDeviceDescriptor.return_value = SimpleNamespace(idVendor=0x054c, idProduct=0x0336)
  backend.getEndpoints.return_value = eps
  device = qemu._getDevice(backend, USB_CLASS_VENDOR_SPECIFIC)
  driver = qemu.VendorSpecificContext().openDevice(device)
  self.assertIsInstance(driver, GenericUsbDriver)
  self.assertEqual((driver.epIn, driver.epOut), ([0x81], [0x02]))
  self.assertIsNone(qemu._getDevice(backend, 8))

 def test_context_uses_loopback_and_releases_shared_connection(self):
  wire = FakeSocket()
  with patch.object(qemu, 'sock', None), patch.object(qemu.socket, 'socket', return_value=wire):
   with qemu.MscContext(), qemu.VendorSpecificContext():
    self.assertEqual(wire.address, ('127.0.0.1', 7642))
    self.assertIs(qemu.sock, wire)
   self.assertTrue(wire.closed)
   self.assertIsNone(qemu.sock)

 def test_connection_refusal_is_explicit_and_does_not_fall_back(self):
  wire = FakeSocket()
  wire.connect = Mock(side_effect=ConnectionRefusedError('no virtual controller'))
  with patch.object(qemu, 'sock', None), patch.object(qemu.socket, 'socket', return_value=wire):
   with self.assertRaisesRegex(ConnectionError, 'local QEMU USB endpoint'):
    qemu.VendorSpecificContext().__enter__()
   self.assertTrue(wire.closed)
   self.assertIsNone(qemu.sock)


if __name__ == '__main__':
 unittest.main()
