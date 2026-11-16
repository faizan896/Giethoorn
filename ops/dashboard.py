#!/usr/bin/env python3
"""Read-only local monitor for a schema-2 reliability experiment.

Reads control/telemetry and normalized stdout only. Never opens market segments
for replay, acquires their locks, changes the collector, or sends venue requests.
"""
import argparse
from collections import deque
from datetime import datetime, timezone
import errno
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit

TEMPLATE = Path(__file__).resolve().parent.parent / 'web' / 'index.html'
THEME = TEMPLATE.with_name('theme.css')
MAX_METADATA = 16 * 1024 * 1024
MAX_CONTROL = 64 * 1024 * 1024
MAX_QUOTES = 2 * 1024 * 1024
RUN_NAME = re.compile(r'run-[0-9]{6}\Z')


def plain_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('monitor input must be a regular file')


def json_file(path, optional=False):
    if optional and not path.exists():
        return None
    plain_file(path)
    with path.open('rb') as source:
        data = source.read(MAX_METADATA + 1)
    if len(data) > MAX_METADATA:
        raise ValueError('metadata exceeds monitor limit')
    # Final reports are written once. A concurrent final write is still pending.
    if optional and not data.endswith(b'\n'):
        return None
    return json.loads(data)


def json_lines(path, limit, tail=False, optional=False):
    if optional and not path.exists():
        return []
    plain_file(path)
    with path.open('rb') as source:
        length = os.fstat(source.fileno()).st_size
        if not tail and length > limit:
            raise ValueError('control evidence exceeds monitor limit')
        start = max(0, length - limit) if tail else 0
        if start:
            source.seek(start - 1)
            boundary = source.read(1) == b'\n'
            source.seek(start)
        else:
            boundary = True
        data = source.read(limit)
    if not boundary:
        data = data.partition(b'\n')[2]
    # Only the unterminated last fragment is provisional. A corrupt complete
    # record is an error, never silently skipped or presented as healthy.
    return [json.loads(line) for line in data.splitlines(keepends=True)
            if line.endswith(b'\n')]


def writer_active(root):
    path = root / 'supervisor.lock'
    plain_file(path)
    with path.open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EACCES):
                return True
            raise
        fcntl.flock(lock, fcntl.LOCK_UN)
    return False


def quote_view(quote, source, run):
    return dict(source=source, run=run, sequence=quote['sequence'],
                connection_id=quote['connection_id'],
                received_ms=quote['local_time_ns'] // 1_000_000,
                exchange_ms=quote['exchange_time_ms'],
                bid=quote['bid'], ask=quote['ask'], mid=quote['mid'], spread=quote['spread'])


