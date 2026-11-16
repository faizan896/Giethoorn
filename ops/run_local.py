#!/usr/bin/env python3
"""Run the unchanged Linux reliability experiment on a direct local connection."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import select
import socket
import socketserver
import threading

SPEC = importlib.util.spec_from_file_location('local_experiment', Path(__file__).with_name('run_reliability.py'))
EXPERIMENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPERIMENT)
PROXY_KEYS = ('https_proxy', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY', 'no_proxy', 'NO_PROXY')
TARGETS = {'mainnet': 'api.hyperliquid.xyz:443', 'testnet': 'api.hyperliquid-testnet.xyz:443'}


class DirectProxy(socketserver.ThreadingTCPServer):
    """Loopback-only, bounded CONNECT relay; never terminates venue TLS."""
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, target):
        EXPERIMENT.require(target in TARGETS.values(), 'unsupported public target')
        self.target = target
        self.address = (target.rsplit(':', 1)[0], 443)
        self.slots = threading.BoundedSemaphore(8)
        self.lock = threading.Lock()
        self.streams = set()
        super().__init__(('127.0.0.1', 0), DirectHandler)

    def disconnect(self):
        with self.lock:
            streams = list(self.streams)
        for stream in streams:
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class DirectHandler(socketserver.BaseRequestHandler):
    def handle(self):
        proxy = self.server
        if not proxy.slots.acquire(blocking=False):
            self.request.sendall(b'HTTP/1.1 503 Busy\r\n\r\n')
            return
        remote = None
        try:
            self.request.settimeout(5)
            first = EXPERIMENT.headers(self.request).split(b'\r\n', 1)[0].decode('ascii')
            if first not in ('CONNECT '+proxy.target+' HTTP/1.1', 'CONNECT '+proxy.target+' HTTP/1.0'):
                self.request.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n')
                return
            remote = socket.create_connection(proxy.address, timeout=5)
            with proxy.lock:
                proxy.streams.update((self.request, remote))
            self.request.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
            while True:
                ready, _, _ = select.select([self.request, remote], [], [], .25)
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (remote if source is self.request else self.request).sendall(data)
        except (OSError, RuntimeError, ValueError, UnicodeError):
            # Routing errors may include private configuration; expose no text.
            pass
        finally:
            with proxy.lock:
                proxy.streams.discard(self.request)
                if remote is not None:
                    proxy.streams.discard(remote)
            if remote is not None:
                remote.close()
            proxy.slots.release()


def run(args):
    EXPERIMENT.require(os.name == 'posix' and Path('/proc/self/exe').exists(), 'local experiment requires Linux; use the container')
    EXPERIMENT.validate_schedule(args.duration_secs, args.disconnect_at_secs, args.kill_at_secs, args.run_duration_secs)
    EXPERIMENT.require(args.network in TARGETS and args.route in ('direct', 'inherit'), 'unsupported network route')
    EXPERIMENT.require(args.binary.is_file() and os.access(args.binary, os.X_OK), 'executable collector required')
    if args.route == 'inherit':
        EXPERIMENT.require(any(os.environ.get(key) for key in PROXY_KEYS[:4]), 'inherited HTTP CONNECT proxy required')
    os.umask(0o077)
    output = args.output_dir.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    EXPERIMENT.save_new(output/'local-run.json', dict(local_launcher_version=1, route=args.route,
        routing='two loopback CONNECT relays then direct venue TCP; verified venue TLS' if args.route == 'direct'
                else 'experiment relay through inherited HTTP CONNECT route; verified venue TLS',
        launcher_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        experiment_runner_sha256=hashlib.sha256(Path(EXPERIMENT.__file__).read_bytes()).hexdigest(),
        duration_secs=args.duration_secs, is_24_hour_request=args.duration_secs == 86400,
        strategy_enabled=False, full_window_verified=False))
    original = {key: os.environ.get(key) for key in PROXY_KEYS}
    proxy = None
    worker = None
    result = 1
    failure = None
    try:
        if args.route == 'direct':
            proxy = DirectProxy(TARGETS[args.network])
            worker = threading.Thread(target=proxy.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
            worker.start()
            for key in PROXY_KEYS[:4]:
                os.environ[key] = 'http://127.0.0.1:'+str(proxy.server_address[1])
            os.environ['no_proxy'] = os.environ['NO_PROXY'] = ''
        experiment_args = argparse.Namespace(**vars(args))
        experiment_args.output_dir = output/'experiment'
        result = EXPERIMENT.run(experiment_args)
    except (OSError, RuntimeError, ValueError) as error:
        failure = type(error).__name__
    finally:
        if proxy is not None:
            proxy.disconnect()
            if worker is not None and worker.is_alive():
                proxy.shutdown()
            proxy.server_close()
            if worker is not None:
                worker.join(timeout=2)
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    EXPERIMENT.save_new(output/'local-result.json', dict(local_launcher_version=1,
        status='completed' if result == 0 else 'failed', experiment_exit_code=result,
        error_class=failure, full_window_verified=result == 0,
        verified_24_hour_window=result == 0 and args.duration_secs == 86400))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--network', choices=tuple(TARGETS), default='mainnet')
    parser.add_argument('--route', choices=('direct', 'inherit'), default='direct')
    parser.add_argument('--duration-secs', type=int, default=86400)
    parser.add_argument('--run-duration-secs', type=int, default=300)
    parser.add_argument('--disconnect-at-secs', type=int, default=30)
    parser.add_argument('--kill-at-secs', type=int, default=60)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, 'Local preflight failed: '+type(error).__name__+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
