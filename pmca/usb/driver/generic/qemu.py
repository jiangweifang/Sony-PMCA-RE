"""USB transactions over the legacy QEMU TCP wire, not the Backup RPC bridge."""
import math
import socket
import time

from . import *

ADDR = ('127.0.0.1', 7642)

USB_RET_NAK = 0xfffffffe
USB_RET_STALL = 0xfffffffd
USB_TIMEOUT = 5000

TcpUsbHeader = Struct('TcpUsbHeader', [
 ('flags', Struct.INT8),
 ('ep', Struct.INT8),
 ('', 2),
 ('length', Struct.INT32),
])

UsbSetupPacket = Struct('UsbSetupPacket', [
 ('requestType', Struct.INT8),
 ('request', Struct.INT8),
 ('value', Struct.INT16),
 ('index', Struct.INT16),
 ('length', Struct.INT16),
])

UsbDeviceDescriptor = Struct('UsbDeviceDescriptor', [
 ('', 8),
 ('idVendor', Struct.INT16),
 ('idProduct', Struct.INT16),
 ('', 6),
])

UsbConfigurationDescriptor = Struct('UsbConfigurationDescriptor', [
 ('', 2),
 ('wTotalLength', Struct.INT16),
 ('bNumInterfaces', Struct.INT8),
 ('bConfigurationValue', Struct.INT8),
 ('', 3),
])

UsbInterfaceDescriptor = Struct('UsbInterfaceDescriptor', [
 ('', 2),
 ('bInterfaceNumber', Struct.INT8),
 ('', 1),
 ('bNumEndpoints', Struct.INT8),
 ('binterfaceClass', Struct.INT8),
 ('bInterfaceSubClass', Struct.INT8),
 ('bInterfaceProtocol', Struct.INT8),
 ('', 1),
])

UsbEndpointDescriptor = Struct('UsbEndpointDescriptor', [
 ('', 2),
 ('bEndpointAddress', Struct.INT8),
 ('bmAttributes', Struct.INT8),
 ('', 3),
])

sock = None

class _UsbContext(BaseUsbContext):
 def __init__(self, name, classType, driverClass):
  super(_UsbContext, self).__init__('qemu-%s' % name, classType)
  self._driverClass = driverClass

 def __enter__(self):
  global sock
  if not sock:
   sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   try:
    sock.settimeout(.5)
    sock.connect(ADDR)
    sock.settimeout(USB_TIMEOUT / 1000)
   except OSError as error:
    sock.close()
    sock = None
    raise ConnectionError('Cannot connect to the local QEMU USB endpoint: %s' % (error,)) from error
  return self

 def __exit__(self, *ex):
  global sock
  if sock is not None:
   sock.close()
   sock = None

 def listDevices(self, vendor):
  global sock
  if sock:
   dev = _getDevice(UsbBackend(sock), self.classType)
   if dev and dev.idVendor == vendor:
    yield dev

 def openDevice(self, device):
  return self._driverClass(device.handle)


class MscContext(_UsbContext):
 def __init__(self):
  super(MscContext, self).__init__('MSC', USB_CLASS_MSC, MscBbbDriver)

class MtpContext(_UsbContext):
 def __init__(self):
  super(MtpContext, self).__init__('MTP', USB_CLASS_PTP, MtpDriver)

class VendorSpecificContext(_UsbContext):
 def __init__(self):
  super(VendorSpecificContext, self).__init__('vendor-specific', USB_CLASS_VENDOR_SPECIFIC, GenericUsbDriver)


def _getDevice(dev, classType):
 dev.reset()
 config, interfaces = dev.getConfigurationDescriptor(0)
 interface, eps = interfaces[0]
 if interface.binterfaceClass == classType:
  desc = dev.getDeviceDescriptor()
  return UsbDeviceHandle(dev, desc.idVendor, desc.idProduct)


