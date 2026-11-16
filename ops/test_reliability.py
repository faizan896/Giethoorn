import base64
import importlib.util
import os
from pathlib import Path
import socket
import threading
import unittest

SPEC = importlib.util.spec_from_file_location('reliability', Path(__file__).parent / 'run_reliability.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReliabilityTests(unittest.TestCase):
    def test_tunnel_forwards_bytes_preserves_auth_and_can_disconnect_then_reconnect(self):
        upstream = socket.socket()
        upstream.bind(('127.0.0.1', 0))
        upstream.listen()
        upstream.settimeout(5)
        requests = []

        def echo():
            for _ in range(2):
                stream, _ = upstream.accept()
                with stream:
                    stream.settimeout(5)
                    requests.append(MODULE.headers(stream))
                    stream.sendall(b'HTTP/1.1 200 OK\r\n\r\n')
                    while True:
                        value = stream.recv(4096)
                        if not value:
                            break
                        stream.sendall(value)

        worker = threading.Thread(target=echo)
        worker.start()
        proxy = MODULE.TunnelProxy('http://user%40test:pass%3Aword@127.0.0.1:' + str(upstream.getsockname()[1]),
                                   'api.hyperliquid.xyz:443')
        server = threading.Thread(target=proxy.serve_forever, kwargs={'poll_interval': 0.05})
        server.start()
        try:
            for ordinal in range(2):
                with socket.create_connection(proxy.server_address, timeout=5) as client:
                    client.sendall(b'CONNECT api.hyperliquid.xyz:443 HTTP/1.1\r\nHost: api.hyperliquid.xyz:443\r\n\r\n')
                    self.assertIn(b'200', MODULE.headers(client))
                    client.sendall(b'opaque-end-to-end-tls-bytes')
                    self.assertEqual(client.recv(4096), b'opaque-end-to-end-tls-bytes')
                    if ordinal == 0:
                        self.assertEqual(proxy.drop_tunnels(), 1)
                        self.assertEqual(client.recv(4096), b'')
            self.assertTrue(all(b'Proxy-Authorization: Basic ' + base64.b64encode(b'user@test:pass:word') in r for r in requests))
        finally:
            proxy.drop_tunnels()
            proxy.shutdown()
            proxy.server_close()
            server.join(timeout=5)
            worker.join(timeout=5)
            upstream.close()
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(requests), 2)

    def test_proxy_rejects_other_targets_without_contacting_the_upstream(self):
        proxy = MODULE.TunnelProxy('http://127.0.0.1:1', 'api.hyperliquid.xyz:443')
        server = threading.Thread(target=proxy.serve_forever, kwargs={'poll_interval': 0.05})
        server.start()
        try:
            with socket.create_connection(proxy.server_address, timeout=2) as client:
                client.sendall(b'CONNECT unexpected.invalid:443 HTTP/1.1\r\n\r\n')
                self.assertIn(b'403', MODULE.headers(client))
            self.assertEqual(proxy.counter, 0)
        finally:
            proxy.shutdown()
            proxy.server_close()
            server.join(timeout=5)

    def test_invalid_route_errors_do_not_echo_credentials(self):
        for route in ('https://secret-user:secret-password@localhost',
                      'http://secret-user:secret-password@localhost:invalid'):
            with self.assertRaises(RuntimeError) as error:
                MODULE.TunnelProxy(route, 'api.hyperliquid.xyz:443')
            self.assertNotIn('secret-', str(error.exception))

    def test_only_a_bounded_ordered_fault_schedule_is_accepted(self):
        MODULE.validate_schedule(86400, 30, 60, 300)
        MODULE.validate_schedule(90, 10, 25, 45)
        for values in ((86401, 30, 60, 300), (90, 25, 10, 45), (50, 10, 25, 45), (90, 10, 25, 20)):
            with self.assertRaises(RuntimeError):
                MODULE.validate_schedule(*values)

    def test_fault_target_must_be_a_child_running_the_retained_executable(self):
        with self.assertRaises(RuntimeError):
            MODULE.owned_collector(Path('/tmp'), {'pid': os.getpid()}, os.getpid())


if __name__ == '__main__':
    unittest.main()