def snapshot(experiment, now_ns=None):
    now = time.time_ns() if now_ns is None else now_ns
    experiment = Path(experiment)
    root = experiment / 'supervision'
    config = json_file(root / 'configuration.json')
    if config.get('event_schema_version') != 2 or not config.get('feed_policy'):
        raise ValueError('dashboard requires an explicit schema-2 feed profile')
    controls = json_lines(root / 'events.jsonl', MAX_CONTROL)
    if not controls or controls[0]['kind'] != 'started':
        raise ValueError('supervisor start evidence is missing')
    resources = json_lines(root / 'resources.jsonl', MAX_CONTROL, tail=True, optional=True)
    faults = json_lines(experiment / 'faults.jsonl', MAX_CONTROL, optional=True)
    final = json_file(experiment / 'experiment.json', optional=True)
    summary = json_file(root / 'summary.json', optional=True)
    audit = json_file(experiment / 'audit.json', optional=True)
    active = writer_active(root)
    origin_wall = controls[0]['local_time_ns'] - controls[0]['elapsed_ns']
    recorded_elapsed = max(controls[-1]['elapsed_ns'], resources[-1]['elapsed_ns'] if resources else 0)
    requested = config['duration_secs'] * 1_000_000_000
    runs = {}
    for event in controls:
        data = event['data']
        if event['kind'] == 'child_started':
            name = data['directory']
            if not RUN_NAME.fullmatch(name) or name != 'run-%06d' % data['run']:
                raise ValueError('noncanonical run identity')
            runs[data['run']] = dict(run=data['run'], directory=name, pid=data['pid'],
                elapsed_start_ns=event['elapsed_ns'], started_ms=event['local_time_ns'] // 1_000_000,
                status='recording', comparison=None, snapshots=None, recording_bytes=None,
                duration_ms=None, exit_code=None, signal=None)
        elif event['kind'] == 'child_exited':
            entry = runs[data['run']]
            entry.update(status='validating', exit_code=data['exit_code'], signal=data['signal'],
                         duration_ms=(event['elapsed_ns'] - entry['elapsed_start_ns']) // 1_000_000)
        elif event['kind'] == 'child_validated':
            entry = runs[data['run']]
            entry.update(status='verified' if data['comparison'] == 'exact' else 'recovered',
                         comparison=data['comparison'], snapshots=data['snapshots'],
                         recording_bytes=data['recording_bytes'])
    current = next((entry for entry in reversed(list(runs.values())) if entry['status'] == 'recording'), None)
    validated = [entry for entry in runs.values() if entry['comparison'] is not None]
    observations = []
    # Bounded reads of the two most recent normalized output files. The chart is
    # a view of this loaded window, not a full archive or a replay verification.
    for entry in list(runs.values())[-2:]:
        path = root / entry['directory']
        if path.is_symlink():
            raise ValueError('run directory must not be a symlink')
        for value in json_lines(path / 'live-quotes.jsonl', MAX_QUOTES, tail=True, optional=True):
            if value.get('normalization_version') != 2:
                raise ValueError('unsupported normalized output version')
            observations.append((entry, value))
    latest_active = next((value for entry, value in reversed(observations)
                          if current and entry['run'] == current['run']), None)
    quotes = {'bbo': None, 'depth': None}
    series = {'bbo': deque(maxlen=4000), 'depth': deque(maxlen=4000)}
    for entry, value in observations:
        source = value['kind']
        quote = value.get('quote')
        if source not in series or not quote:
            continue
        quotes[source] = quote_view(quote, source, entry['run'])
        if quote['mid'] is not None:
            series[source].append(dict(x_ms=(entry['elapsed_start_ns'] + value['monotonic_ns']) // 1_000_000,
                received_ms=value['local_time_ns'] // 1_000_000, mid=quote['mid'],
                run=entry['run'], connection_id=value['connection_id']))
    policy = config['feed_policy']
    # A running producer can append while files are read. Capture the observer's
    # time after those reads so a newly arrived quote is not mistaken for a
    # backwards wall clock. Tests can supply a fixed observation time explicitly.
    if now_ns is None:
        now = time.time_ns()
    clock_uncertain = now < origin_wall + recorded_elapsed - 1_000_000_000
    elapsed = summary['elapsed_ns'] if summary else max(recorded_elapsed, now - origin_wall) if active else recorded_elapsed
    feeds = {}
    for source in ('depth', 'bbo'):
        selected = policy['profile'] in (source, 'combined')
        limit_ms = policy[source + '_stale_after_ms']
        state = latest_active['feeds'].get(source) if latest_active else None
        delay_ns = now - latest_active['local_time_ns'] if latest_active else None
        uncertain = clock_uncertain or (delay_ns is not None and delay_ns < 0)
        age_ns = state.get('age_ns') if state else None
        age_ms = (age_ns + max(0, delay_ns)) / 1_000_000 if age_ns is not None else None
        status = state['status'] if state else 'awaiting_data'
        if not selected:
            status = 'disabled'
        elif not active or not current or status == 'disconnected':
            status = 'disconnected'
        elif uncertain:
            status = 'clock_uncertain'
        elif (age_ms is not None and age_ms >= limit_ms) or (delay_ns is not None and delay_ns >= limit_ms * 1_000_000):
            status = 'stale'
        feeds[source] = dict(status=status, recorded_status=state['status'] if state else None,
            age_ms=round(age_ms, 1) if age_ms is not None else None,
            threshold_ms=limit_ms, acknowledged=bool(state and state['acknowledged']),
            latest_sequence=state.get('latest_sequence') if state else None,
            quote=quotes[source], selected=selected)
    passed = bool(final and final.get('status') == 'completed' and summary
                  and summary.get('status') in ('completed', 'completed_with_restarts')
                  and summary.get('elapsed_ns', 0) >= requested and audit
                  and audit.get('integrity') == 'verified' and audit.get('full_window_completed'))
    failed = bool((final and final.get('status') == 'failed') or
                  (summary and summary.get('status') in ('failed', 'budget_exhausted')))
    gate = 'passed' if passed else 'failed' if failed else 'running' if active else 'audit_pending' if summary and summary.get('status') in ('completed', 'completed_with_restarts') else 'incomplete'
    latest_resource = resources[-1] if resources else {}
    activity_labels = {
        'experiment_started': ('Experiment started', 'Public BTC collection began.'),
        'disconnect_injected': ('Connection fault injected', 'The owned tunnel was deliberately closed.'),
        'network_recovery_observed': ('Connection recovered', 'Both feeds returned on a new connection.'),
        'collector_killed': ('Collector crash injected', 'The owned collector received SIGKILL.'),
        'crash_recovery_observed': ('Collector recovered', 'A replacement child produced usable data.'),
        'experiment_completed': ('Full experiment verified', 'The window and final archive audit passed.'),
        'experiment_failed': ('Experiment failed', 'Review retained evidence before continuing.'),
        'stop_requested': ('Stop requested', 'The experiment was asked to shut down.'),
    }
    activity = [dict(kind=f['kind'], title=activity_labels[f['kind']][0],
                     detail=activity_labels[f['kind']][1], at_ms=f['local_time_ns'] // 1_000_000)
                for f in faults if f['kind'] in activity_labels]
    chart = {}
    for source, values in series.items():
        points = list(values)
        stride = max(1, math.ceil(len(points) / 700))
        chart[source] = points[::stride]
        if points and chart[source][-1] != points[-1]:
            chart[source].append(points[-1])
    if current and not active:
        current['status'] = 'stopped'
    return dict(schema_version=1, observed_at_ms=now // 1_000_000, experiment=experiment.parent.name,
        coin=config['coin'], network=config['network'], gate_status=gate, writer_active=active,
        clock_uncertain=clock_uncertain, started_ms=origin_wall // 1_000_000,
        expected_end_ms=(origin_wall + requested) // 1_000_000,
        elapsed_ms=max(0, elapsed // 1_000_000), requested_ms=requested // 1_000_000,
        progress=min(1, max(0, elapsed / requested)), current_run=current['run'] if current else None,
        validated_runs=len(validated), started_runs=len(runs),
        verified_observations=sum(entry['snapshots'] for entry in validated),
        verified_recording_bytes=sum(entry['recording_bytes'] for entry in validated),
        recording_budget_bytes=config['max_total_recording_bytes'],
        restarts=sum(c['kind'] == 'restart_scheduled' for c in controls),
        network_recovered=any(f['kind'] == 'network_recovery_observed' for f in faults),
        crash_recovered=any(f['kind'] == 'crash_recovery_observed' for f in faults),
        resource=dict(rss_bytes=latest_resource.get('rss_bytes'), open_fds=latest_resource.get('open_fds'),
            run=latest_resource.get('run'), sample_count=len(resources)),
        feeds=feeds, chart=chart, runs=[{k: v for k, v in entry.items() if k not in ('pid', 'elapsed_start_ns')}
                                    for entry in reversed(list(runs.values())[-30:])],
        activity=list(reversed(activity[-12:])), final_audit_verified=passed,
        note='Read-only monitoring of normalized output. Active data is provisional until replay validation.')


def render_html(state, mode='live'):
    if mode not in ('live', 'snapshot'):
        raise ValueError('invalid dashboard mode')
    boot = json.dumps(dict(mode=mode, state=state), separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = TEMPLATE.read_text()
    if template.count('__DASHBOARD_BOOT__') != 1 or template.count('__GIETHOORN_THEME__') != 1:
        raise ValueError('invalid dashboard template')
    return template.replace('__GIETHOORN_THEME__', THEME.read_text()).replace('__DASHBOARD_BOOT__', boot).encode()


class Monitor:
    def __init__(self, experiment):
        self.experiment = Path(experiment).resolve()
        self.lock = threading.Lock()
        self.cached = None
        self.cached_at = 0

    def read(self):
        with self.lock:
            now = time.monotonic()
            if self.cached is None or now - self.cached_at >= 1:
                self.cached = snapshot(self.experiment)
                self.cached_at = now
            return self.cached


def server_for(experiment, host='127.0.0.1', port=3000, paper_view=None, batch_view=None):
    monitor = Monitor(experiment)
    views = {route: Path(view).absolute() for route, view in [('/paper', paper_view), ('/batch', batch_view)] if view}
    for view in views.values():
        plain_file(view)
        if view.stat().st_size > MAX_METADATA:
            raise ValueError('Research view exceeds view limit')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path not in ('/', '/api/state', '/snapshot.html') and path not in views:
                self.send_error(404)
                return
            try:
                if path in views:
                    plain_file(views[path])
                    with views[path].open('rb') as source:
                        body = source.read(MAX_METADATA + 1)
                    if len(body) > MAX_METADATA:
                        raise ValueError('Research view exceeds view limit')
                else:
                    state = dict(monitor.read(), paper_lab_available='/paper' in views, batch_available='/batch' in views)
                    body = json.dumps(state, separators=(',', ':')).encode() if path == '/api/state' else render_html(state, 'snapshot' if path == '/snapshot.html' else 'live')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8' if path == '/api/state' else 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                if path == '/snapshot.html':
                    self.send_header('Content-Disposition', 'attachment; filename="giethoorn-snapshot.html"')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (OSError, ValueError, KeyError, TypeError) as error:
                body = json.dumps({'error': 'Requested read-only evidence is unavailable or inconsistent.',
                                   'error_class': type(error).__name__}).encode()
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def do_POST(self):
            self.send_error(405, 'Read-only monitor')

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--host', choices=('127.0.0.1', '0.0.0.0'), default='127.0.0.1')
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--snapshot', type=Path, help='Write a self-contained HTML snapshot, then exit.')
    parser.add_argument('--paper-view', type=Path, help='Optional offline Paper Lab HTML with declared source provenance.')
    parser.add_argument('--batch-view', type=Path, help='Optional offline sensitivity report HTML.')
    args = parser.parse_args()
    if args.snapshot:
        data = render_html(snapshot(args.experiment), 'snapshot')
        with args.snapshot.open('xb') as output:
            output.write(data)
        print(args.snapshot)
    else:
        server = server_for(args.experiment, args.host, args.port, args.paper_view, args.batch_view)
        print('Giethoorn monitor: http://' + args.host + ':' + str(server.server_port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
