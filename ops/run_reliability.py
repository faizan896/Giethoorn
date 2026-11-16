#!/usr/bin/env python3
"""Bounded public-data reliability experiment with real tunnel/crash faults.

The loopback proxy forwards opaque bytes through the existing HTTP CONNECT route;
TLS remains between the Rust collector and the selected public venue. No service
is installed. All experiment evidence lives outside the strict supervision root.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import socketserver
import subprocess
import threading
import time
from urllib.parse import unquote, urlsplit


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def headers(stream):
    data = bytearray()
    while not data.endswith(b'\r\n\r\n'):
        require(len(data) < 32768, 'CONNECT headers exceed limit')
        byte = stream.recv(1)
        require(byte, 'incomplete CONNECT headers')
        data.extend(byte)
    return bytes(data)


class TunnelProxy(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, upstream, target, record=lambda *args, **kwargs: None):
        try:
            parsed = urlsplit(upstream)
            require(parsed.scheme == 'http' and parsed.hostname, 'HTTP CONNECT upstream required')
            self.address = (parsed.hostname, parsed.port or 80)
            self.authorization = None
            if parsed.username or parsed.password is not None:
                user = unquote(parsed.username or '', errors='strict')
                password = unquote(parsed.password or '', errors='strict')
                self.authorization = base64.b64encode((user + ':' + password).encode())
        except (ValueError, UnicodeError):
            raise RuntimeError('invalid upstream proxy configuration') from None
        require(target in ('api.hyperliquid.xyz:443', 'api.hyperliquid-testnet.xyz:443'),
                'unsupported public target')
        self.target = target
        self.record = record
        self.lock = threading.Lock()
        self.tunnels = {}
        self.counter = 0
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', 0), TunnelHandler)

    def drop_tunnels(self):
        with self.lock:
            active = list(self.tunnels.values())
        for pair in active:
            for stream in pair:
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        return len(active)


class TunnelHandler(socketserver.BaseRequestHandler):
    def handle(self):
        proxy = self.server
        if not proxy.slots.acquire(blocking=False):
            self.request.sendall(b'HTTP/1.1 503 Busy\r\n\r\n')
            return
        remote = None
        identifier = None
        try:
            self.request.settimeout(5)
            first = headers(self.request).split(b'\r\n', 1)[0].decode('ascii')
            if first not in ('CONNECT ' + proxy.target + ' HTTP/1.1',
                             'CONNECT ' + proxy.target + ' HTTP/1.0'):
                self.request.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n')
                return
            remote = socket.create_connection(proxy.address, timeout=5)
            request = ('CONNECT ' + proxy.target + ' HTTP/1.1\r\nHost: ' + proxy.target + '\r\n').encode()
            if proxy.authorization is not None:
                request += b'Proxy-Authorization: Basic ' + proxy.authorization + b'\r\n'
            remote.sendall(request + b'\r\n')
            status = headers(remote).split(b'\r\n', 1)[0].split()
            require(len(status) >= 2 and status[0] in (b'HTTP/1.0', b'HTTP/1.1'), 'invalid upstream response')
            code = int(status[1])
            require(100 <= code <= 599, 'invalid upstream status')
            if code != 200:
                self.request.sendall(('HTTP/1.1 ' + str(code) + ' Upstream rejection\r\n\r\n').encode())
                proxy.record('upstream_rejected', status=code)
                return
            self.request.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
            with proxy.lock:
                proxy.counter += 1
                identifier = proxy.counter
                proxy.tunnels[identifier] = (self.request, remote)
            proxy.record('tunnel_opened', tunnel=identifier)
            while True:
                ready, _, _ = select.select([self.request, remote], [], [], 0.25)
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    destination = remote if source is self.request else self.request
                    destination.sendall(data)
        except (OSError, RuntimeError, ValueError, UnicodeError) as error:
            # Exception text can contain routing/credential details. Keep class only.
            proxy.record('tunnel_closed_with_error', tunnel=identifier, error_class=type(error).__name__)
        finally:
            if identifier is not None:
                with proxy.lock:
                    proxy.tunnels.pop(identifier, None)
                proxy.record('tunnel_closed', tunnel=identifier)
            if remote is not None:
                remote.close()
            proxy.slots.release()


class Evidence:
    def __init__(self, path):
        self.path = path
        self.origin = time.monotonic_ns()
        self.sequence = 0
        self.lock = threading.Lock()

    def record(self, kind, **detail):
        with self.lock:
            self.sequence += 1
            value = dict(schema_version=1, sequence=self.sequence, kind=kind,
                         elapsed_ns=time.monotonic_ns() - self.origin,
                         local_time_ns=time.time_ns(), data=detail)
            with self.path.open('a') as output:
                output.write(json.dumps(value, separators=(',', ':')) + '\n')
                output.flush()
                os.fsync(output.fileno())


def read_records(path, limit=4 * 1024 * 1024):
    if not path.exists():
        return []
    with path.open('rb') as source:
        data = source.read(limit)
    # Monitoring an active file may see its final write in progress. This is not
    # replay or acceptance; the Rust audit subsequently validates actual records.
    lines = data.splitlines(keepends=True)
    return [json.loads(line) for line in lines if line.endswith(b'\n')]


def active_run(root):
    current = None
    for event in read_records(root / 'events.jsonl', 64 * 1024 * 1024):
        if event['kind'] == 'child_started':
            current = event['data']
        elif event['kind'] == 'child_exited':
            current = None
    return current


def fresh_connections(root, run):
    if not run:
        return set()
    values = read_records(root / run['directory'] / 'live-quotes.jsonl')
    return {value['connection_id'] for value in values
            if value.get('kind') in ('depth', 'bbo')
            and value['feeds']['all_required_fresh']}


def owned_collector(root, run, parent):
    require(run is not None, 'no active collector')
    pid = run['pid']
    try:
        stat = Path('/proc') / str(pid) / 'stat'
        fields = stat.read_text().rsplit(')', 1)[1].split()
        require(fields[0] != 'Z' and int(fields[1]) == parent,
                'collector does not belong to experiment supervisor')
        require(os.path.samefile('/proc/' + str(pid) + '/exe', root / 'collector.bin'),
                'collector executable differs from retained snapshot')
    except OSError:
        raise RuntimeError('collector identity is no longer available') from None
    return pid


def validate_schedule(duration, disconnect_at, kill_at, run_duration):
    require(1 <= duration <= 86400 and run_duration > 0, 'duration must be bounded to at most 24 hours')
    require(0 < disconnect_at < kill_at and kill_at + 30 < duration,
            'leave at least 30 seconds after ordered disconnect/crash faults')
    require(kill_at < run_duration, 'initial child must outlast the crash schedule')


def save_new(path, value):
    with path.open('x') as output:
        output.write(json.dumps(value, indent=2) + '\n')
        output.flush()
        os.fsync(output.fileno())


def run(args):
    require(os.name == 'posix' and Path('/proc/self/exe').exists(), 'experiment requires Linux')
    validate_schedule(args.duration_secs, args.disconnect_at_secs, args.kill_at_secs, args.run_duration_secs)
    binary = args.binary.resolve()
    require(binary.is_file() and os.access(binary, os.X_OK), 'executable collector required')
    upstream = next((os.environ[name] for name in ('https_proxy', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY')
                     if os.environ.get(name)), None)
    require(upstream is not None, 'an existing HTTP CONNECT route is required')
    # Validate routing before making experiment artifacts. Never persist its URL.
    target = ('api.hyperliquid.xyz' if args.network == 'mainnet' else 'api.hyperliquid-testnet.xyz') + ':443'
    proxy = TunnelProxy(upstream, target)
    os.umask(0o077)
    output = args.output_dir.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    evidence = Evidence(output / 'faults.jsonl')
    proxy.record = evidence.record
    thread = threading.Thread(target=proxy.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
    root = output / 'supervision'
    command = [str(binary), 'supervise', '--output-dir', str(root), '--coin', 'BTC', '--network', args.network,
               '--duration-secs', str(args.duration_secs), '--run-duration-secs', str(args.run_duration_secs),
               '--feed-profile', 'combined', '--depth-stale-after-ms', '15000', '--bbo-stale-after-ms', '2000',
               '--max-reconnects', '3', '--max-restarts', '5', '--max-segment-bytes', '8388608',
               '--max-run-bytes', '268435456', '--max-total-recording-bytes', '4294967296',
               '--min-free-disk-bytes', '1073741824', '--sample-interval-secs', '5',
               '--parent-pid', str(os.getpid())]
    save_new(output / 'run.json', dict(schema_version=1, command=command,
             duration_secs=args.duration_secs, disconnect_at_secs=args.disconnect_at_secs,
             kill_at_secs=args.kill_at_secs, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
             runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             routing='loopback byte tunnel through inherited HTTP CONNECT proxy; verified venue TLS'))
    env = dict(os.environ)
    route = 'http://127.0.0.1:' + str(proxy.server_address[1])
    for name in ('https_proxy', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY'):
        env[name] = route
    env['no_proxy'] = env['NO_PROXY'] = ''
    stop = threading.Event()
    old_handlers = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    child = None
    disconnected_run = None
    disconnected_connections = None
    network_recovered = False
    killed_run = None
    crash_recovered = False
    failure = None
    thread.start()
    evidence.record('experiment_started', requested_duration_secs=args.duration_secs)
    print(json.dumps({'experiment': str(output), 'status': 'starting'}), flush=True)
    try:
        with (output / 'report.json').open('xb') as stdout, (output / 'command.stderr').open('xb') as stderr:
            child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            evidence.record('supervisor_started', pid=child.pid)
            started = time.monotonic()
            while child.poll() is None:
                elapsed = time.monotonic() - started
                if stop.is_set():
                    evidence.record('stop_requested')
                    child.send_signal(signal.SIGTERM)
                    break
                # Once both recoveries are evidenced, let the collector run
                # without repeatedly parsing an ever-growing active quote file.
                current = active_run(root) if not crash_recovered else None
                connections = fresh_connections(root, current) if not crash_recovered else set()
                if disconnected_run is None and elapsed >= args.disconnect_at_secs and connections:
                    owned_collector(root, current, child.pid)
                    count = proxy.drop_tunnels()
                    if count:
                        disconnected_run = current['run']
                        disconnected_connections = connections
                        evidence.record('disconnect_injected', run=disconnected_run, tunnels=count)
                if disconnected_run is not None and not network_recovered:
                    if current and current['run'] == disconnected_run and connections - disconnected_connections:
                        network_recovered = True
                        evidence.record('network_recovery_observed', run=current['run'], connections=sorted(connections))
                if network_recovered and killed_run is None and elapsed >= args.kill_at_secs and connections:
                    require(current['run'] == disconnected_run, 'initial collector changed before crash injection')
                    pid = owned_collector(root, current, child.pid)
                    os.kill(pid, signal.SIGKILL)
                    killed_run = current['run']
                    evidence.record('collector_killed', run=killed_run, pid=pid, signal=9)
                if killed_run is not None and not crash_recovered and current and current['run'] > killed_run and connections:
                    crash_recovered = True
                    evidence.record('crash_recovery_observed', run=current['run'])
                require(elapsed <= args.disconnect_at_secs + 30 or network_recovered,
                        'network fault/recovery was not observed before deadline')
                require(elapsed <= args.kill_at_secs + 30 or crash_recovered,
                        'collector crash/recovery was not observed before deadline')
                require(elapsed <= args.duration_secs + 30, 'supervisor exceeded experiment deadline')
                stop.wait(1 if crash_recovered else 0.2)
            child.wait(timeout=20)
        require(not stop.is_set(), 'experiment interrupted')
        require(child.returncode == 0, 'supervision exited unsuccessfully; inspect retained evidence')
        require(network_recovered and crash_recovered, 'required fault/recovery evidence is missing')
        audit = subprocess.run([str(binary), 'audit-supervision', '--input', str(root)], capture_output=True, check=True)
        with (output / 'audit.json').open('xb') as destination:
            destination.write(audit.stdout)
        result = json.loads(audit.stdout)
        require(result['integrity'] == 'verified' and result['full_window_completed'], 'final audit did not verify full window')
        evidence.record('experiment_completed', validated_runs=result['validated_runs'], snapshots=result['snapshots'])
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        failure = type(error).__name__
        # Our RuntimeError messages are static and contain no routing credentials.
        evidence.record('experiment_failed', error_class=failure,
                        reason=str(error) if isinstance(error, RuntimeError) else 'operation failed; inspect artifacts')
    finally:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                current = active_run(root)
                if current:
                    try:
                        os.kill(owned_collector(root, current, child.pid), signal.SIGKILL)
                    except (OSError, RuntimeError):
                        pass
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        proxy.drop_tunnels()
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=2)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    status = 'interrupted' if stop.is_set() else ('failed' if failure else 'completed')
    summary = dict(schema_version=1, status=status, requested_duration_secs=args.duration_secs,
                   network_recovery_observed=network_recovered, crash_recovery_observed=crash_recovered,
                   supervisor_exit_code=child.returncode if child else None)
    save_new(output / 'experiment.json', summary)
    print(json.dumps(summary), flush=True)
    return 0 if status == 'completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--network', choices=('mainnet', 'testnet'), default='mainnet')
    parser.add_argument('--duration-secs', type=int, default=86400)
    parser.add_argument('--run-duration-secs', type=int, default=300)
    parser.add_argument('--disconnect-at-secs', type=int, default=30)
    parser.add_argument('--kill-at-secs', type=int, default=60)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, 'experiment preflight failed: ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