class UsbBackend(BaseUsbBackend):
 FLAG_SETUP = 1
 FLAG_RESET = 2

 DIR_IN = 0x80

 def __init__(self, socket):
  self.socket = socket
  self.failed = False

 def _remaining(self, deadline):
  remaining = deadline - time.monotonic()
  if remaining <= 0:
   raise TimeoutError('QEMU USB transaction timed out')
  return remaining

 def _recvExact(self, size, deadline):
  data = bytearray()
  while len(data) < size:
   self.socket.settimeout(self._remaining(deadline))
   chunk = self.socket.recv(size - len(data))
   if not chunk:
    raise ConnectionError('QEMU USB disconnected during a response')
   data.extend(chunk)
  return bytes(data)

 def _req(self, ep, outData=b'', inLength=0, flags=0, timeout=None):
  if self.failed:
   raise RuntimeError('QEMU USB transport failed; refusing further requests')
  timeout = USB_TIMEOUT if timeout is None else timeout
  if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
   raise ValueError('QEMU USB timeout must be a positive finite number of milliseconds')
  if type(inLength) is not int or inLength < 0:
   raise ValueError('Invalid QEMU USB read length')
  inData = bytearray()
  remaining = inLength if ep & self.DIR_IN else len(outData)
  offset = 0
  deadline = time.monotonic() + timeout / 1000
  previousTimeout = self.socket.gettimeout()
  try:
   while True:
    request = TcpUsbHeader.pack(flags=flags, ep=ep, length=remaining)
    for i in range(100):
     time.sleep(.01)
     self.socket.settimeout(self._remaining(deadline))
     self.socket.sendall(request)
     if not (ep & self.DIR_IN):
      self.socket.settimeout(self._remaining(deadline))
      self.socket.sendall(outData[offset:offset + remaining])
     response = TcpUsbHeader.unpack(self._recvExact(TcpUsbHeader.size, deadline))
     if response.flags != flags or response.ep != ep:
      raise ValueError('QEMU USB response does not match the request')
     if response.length == USB_RET_STALL:
      raise GenericUsbException('QEMU USB endpoint stalled')
     if response.length == USB_RET_NAK:
      continue
     if response.length & 0x80000000:
      raise RuntimeError('QEMU USB error 0x%08x' % response.length)
     if response.length > remaining:
      raise ValueError('QEMU USB response exceeds the requested length')
     break
    else:
     raise TimeoutError('QEMU USB endpoint remained NAK')

    if ep & self.DIR_IN:
     inData.extend(self._recvExact(response.length, deadline))
    elif remaining and not response.length:
     raise RuntimeError('QEMU USB OUT transfer made no progress')
    offset += response.length
    remaining -= response.length
    if remaining == 0 or response.length == 0:
     return bytes(inData)
  except (OSError, ValueError, RuntimeError):
   self.failed = True
   self.socket.close()
   raise
  finally:
   if not self.failed:
    self.socket.settimeout(previousTimeout)

 def _setup(self, type, request, value=0, index=0, outData=b'', inLength=0):
  l = inLength if type & self.DIR_IN else len(outData)
  header = UsbSetupPacket.pack(requestType=type, request=request, value=value, index=index, length=l)
  self._req(0, header, flags=self.FLAG_SETUP)
  return self._req(type & self.DIR_IN, outData, inLength)

 def _getDescriptor(self, type, index, length, lang=0):
  return self._setup(self.DIR_IN, 6, (type << 8) | index, lang, inLength=length)

 def _setAddress(self, addr):
  self._setup(0, 5, addr)

 def _setConfiguration(self, i):
  self._setup(0, 9, i)

 def reset(self):
  for i in range(2):
   time.sleep(1)
   self._req(0, flags=self.FLAG_RESET)
   time.sleep(1)
   self._req(0, flags=self.FLAG_RESET)
   self.getDeviceDescriptor()
   self._setAddress(1)
   self._setConfiguration(1)

 def clearHalt(self, ep):
  self._setup(2, 1, 0, ep)

 def getDeviceDescriptor(self):
  return UsbDeviceDescriptor.unpack(self._getDescriptor(1, 0, UsbDeviceDescriptor.size))

 def getConfigurationDescriptor(self, i):
  l = UsbConfigurationDescriptor.unpack(self._getDescriptor(2, i, UsbConfigurationDescriptor.size)).wTotalLength
  data = self._getDescriptor(2, i, l)

  config = UsbConfigurationDescriptor.unpack(data)
  offset = UsbConfigurationDescriptor.size

  interfaces = []
  for j in range(config.bNumInterfaces):
   interface = UsbInterfaceDescriptor.unpack(data, offset)
   offset += UsbInterfaceDescriptor.size

   endpoints = []
   for k in range(interface.bNumEndpoints):
    endpoints.append(UsbEndpointDescriptor.unpack(data, offset))
    offset += UsbEndpointDescriptor.size

   interfaces.append((interface, endpoints))

  return config, interfaces

 def getId(self):
  desc = self.getDeviceDescriptor()
  return desc.idVendor, desc.idProduct

 def getEndpoints(self):
  config, interfaces = self.getConfigurationDescriptor(0)
  interface, eps = interfaces[0]
  return eps

 def read(self, ep, length, timeout=None):
  return self._req(ep, inLength=length, timeout=timeout)

 def write(self, ep, data):
  return self._req(ep, data)

 def classInterfaceRequestOut(self, request, value, index, data=b''):
  self._setup(0x21, request, value, index, outData=data)

 def vendorRequestOut(self, request, value, index, data=b''):
  self._setup(0x43, request, value, index, outData=data)
