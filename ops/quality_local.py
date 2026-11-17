#!/usr/bin/env python3
"""Audit a stopped archive and describe its recorded data quality offline."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path

if __package__:
    from . import review_local as REVIEW
else:
    import review_local as REVIEW

MIB = 1024 * 1024
MAX_LINE = MIB
MAX_RECORDS = 2_000_000
MAX_SPANS_BYTES = 64 * MIB
STATES = ('disconnected', 'awaiting_acknowledgement', 'awaiting_data', 'fresh', 'empty', 'stale', 'unobserved_deadline')
POLICY = dict(quality_policy_version=1, study_id='btc-bbo-imbalance-001',
              max_bbo_gap_ns=250_000_000, min_candidate_span_ns=1_250_000_000,
              clock_discontinuity_ns=1_000_000_000, finalized_only=True,
              unique_exchange_times_only=True, signal_evaluated=False)
require = REVIEW.require


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read_asset(path):
    REVIEW.plain(path)
    require(path.stat().st_size <= 2*MIB, 'report asset exceeds limit')
    value = path.read_bytes()
    require(len(value) <= 2*MIB, 'report asset grew beyond limit')
    return value


def objects(path):
    REVIEW.plain(path)
    with path.open('rb') as stream:
        count = 0
        while True:
            line = stream.readline(MAX_LINE+1)
            if not line:
                return
            count += 1
            require(count <= MAX_RECORDS and len(line) <= MAX_LINE and line.endswith(b'\n'),
                    'record stream exceeds limits or is incomplete')
            value = json.loads(line)
            require(type(value) is dict, 'record must be an object')
            yield value


def source_records(session):
    for path in sorted(session.glob('segment-*.jsonl')):
        yield from objects(path)


class SpanWriter:
    def __init__(self, stream):
        self.stream, self.bytes = stream, 0

    def write(self, value):
        raw = encoded(value) + b'\n'
        self.bytes += len(raw)
        require(self.bytes <= MAX_SPANS_BYTES, 'cadence span output exceeds limit')
        self.stream.write(raw)


def measure(session, quotes, inspection, child, span_writer):
    """Use native-verified records/observations; never renormalize market prices."""
    feed_report = inspection['session'].get('feeds')
    require(feed_report and feed_report['normalization_version'] == 2, 'schema-2 feeds required')
    enabled = [feed for feed in ('bbo', 'depth') if feed_report.get(feed) is not None]
    durations = {feed: {state: 0 for state in STATES} for feed in enabled}
    states = {feed: dict(status='disconnected') for feed in enabled}
    observed_at = 0
    quote_rows = iter(objects(quotes))
    observation = next(quote_rows, None)
    previous = first = None
    maximum_gap = clock_jumps = wall_backwards = 0
    min_clock_step = max_clock_step = None
    quote_counts = {feed: 0 for feed in enabled}
    usable_bbo = duplicate_times = 0
    latest_exchange = {}
    chain = None
    cadence = dict(span_count=0, candidate_span_count=0, span_ns=0,
                   candidate_span_ns=0, longest_span_ns=0, singleton_observations=0)

    def close_chain():
        nonlocal chain
        if chain is None:
            return
        length = chain['end_ns'] - chain['start_ns']
        if chain['observations'] < 2:
            cadence['singleton_observations'] += 1
        else:
            candidate = length >= POLICY['min_candidate_span_ns']
            cadence['span_count'] += 1
            cadence['span_ns'] += length
            cadence['longest_span_ns'] = max(cadence['longest_span_ns'], length)
            if candidate:
                cadence['candidate_span_count'] += 1
                cadence['candidate_span_ns'] += length
            span_writer.write(dict(child=child, **chain, duration_ns=length, candidate=candidate))
        chain = None

    records = 0
    for record in source_records(session):
        records += 1
        require(records <= MAX_RECORDS and record['schema_version'] == 2 and record['sequence'] == records,
                'source order or schema changed after native audit')
        now = record['monotonic_ns']
        if first is None:
            first = record
        if previous is not None:
            delta = now-previous['monotonic_ns']
            require(delta >= 0, 'source monotonic clock went backwards')
            maximum_gap = max(maximum_gap, delta)
            clock_step = record['local_time_ns']-previous['local_time_ns']-delta
            min_clock_step = clock_step if min_clock_step is None else min(min_clock_step, clock_step)
            max_clock_step = clock_step if max_clock_step is None else max(max_clock_step, clock_step)
            clock_jumps += abs(clock_step) >= POLICY['clock_discontinuity_ns']
            wall_backwards += record['local_time_ns'] < previous['local_time_ns']
            if abs(clock_step) >= POLICY['clock_discontinuity_ns'] or record['local_time_ns'] < previous['local_time_ns']:
                close_chain()
            for feed, state in states.items():
                status = state['status']
                require(status in STATES, 'unsupported recorded feed state')
                if status == 'fresh':
                    deadline = observed_at + state['stale_after_ms']*1_000_000-state['age_ns']
                    fresh = max(0, min(now, deadline)-previous['monotonic_ns'])
                    durations[feed]['fresh'] += fresh
                    durations[feed]['unobserved_deadline'] += delta-fresh
                else:
                    durations[feed][status] += delta
        if observation is not None:
            require(observation['sequence'] >= records, 'unexpected native observation ordering')
        if observation is not None and observation['sequence'] == records:
            require(observation['normalization_version'] == 2
                    and all(observation[key] == record[key] for key in ('monotonic_ns', 'local_time_ns', 'connection_id')),
                    'normalized observation no longer matches original event')
            states = {feed: observation['feeds'][feed] for feed in enabled}
            observed_at = now
            for state in states.values():
                require(state is not None and state['status'] in STATES, 'missing native feed state')
            if states.get('bbo', {}).get('status') != 'fresh':
                close_chain()
            kind = observation['kind']
            if kind in enabled:
                quote_counts[kind] += 1
            if kind == 'bbo':
                state = states['bbo']
                quote = observation.get('quote') or {}
                usable = state['status'] == 'fresh' and state['acknowledged'] and quote.get('mid') is not None
                if not usable:
                    close_chain()
                else:
                    usable_bbo += 1
                    connection = record['connection_id']
                    exchange = quote['exchange_time_ms']
                    old = latest_exchange.get(connection)
                    require(old is None or exchange >= old, 'accepted BBO exchange clock regressed')
                    latest_exchange[connection] = exchange
                    if old == exchange:
                        duplicate_times += 1
                        close_chain()
                    else:
                        if chain is not None and (chain['connection_id'] != connection
                                                  or now-chain['end_ns'] > POLICY['max_bbo_gap_ns']):
                            close_chain()
                        if chain is None:
                            chain = dict(connection_id=connection, start_ns=now, end_ns=now,
                                         first_sequence=records, last_sequence=records, observations=1)
                        else:
                            chain.update(end_ns=now, last_sequence=records, observations=chain['observations']+1)
            observation = next(quote_rows, None)
        previous = record
    close_chain()
    require(first is not None and observation is None and records == inspection['session']['records'],
            'source count or observation tail changed after audit')
    duration = previous['monotonic_ns']-first['monotonic_ns']
    require(duration == inspection['recorded_duration_ns'], 'recorded duration disagrees with native inspection')
    for feed in enabled:
        require(sum(durations[feed].values()) == duration
                and quote_counts[feed] == inspection['feeds'][feed]['snapshots'],
                'feed accounting differs from native inspection')
    return dict(source_records=records, recorded_duration_ns=duration,
                first_local_time_ns=str(first['local_time_ns']), last_local_time_ns=str(previous['local_time_ns']),
                max_record_gap_ns=maximum_gap, wall_clock_discontinuities=clock_jumps,
                backwards_wall_steps=wall_backwards, min_wall_minus_monotonic_step_ns=min_clock_step,
                max_wall_minus_monotonic_step_ns=max_clock_step, feed_state_duration_ns=durations,
                usable_bbo_observations=usable_bbo, equal_exchange_time_bbo_observations=duplicate_times,
                cadence=cadence)


def summarize(runs):
    candidates = [row for row in runs if row['candidate']]
    measured = [row for row in runs if row['measurements'] is not None]
    return dict(recordings=len(runs), finalized=sum(row['finalized'] for row in runs),
                recovered_prefixes=sum(not row['finalized'] for row in runs),
                candidate_recordings=len(candidates),
                retained_snapshots=sum(row['snapshots'] for row in runs),
                usable_bbo_observations=sum(row['measurements']['usable_bbo_observations'] for row in measured),
                candidate_span_count=sum(row['measurements']['cadence']['candidate_span_count'] for row in measured),
                candidate_span_ns=sum(row['measurements']['cadence']['candidate_span_ns'] for row in measured))


def partitions(runs):
    ids = sorted(row['run'] for row in runs if row['candidate'])
    if len(ids) < 5:
        return dict(status='insufficient_children', development=None, validation=None, retrospective_test=None,
                    qualified_children=ids)
    train, validation = len(ids)*3//5, len(ids)//5
    return dict(status='frozen_retrospective', development=ids[:train], validation=ids[train:train+validation],
                retrospective_test=ids[train+validation:], qualified_children=ids)


def render(report, template, theme):
    require(template.count('__QUALITY_BOOT__') == template.count('__GIETHOORN_THEME__') == 1,
            'invalid quality view template')
    boot = encoded(report).decode().replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = template.replace('__GIETHOORN_THEME__', theme).replace('__QUALITY_BOOT__', boot)
    require(len(html.encode()) <= 8*MIB, 'portable quality view exceeds limit')
    return html


def generate(binary, experiment, output, origin, template, theme, protocol, inspected_children=()):
    require(origin in ('captured_public_data', 'synthetic_fixture'), 'explicit source origin required')
    require(all(type(n) is int and 1 <= n <= 999999 for n in inspected_children), 'invalid inspected child')
    experiment, output = experiment.absolute(), output.resolve()
    require(experiment.is_dir() and not experiment.is_symlink(), 'experiment directory required')
    require(not output.is_relative_to(experiment.resolve()), 'quality output must be outside source evidence')
    assets = {name: read_asset(path) for name, path in [('template', template), ('theme', theme), ('protocol', protocol)]}
    root = experiment/'supervision'
    require(root.is_dir() and not root.is_symlink(), 'supervision directory required')
    REVIEW.plain(root/'supervisor.lock')
    with (root/'supervisor.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('supervisor is active; quality requires stopped evidence') from None
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(mode=0o700)
        before = REVIEW.inventory(experiment)
        REVIEW.save(output/'source-before.json', before)
        (output/'research-protocol.md').write_bytes(assets['protocol'])
        REVIEW.save(output/'quality-policy.json', POLICY)
        audit = REVIEW.review(binary, experiment, output/'audit')
        report = dict(quality_report_version=1, status='audit_unverified', origin=origin,
                      created_at_utc=datetime.now(timezone.utc).isoformat(), policy=POLICY,
                      audit=audit, source_unchanged=False, totals=None, runs=[], partitions=None,
                      strategy_evaluated=False, error=audit['audit_diagnostic'])
        if audit['integrity'] == 'verified':
            try:
                native = REVIEW.read_json(output/'audit/audit.stdout.json')
                summary = REVIEW.read_json(root/'summary.json')
                reported = {row['run']: row for row in summary['runs']}
                require(len(native['runs']) <= 4096, 'too many recordings for quality report')
                rows = []
                with (output/'fast-spans.jsonl').open('xb') as stream:
                    writer = SpanWriter(stream)
                    for row in sorted(native['runs'], key=lambda r: r['run']):
                        require(row['directory'] == f"run-{row['run']:06d}", 'noncanonical child path')
                        child = root/row['directory']
                        inspection = REVIEW.read_json(child/'inspection.json')
                        feeds = inspection['session'].get('feeds')
                        metrics = None
                        reason = 'recovered_prefix'
                        if row['finalized']:
                            reason = 'schema_2_bbo_required'
                            if feeds and feeds.get('bbo') is not None:
                                metrics = measure(child/'session', child/'live-quotes.jsonl', inspection, row['run'], writer)
                                reason = 'candidate' if metrics['cadence']['candidate_span_count'] else 'no_qualifying_bbo_span'
                        rows.append(dict(run=row['run'], directory=row['directory'], finalized=row['finalized'],
                                         snapshots=row['snapshots'], recording_bytes=row['recording_bytes'],
                                         comparison=row['comparison'], candidate=reason == 'candidate', reason=reason,
                                         previously_inspected=row['run'] in inspected_children,
                                         process_elapsed_ns=reported[row['run']]['elapsed_ns'],
                                         source_end_reason=inspection['session']['end_reason'],
                                         inspection_status=inspection['status'], native_feeds=inspection.get('feeds'),
                                         ignored_older_updates={feed: feeds[feed].get('stale_snapshots') for feed in ('bbo', 'depth')
                                                                if feeds and feeds.get(feed) is not None},
                                         connection_errors=inspection['connection_errors'],
                                         successful_connections=inspection['successful_connections'], measurements=metrics))
                report.update(status='completed', runs=rows, totals=summarize(rows), partitions=partitions(rows), error=None)
            except (ValueError, OSError, KeyError, TypeError) as error:
                report.update(status='analysis_failed', error=str(error))
        after = REVIEW.inventory(experiment)
        REVIEW.save(output/'source-after.json', after)
        unchanged = before == after and REVIEW.digest(binary.resolve()) == audit['audit_binary_sha256']
        report['source_unchanged'] = unchanged
        if not unchanged:
            report.update(status='source_changed', totals=None, runs=[], partitions=None, error='source or audit executable changed')
        manifest = dict(quality_manifest_version=1, origin=origin, source=str(experiment),
                        source_inventory_sha256=REVIEW.digest(output/'source-before.json'),
                        audit_output_sha256=REVIEW.digest(output/'audit/audit.stdout.json'),
                        audit_binary_sha256=audit['audit_binary_sha256'], policy_sha256=REVIEW.digest(output/'quality-policy.json'),
                        assets={name: hashlib.sha256(raw).hexdigest() for name, raw in assets.items()},
                        quality_helper_sha256=REVIEW.digest(Path(__file__)),
                        review_helper_sha256=REVIEW.digest(Path(REVIEW.__file__)),
                        fast_spans_sha256=REVIEW.digest(output/'fast-spans.jsonl') if (output/'fast-spans.jsonl').exists() else None,
                        inspected_children=sorted(set(inspected_children)),
                        candidate_partitions=report['partitions'],
                        admitted=report['status'] == 'completed' and unchanged
                                 and report['partitions']['status'] == 'frozen_retrospective')
        REVIEW.save(output/'dataset-manifest.json', manifest)
        report['manifest'] = manifest
        raw_report = encoded(report)+b'\n'
        require(len(raw_report) <= 6*MIB, 'quality report exceeds limit')
        with (output/'quality-report.json').open('xb') as stream:
            stream.write(raw_report)
        (output/'quality.html').write_text(render(report, assets['template'].decode(), assets['theme'].decode()))
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('binary', 'experiment', 'output-dir', 'template', 'theme', 'protocol'):
        parser.add_argument('--'+option, type=Path, required=True)
    parser.add_argument('--origin', choices=('captured-public-data', 'synthetic-fixture'), required=True)
    parser.add_argument('--inspected-child', type=int, action='append', default=[])
    args = parser.parse_args()
    try:
        report = generate(args.binary, args.experiment, args.output_dir, args.origin.replace('-', '_'),
                          args.template, args.theme, args.protocol, args.inspected_child)
    except (ValueError, OSError) as error:
        parser.exit(2, 'Quality preflight failed: '+str(error)+'\n')
    brief = {name: report[name] for name in ('status', 'source_unchanged', 'totals', 'error')}
    parts = report['partitions']
    brief['partitions'] = None if parts is None else dict(status=parts['status'], **{
        key+'_count': None if parts[key] is None else len(parts[key])
        for key in ('development', 'validation', 'retrospective_test')})
    last = report['runs'][-1] if report['runs'] else None
    if last is not None:
        metrics = last['measurements'] or {}
        def seconds(value):
            return None if value is None else f'{value//1_000_000_000}.{value%1_000_000_000:09d}'
        brief['last_recording'] = dict(run=last['run'], process_elapsed_seconds=seconds(last['process_elapsed_ns']),
            recorded_span_seconds=seconds(metrics.get('recorded_duration_ns')),
            max_record_gap_seconds=seconds(metrics.get('max_record_gap_ns')),
            wall_clock_discontinuities=metrics.get('wall_clock_discontinuities'))
    print(json.dumps(brief, indent=2))
    print('Quality view: '+str(args.output_dir/'quality.html'))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
