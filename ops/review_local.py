#!/usr/bin/env python3
"""Read-only review of a stopped local experiment; never restart or repair it."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess

MIB = 1024*1024
MAX_METADATA = 16*MIB
MAX_INPUT = 16*1024*MIB
MAX_FILES = 32768
AUDIT_FIELDS = ('integrity', 'supervisor_status', 'full_window_completed', 'coin', 'network',
                'validated_runs', 'started_runs', 'restarts', 'snapshots', 'recording_bytes',
                'peak_sampled_rss_bytes', 'max_sampled_open_fds')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def plain(path):
    require(path.is_file() and not path.is_symlink(), 'regular source file required: '+path.name)


def digest(path):
    plain(path)
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(MIB), b''):
            hasher.update(block)
    return hasher.hexdigest()


def read_json(path):
    plain(path)
    require(path.stat().st_size <= MAX_METADATA, 'metadata exceeds review limit')
    with path.open('rb') as stream:
        raw = stream.read(MAX_METADATA+1)
    require(len(raw) <= MAX_METADATA, 'metadata grew beyond review limit')
    value = json.loads(raw)
    require(type(value) is dict, 'metadata must be an object')
    return value


def save(path, value):
    with path.open('x') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())


def inventory(experiment):
    result = {}
    total = 0
    for path in sorted(experiment.rglob('*')):
        require(not path.is_symlink(), 'source symlink refused')
        if path.is_dir():
            continue
        plain(path)
        info = path.stat()
        total += info.st_size
        require(len(result) < MAX_FILES and total <= MAX_INPUT, 'source exceeds review bounds')
        result[str(path.relative_to(experiment))] = dict(bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                                                       sha256=digest(path))
    # Local wrapper receipts live beside the experiment and contribute to its
    # completion claim. Bind them to the same before/after check as the archive.
    for name in ('local-run.json', 'local-result.json'):
        path = experiment.parent/name
        if not path.exists() and not path.is_symlink():
            continue
        plain(path)
        info = path.stat()
        total += info.st_size
        require(len(result) < MAX_FILES and total <= MAX_INPUT, 'source exceeds review bounds')
        result['../'+name] = dict(bytes=info.st_size, mtime_ns=info.st_mtime_ns, sha256=digest(path))
    return result


def cap_child_output():
    # Each native diagnostic stream is bounded; no source file is writable.
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_METADATA, MAX_METADATA))


def review(binary, experiment, output, timeout_seconds=180):
    binary = binary.resolve()
    experiment = experiment.absolute()
    output = output.resolve()
    require(type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 600, 'invalid native audit timeout')
    require(binary.is_file() and os.access(binary, os.X_OK) and binary.stat().st_size <= 128*MIB,
            'bounded installed audit executable required')
    require(experiment.is_dir() and not experiment.is_symlink(), 'experiment directory required')
    require(not output.is_relative_to(experiment.resolve()), 'review output must be outside original evidence')
    root = experiment/'supervision'
    require(root.is_dir() and not root.is_symlink(), 'supervision directory required')
    plain(root/'supervisor.lock')
    with (root/'supervisor.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('supervisor is still active; review only stopped evidence') from None
        os.umask(0o077)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(mode=0o700)
        before = inventory(experiment)
        save(output/'source-before.json', before)
        binary_sha = digest(binary)
        issues = []
        metadata = {}
        for name, path in [('supervisor', root/'summary.json'), ('experiment', experiment/'experiment.json'),
                           ('local_result', experiment.parent/'local-result.json')]:
            try:
                metadata[name] = read_json(path)
            except (OSError, ValueError) as error:
                metadata[name] = None
                issues.append(dict(artifact=name, error_class=type(error).__name__))
        command = [str(binary), 'audit-supervision', '--input', str(root)]
        exit_code = None
        timed_out = False
        audit = None
        with (output/'audit.stdout.json').open('xb') as stdout, (output/'audit.stderr').open('xb') as stderr:
            try:
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        timeout=timeout_seconds, check=False, preexec_fn=cap_child_output)
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
            except OSError as error:
                issues.append(dict(artifact='native_audit', error_class=type(error).__name__))
        with (output/'audit.stderr').open('rb') as stderr:
            diagnostic = stderr.read(2048).decode('utf-8', errors='replace').strip() or None
        if exit_code == 0:
            try:
                audit = read_json(output/'audit.stdout.json')
                require(type(audit.get('schema_version')) is int and audit['schema_version'] == 1
                        and audit.get('integrity') == 'verified'
                        and type(audit.get('full_window_completed')) is bool
                        and all(key in audit for key in AUDIT_FIELDS)
                        and type(audit.get('runs')) is list
                        and len(audit['runs']) == audit['validated_runs']
                        and all(type(row) is dict and type(row.get('finalized')) is bool for row in audit['runs']),
                        'unsupported audit envelope')
            except (ValueError, OSError):
                audit = None
                issues.append(dict(artifact='native_audit', error_class='InvalidAuditEnvelope'))
        after = inventory(experiment)
        save(output/'source-after.json', after)
        unchanged = before == after and digest(binary) == binary_sha
        supervisor = metadata['supervisor'] or {}
        experiment_report = metadata['experiment'] or {}
        local_result = metadata['local_result'] or {}
        verified = audit is not None and unchanged
        verified_day = bool(verified and supervisor.get('requested_duration_secs') == 86400
                            and audit['full_window_completed']
                            and experiment_report.get('status') == 'completed'
                            and experiment_report.get('network_recovery_observed') is True
                            and experiment_report.get('crash_recovery_observed') is True
                            and local_result.get('status') == 'completed'
                            and local_result.get('experiment_exit_code') == 0
                            and local_result.get('verified_24_hour_window') is True)
        elapsed = supervisor.get('elapsed_ns')
        seconds = elapsed//1_000_000_000 if type(elapsed) is int and elapsed >= 0 else None
        reported_runs = supervisor.get('runs')
        last_run = reported_runs[-1] if type(reported_runs) is list and reported_runs and type(reported_runs[-1]) is dict else None
        last_reported_run = None
        if last_run is not None:
            last_reported_run = {key: last_run.get(key) for key in ['run', 'exit_code', 'signal', 'finalized', 'comparison', 'snapshots']}
            run_elapsed = last_run.get('elapsed_ns')
            last_reported_run['elapsed_seconds'] = run_elapsed//1_000_000_000 if type(run_elapsed) is int else None
        audit_summary = {key: audit.get(key) for key in AUDIT_FIELDS} if verified else None
        if audit_summary is not None:
            audit_summary['finalized_recordings'] = sum(row['finalized'] for row in audit['runs'])
            audit_summary['recovered_prefixes'] = sum(not row['finalized'] for row in audit['runs'])
        report = dict(review_version=1, status='reviewed' if verified else 'audit_unverified',
            reviewed_at_utc=datetime.now(timezone.utc).isoformat(), source=str(experiment),
            source_files=len(before), source_unchanged=unchanged, audit_binary_sha256=binary_sha,
            audit_command=command, audit_exit_code=exit_code, audit_timed_out=timed_out,
            audit_diagnostic=diagnostic,
            native_audit_timeout_seconds=timeout_seconds, integrity='verified' if verified else 'unverified',
            reported_supervisor_status=supervisor.get('status'), reported_reason=supervisor.get('reason'),
            reported_elapsed_seconds=seconds, requested_duration_secs=supervisor.get('requested_duration_secs'),
            reported_elapsed=None if seconds is None else f'{seconds//3600}h {seconds%3600//60}m {seconds%60}s',
            last_reported_run=last_reported_run,
            reported_experiment_status=experiment_report.get('status'),
            network_recovery_observed=experiment_report.get('network_recovery_observed'),
            crash_recovery_observed=experiment_report.get('crash_recovery_observed'),
            audit=audit_summary,
            verified_24_hour_window=verified_day, metadata_issues=issues,
            interpretation='Integrity verifies retained evidence, independently of operating success. '
                'A refused audit needs separate per-recording recovery; no archive is repaired or resumed.')
        save(output/'review.json', report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=float, default=180)
    args = parser.parse_args()
    try:
        result = review(args.binary, args.experiment, args.output_dir, args.timeout_seconds)
    except (ValueError, OSError) as error:
        parser.exit(2, 'Review preflight failed: '+str(error)+'\n')
    print(json.dumps({key: result[key] for key in ['status', 'integrity', 'source_unchanged',
        'reported_supervisor_status', 'reported_reason', 'reported_elapsed',
        'last_reported_run', 'audit', 'verified_24_hour_window', 'audit_exit_code', 'audit_timed_out',
        'audit_diagnostic', 'metadata_issues']}, indent=2))
    print('Review evidence: '+str(args.output_dir/'review.json'))
    return 0 if result['status'] == 'reviewed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
