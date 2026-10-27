import contextlib
import io
import json
import os
from pathlib import Path
import socketserver
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from pmca.platform.qemu import QemuBackupDataInterface, decodeState, qemuBackupCommand, readEndpoint
from pmca.platform.backup import BackupInterface
from pmca.platform.tweaks import LanguageTweak


def nativeState(flags=None, current=1):
 flags = bytes(1 if i == 1 else 2 for i in range(35)) if flags is None else flags
 return (b'CX89700_J1'.ljust(32, b'\0') + b'ILCE-7CM2'.ljust(16, b'\0') +
         bytes([current]) + flags + struct.pack('<35H', *([1] * 35))).hex()


class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  envelope = json.loads(self.rfile.readline(1025))
  request = envelope['request']
  self.server.requests.append(request)
  assert envelope['token'] == self.server.token
  operation = request['operation']
  failed = operation == 'write' and self.server.failure == 'native'
  if operation == 'write' and not failed:
   self.server.flags[request['id'] - 0x010d008f] = request['value']
  result = {'type': 'backup', 'nonce': request['nonce'], 'operation': operation,
            'ok': not failed, 'stage': 6 if failed else 0,
            'native_rc': -2 if failed else (1 if operation == 'write' else 0),
            'data': '' if failed else nativeState(bytes(self.server.flags))}
  if self.server.failure == 'nonce':
   result['nonce'] = '0' * 32
  self.wfile.write(json.dumps({'session': self.server.session, 'result': result}).encode() + b'\n')


class QemuBackupTests(unittest.TestCase):
 def setUp(self):
  self.temp = tempfile.TemporaryDirectory()
  self.addCleanup(self.temp.cleanup)
  self.root = Path(self.temp.name)
  self.server = socketserver.TCPServer(('127.0.0.1', 0), Handler)
  self.server.requests = []
  self.server.flags = bytearray(1 if i == 1 else 2 for i in range(35))
  self.server.token = 'a' * 64
  self.server.session = 'b' * 32
  self.server.failure = None
  self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
  self.thread.start()
  self.addCleanup(self.close)
  self.endpoint = self.root / 'endpoint.json'
  self.info = dict(schema=1, kind='pmca-qemu-backup', host='127.0.0.1',
                   port=self.server.server_address[1], token=self.server.token, session=self.server.session)
  self.saveEndpoint()

 def close(self):
  self.server.shutdown()
  self.server.server_close()
  self.thread.join()

 def saveEndpoint(self):
  self.endpoint.write_text(json.dumps(self.info))
  self.endpoint.chmod(0o600)

 def test_read_only_check_has_no_native_writes(self):
  with contextlib.redirect_stdout(io.StringIO()):
   self.assertEqual(qemuBackupCommand(self.endpoint, self.root / 'check.jsonl'), 0)
  self.assertEqual([r['operation'] for r in self.server.requests], ['state'])

 def test_explicit_pmca_all35_preserves_current_language_and_attributes(self):
  output = io.StringIO()
  with contextlib.redirect_stdout(output):
   self.assertEqual(qemuBackupCommand(self.endpoint, self.root / 'unlock.jsonl', True, True), 0)
  self.assertIn('PMCA_QEMU_LANGUAGE_UNLOCK_PASS', output.getvalue())
  requests = self.server.requests
  self.assertEqual([r['operation'] for r in requests], ['state'] + ['write'] * 35 + ['sync', 'state'])
  self.assertEqual([r['id'] for r in requests[1:36]], list(range(0x010d008f, 0x010d00b2)))
  self.assertTrue(all(r['value'] == 1 for r in requests[1:36]))
  records = [json.loads(line) for line in (self.root / 'unlock.jsonl').read_text().splitlines()]
  self.assertEqual(records[-1]['state']['enabled'], 35)
  self.assertEqual(records[-1]['state']['current_language'], 1)
  self.assertFalse(records[-1]['persistence_verified'])
  self.assertNotIn(self.server.token, (self.root / 'unlock.jsonl').read_text())

 def test_confirmation_required_before_connect_or_output(self):
  with self.assertRaises(ValueError), patch('socket.create_connection') as connect:
   qemuBackupCommand(self.endpoint, self.root / 'absent.jsonl', True, False)
  connect.assert_not_called()
  self.assertFalse((self.root / 'absent.jsonl').exists())

 def test_native_rejection_stops_without_sync_or_rollback(self):
  self.server.failure = 'native'
  with contextlib.redirect_stdout(io.StringIO()):
   self.assertEqual(qemuBackupCommand(self.endpoint, self.root / 'failed.jsonl', True, True), 1)
  self.assertEqual([r['operation'] for r in self.server.requests], ['state', 'write'])
  text = (self.root / 'failed.jsonl').read_text()
  self.assertIn('native_rc=-2', text)
  self.assertNotIn('unlock_verified', text)

 def test_response_identity_failure_latches(self):
  self.server.failure = 'nonce'
  backend = QemuBackupDataInterface(self.endpoint, lambda event: None)
  with self.assertRaises(ValueError):
   backend.refresh()
  with self.assertRaises(RuntimeError):
   backend.refresh()
  self.assertEqual(len(self.server.requests), 1)

 def test_refuses_nonlocal_or_invalid_endpoint(self):
  for key, value in (('host', 'localhost'), ('host', '192.168.1.1'), ('port', True),
                     ('port', 0), ('kind', 'sony-camera'), ('token', 'x' * 64)):
   original = self.info[key]
   with self.subTest(key=key, value=value):
    self.info[key] = value
    self.saveEndpoint()
    with self.assertRaises(ValueError):
     readEndpoint(self.endpoint)
   self.info[key] = original
  self.assertEqual(self.server.requests, [])

 def test_rejects_wrong_state_and_preserves_physical_policy(self):
  for value in (nativeState(current=255), '00', nativeState(flags=b'\x00' * 35)):
   with self.assertRaises(ValueError):
    decodeState(value)
  backend = QemuBackupDataInterface(self.endpoint, lambda event: None)
  backend.refresh()
  tweak = LanguageTweak(BackupInterface(backend))
  self.assertEqual(tweak.onValue()[7:9], b'\x02\x02')
  self.assertEqual(sum(v == 1 for v in tweak.onValue()), 33)
  for identifier, value in ((0x02cf0401, b'\x19'), (0x010d0096, b'\x02')):
   with self.assertRaises(ValueError):
    backend.writeProp(identifier, value)
  self.assertEqual([r['operation'] for r in self.server.requests], ['state'])


if __name__ == '__main__':
 unittest.main()
