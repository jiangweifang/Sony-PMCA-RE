"""Explicit local QEMU Backup experiment. This module has no USB backend."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct

from .backup import BackupDataInterface, BackupInterface
from .tweaks import LanguageTweak

FIRST_LANGUAGE = 0x010d008f
LANGUAGE_COUNT = 35
STATE_BYTES = 154


def _uniqueObject(pairs):
 result = {}
 for key, value in pairs:
  if key in result:
   raise ValueError('Duplicate JSON field')
  result[key] = value
 return result


def readEndpoint(path):
 path = Path(os.path.abspath(path))
 if any(p.is_symlink() for p in (path, *path.parents)):
  raise ValueError('Endpoint must not use symlinks')
 info = path.stat()
 if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= 1024:
  raise ValueError('Endpoint must be a small ordinary host file')
 if os.name != 'nt' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
  raise ValueError('Endpoint must be owned by this user and private')
 value = json.loads(path.read_bytes(), object_pairs_hook=_uniqueObject)
 if not isinstance(value, dict) or set(value) != {'schema', 'kind', 'host', 'port', 'session', 'token'}:
  raise ValueError('Unknown QEMU endpoint format')
 if (type(value['schema']) is not int or value['schema'] != 1 or
     value['kind'] != 'pmca-qemu-backup' or value['host'] != '127.0.0.1' or
     type(value['port']) is not int or not 1 <= value['port'] <= 65535 or
     not isinstance(value['token'], str) or not re.fullmatch('[0-9a-f]{64}', value['token']) or
     not isinstance(value['session'], str) or not re.fullmatch('[0-9a-f]{32}', value['session'])):
  raise ValueError('Only an explicit loopback QEMU Backup endpoint is accepted')
 return value


def decodeState(value):
 if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{308}', value):
  raise ValueError('Invalid native Backup state length/encoding')
 raw = bytes.fromhex(value)
 region = raw[:32].rstrip(b'\0').decode('ascii')
 model = raw[32:48].rstrip(b'\0').decode('ascii')
 current = raw[48]
 languages = raw[49:84]
 attributes = list(struct.unpack('<35H', raw[84:]))
 if region != 'CX89700_J1' or model != 'ILCE-7CM2' or current > 33:
  raise ValueError('Native guest identity or language enumeration is invalid')
 if any(v not in (1, 2) for v in languages):
  raise ValueError('Invalid language availability from original Backup API')
 return {'region': region, 'model': model, 'current_language': current,
         'languages': languages.hex(), 'enabled': languages.count(1),
         'attributes': attributes}


class QemuBackupDataInterface(BackupDataInterface):
 def __init__(self, endpoint, record):
  self.endpoint = readEndpoint(endpoint)
  self.record = record
  self.state = None
  self.failed = False

 def _request(self, operation, **fields):
  if self.failed:
   raise RuntimeError('Previous Backup request failed; refusing retry or rollback')
  request = dict(operation=operation, nonce=secrets.token_hex(16), **fields)
  self.record({'event': 'request', 'request': request})
  try:
   with socket.create_connection((self.endpoint['host'], self.endpoint['port']), timeout=5) as connection:
    connection.settimeout(45)
    connection.sendall(json.dumps({'token': self.endpoint['token'], 'session': self.endpoint['session'],
                                  'request': request}).encode('ascii') + b'\n')
    with connection.makefile('rb') as reader:
     raw = reader.readline(4097)
    if len(raw) > 4096 or not raw.endswith(b'\n'):
     raise ValueError('Incomplete or oversized QEMU response')
   reply = json.loads(raw, object_pairs_hook=_uniqueObject)
   if not isinstance(reply, dict):
    raise ValueError('Invalid response object')
   if set(reply) == {'error'}:
    raise RuntimeError('QEMU bridge: %s' % reply['error'])
   if set(reply) != {'session', 'result'} or reply['session'] != self.endpoint['session']:
    raise ValueError('QEMU response session mismatch')
   result = reply['result']
   if (not isinstance(result, dict) or
       set(result) != {'type', 'nonce', 'operation', 'ok', 'stage', 'native_rc', 'data'} or
       result['type'] != 'backup' or result['nonce'] != request['nonce'] or
       result['operation'] != operation or type(result['ok']) is not bool or
       type(result['stage']) is not int or type(result['native_rc']) is not int):
    raise ValueError('QEMU response request identity or shape differs')
   self.record({'event': 'native_result', 'result': result})
   if not result['ok']:
    raise RuntimeError('Original Backup API rejected operation: stage=%d native_rc=%d' %
                       (result['stage'], result['native_rc']))
   if result['stage'] != 0 or result['native_rc'] != (1 if operation == 'write' else 0):
    raise ValueError('Unexpected original API return status')
   state = decodeState(result['data'])
   self.state = state
   return state
  except (OSError, ValueError, RuntimeError) as error:
   self.failed = True
   self.record({'event': 'failure', 'operation': operation, 'error': str(error),
                'completion_may_be_unknown': operation != 'state'})
   raise

 def refresh(self):
  return self._request('state')

 def getRegion(self):
  if self.state is None:
   raise RuntimeError('Read native QEMU state before using Backup properties')
  return self.state['region']

 def readProp(self, id):
  if self.state is None or not FIRST_LANGUAGE <= id < FIRST_LANGUAGE + LANGUAGE_COUNT:
   raise ValueError('Only the verified language properties are exposed')
  return bytes.fromhex(self.state['languages'])[id - FIRST_LANGUAGE:id - FIRST_LANGUAGE + 1]

 def writeProp(self, id, data):
  if not FIRST_LANGUAGE <= id < FIRST_LANGUAGE + LANGUAGE_COUNT or data != b'\x01':
   raise ValueError('Only enabling language availability is allowed')
  before = dict(self.state)
  result = self._request('write', id=id, value=1)
  expected = bytearray.fromhex(before['languages'])
  expected[id - FIRST_LANGUAGE] = 1
  if (result['languages'] != expected.hex() or result['attributes'] != before['attributes'] or
      result['current_language'] != before['current_language']):
   self.failed = True
   raise ValueError('Native readback changed unrelated language state')

 def sync(self):
  return self._request('sync')


def qemuBackupCommand(endpoint, report, unlock=False, confirmed=False):
 if unlock and not confirmed:
  raise ValueError('QEMU-only all35 unlock requires explicit confirmation')
 report = Path(os.path.abspath(report))
 if any(p.is_symlink() for p in (report, *report.parents)):
  raise ValueError('Report must not use symlinks')
 fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
 with os.fdopen(fd, 'w', encoding='utf-8') as output:
  def record(event):
   output.write(json.dumps(event, sort_keys=True) + '\n')
   output.flush()
   os.fsync(output.fileno())
  record({'event': 'scope', 'scope': 'PMCA over local QEMU native Backup RPC; not Sony USB authentication',
          'fonts_modified': False, 'current_language_write_allowed': False,
          'physical_camera_access': False, 'persistence_verified': False})
  try:
   backend = QemuBackupDataInterface(endpoint, record)
   before = backend.refresh()
   record({'event': 'before', 'state': before})
   print('QEMU %s %s: %d / 35 languages; current=%02x' %
         (before['model'], before['region'], before['enabled'], before['current_language']))
   if not unlock:
    return 0
   if bytes.fromhex(before['languages']) != bytes(1 if i == 1 else 2 for i in range(35)):
    raise ValueError('Expected the untouched J1 language availability baseline')
   interface = BackupInterface(backend)
   # Keep physical J1 onValue() -> JP-MOD unchanged; all35 is explicit here only.
   desired = LanguageTweak(interface)._getLangs('ALLLANG')
   if desired != b'\x01' * 35:
    raise ValueError('PMCA ALLLANG policy changed; experiment requires review')
   record({'event': 'policy', 'policy': 'QEMU-only all35 including Chinese',
           'physical_JP_MOD_unchanged': True,
           'tweaks_sha256': hashlib.sha256(Path(__file__).with_name('tweaks.py').read_bytes()).hexdigest()})
   interface.writeProp('language', desired)
   synced = backend.sync()
   after = backend.refresh()
   if (after != synced or after['languages'] != '01' * 35 or
       after['attributes'] != before['attributes'] or after['current_language'] != before['current_language']):
    raise ValueError('Final original Backup readback did not match all35')
   record({'event': 'unlock_verified', 'state': after, 'persistence_verified': False,
           'menu_language_selected': False, 'font_restoration_verified': False})
   print('PMCA_QEMU_LANGUAGE_UNLOCK_PASS 35/35; original Backup API readback verified.')
   print('No font restore or language selection performed. Reboot persistence is not verified.')
   return 0
  except (OSError, ValueError, RuntimeError) as error:
   record({'event': 'aborted', 'error': str(error), 'automatic_rollback': False})
   print('PMCA QEMU Backup failed: %s. Stopped without automatic retry or rollback.' % error)
   return 1
