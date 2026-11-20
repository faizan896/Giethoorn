#!/usr/bin/env python3
"""Replicate the fixed causal paper cycle across a frozen development cohort."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

if __package__:
    from . import evaluation_core as CORE, proxy_policy_local as CYCLE
else:
    import evaluation_core as CORE
    import proxy_policy_local as CYCLE

ORIGINAL = CYCLE.ORIGINAL
COST, QUALITY, REVIEW = ORIGINAL.COST, CYCLE.QUALITY, CYCLE.REVIEW
STUDY = COST.STUDY
require = REVIEW.require
MIB = 1024 * 1024
LIMITS = dict(output_bytes=16*1024*MIB, free_reserve_bytes=1024*MIB, report_reserve_bytes=16*MIB,
    source_allowance_bytes=128*MIB, case_allowance_bytes=256*MIB, suite_seconds=3600,
    native_seconds=30, max_children=128, max_cases=768)
ERRORS = (ValueError, OSError, KeyError, TypeError, IndexError, subprocess.TimeoutExpired)


def admit(root, deadline, allowance):
    require(time.monotonic() < deadline, 'evaluation time budget exhausted')
    reserve = allowance + LIMITS['report_reserve_bytes']
    require(COST.used_bytes(root) + reserve <= LIMITS['output_bytes'], 'evaluation output admission exhausted')
    require(shutil.disk_usage(root).free >= LIMITS['free_reserve_bytes'] + reserve, 'evaluation free-space reserve insufficient')


def code_files(quality_template, cost_template, template, theme, protocol):
    files = CYCLE.code_files(quality_template, cost_template, template, theme)
    files.pop('policy_template')
    return dict(files, evaluation_core=Path(CORE.__file__), evaluation_local=Path(__file__),
        evaluation_template=template, evaluation_protocol=protocol)


def fresh_quality(binary, experiment, output, frozen, manifest, expected_source, deadline):
    """Fresh native audit, then unchanged quality measurements and membership."""
    output.mkdir()
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'evaluation time budget exhausted')
    audit = REVIEW.review(binary, experiment, output/'audit',
        timeout_seconds=min(LIMITS['native_seconds'], remaining))
    require(audit['integrity'] == 'verified' and audit['source_unchanged'], 'fresh native archive audit unverified')
    require(REVIEW.digest(output/'audit/audit.stdout.json') == manifest['audit_output_sha256']
        and REVIEW.read_json(output/'audit/source-before.json') == expected_source,
        'fresh native archive differs from frozen quality evidence')
    native = REVIEW.read_json(output/'audit/audit.stdout.json')
    expected = {row['run']: row for row in frozen['runs']}
    require(len(native['runs']) == len(expected), 'fresh quality membership differs')
    rows = []
    with (output/'fast-spans.jsonl').open('xb') as stream:
        writer = QUALITY.SpanWriter(stream)
        for row in sorted(native['runs'], key=lambda value: value['run']):
            require(time.monotonic() < deadline, 'quality measurement time budget exhausted')
            child, measurement, reason = experiment/'supervision'/row['directory'], None, 'recovered_prefix'
            require(row['directory'] == f'run-{row["run"]:06d}', 'noncanonical fresh source path')
            inspection = REVIEW.read_json(child/'inspection.json')
            feeds = inspection['session'].get('feeds')
            if row['finalized']:
                reason = 'schema_2_bbo_required'
                if feeds and feeds.get('bbo') is not None:
                    measurement = QUALITY.measure(child/'session', child/'live-quotes.jsonl', inspection, row['run'], writer)
                    reason = 'candidate' if measurement['cadence']['candidate_span_count'] else 'no_qualifying_bbo_span'
            old = expected[row['run']]
            require(old['finalized'] == row['finalized'] and old['measurements'] == measurement
                and old['reason'] == reason and old['candidate'] == (reason == 'candidate'),
                'fresh quality measurements or candidate membership differ')
            rows.append(dict(run=row['run'], candidate=reason == 'candidate', reason=reason))
    require(QUALITY.partitions(rows) == manifest['candidate_partitions']
        and REVIEW.digest(output/'fast-spans.jsonl') == manifest['fast_spans_sha256'],
        'fresh partitions or spans differ from frozen quality')
    REVIEW.save(output/'checked-membership.json', dict(partitions=QUALITY.partitions(rows), rows=rows))
    return audit


def load_market(binary, source, output, child, expected_source, origin, deadline):
    output.mkdir()
    ORIGINAL.native(binary, ['paper-market-replay', '--input', str(source), '--output-dir', str(output/'market'),
        '--origin', origin.replace('_', '-'), '--feed', 'bbo'], output/'market.stdout.json', output/'market.stderr', deadline)
    report = ORIGINAL.obj(output/'market/market-replay.json')
    require(report == ORIGINAL.obj(output/'market.stdout.json'), 'native market report differs')
    COST.match_source(dict(market=report), expected_source, child)
    require(report['paper']['config']['coin'] == CORE.CYCLE.FROZEN.SIGNAL.POLICY['coin']
        and report['paper']['config']['source']['network'] == CORE.CYCLE.FROZEN.SIGNAL.POLICY['network'],
        'evaluation requires the declared BTC mainnet domain')
    original = list(QUALITY.source_records(output/'market/source'))
    require(len(original) < 10000 and len(original) == report['source_report']['records'], 'bounded source count differs')
    frames, links = ORIGINAL.lines(output/'market/paper-updates.jsonl'), ORIGINAL.lines(output/'market/market-links.jsonl')
    events = ORIGINAL.CORE.market_events(original, frames, links)
    ORIGINAL.native(binary, ['replay', '--input', str(output/'market/source')],
        output/'normalized.jsonl', output/'normalized-report.json', deadline)
    require(ORIGINAL.obj(output/'normalized-report.json') == report['source_report'], 'fresh normalization differs')
    feature = ORIGINAL.selected_feature(child, original, ORIGINAL.lines(output/'normalized.jsonl'))
    return dict(directory=output/'market', report=report, frames=frames, links=links, events=events, feature=feature)


def compact(policy):
    return {key: policy[key] for key in ('policy_id', 'metrics', 'causal_prefix_audit', 'causal_prefix_verified', 'control_reused')} | dict(
        close_compilation={key: policy['close_compilation'][key] for key in
            ('status', 'known_position', 'working_orders', 'prefix_records', 'prefix_sha256')},
        orders=[dict(id=o['order']['id'], side=o['order']['side'], requested_quantity=o['order']['quantity'],
            filled_quantity=o['native_final_order']['filled_quantity'], outcome=o['outcome'],
            assumed_fill_price=o.get('assumed_fill_price'), assumed_fee=o.get('assumed_fee'),
            reference_age_ns=o.get('reference_age_ns')) for o in policy['orders']])


def progress(row, cases):
    print(json.dumps(dict(child=row['child'], status=row['status'],
        verified=sum(case['status'] == 'verified' for case in cases))), flush=True)


def generate(binary, experiment, quality, output, origin, quality_template, cost_template, template, theme, protocol):
    binary, experiment, quality, output = binary.resolve(), experiment.absolute(), quality.absolute(), output.resolve()
    require(binary.is_file() and os.access(binary, os.X_OK) and binary.stat().st_size <= 128*MIB,
        'bounded installed executable required')
    require(origin in ('captured_public_data', 'synthetic_fixture'), 'explicit source origin required')
    require(not output.exists() and not output.is_relative_to(experiment.resolve()) and not output.is_relative_to(quality.resolve()),
        'evaluation output must be new and outside original evidence')
    assets = dict(template=QUALITY.read_asset(template), theme=QUALITY.read_asset(theme), protocol=QUALITY.read_asset(protocol))
    require(REVIEW.digest(protocol) == CORE.PROTOCOL_SHA256, 'frozen evaluation protocol differs')
    root = experiment/'supervision'
    REVIEW.plain(root/'supervisor.lock')
    with (root/'supervisor.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('supervisor is active; evaluation requires stopped evidence') from None
        hashes, manifest, frozen, before = STUDY.frozen(quality, binary, origin, quality_template, theme)
        selected = CORE.cohort(manifest)
        require(REVIEW.inventory(experiment) == before, 'source differs from frozen quality dataset')
        files = code_files(quality_template, cost_template, template, theme, protocol)
        code = {key: REVIEW.digest(path) for key, path in files.items()}
        binary_sha = REVIEW.digest(binary)
        os.umask(0o077)
        output.parent.mkdir(parents=True, exist_ok=True)
        require(shutil.disk_usage(output.parent).free >= LIMITS['free_reserve_bytes']+LIMITS['case_allowance_bytes'],
            'evaluation initial free-space reserve insufficient')
        output.mkdir(mode=0o700)
        for directory in ('input-quality', 'markets', 'cases'):
            (output/directory).mkdir()
        deadline = time.monotonic()+LIMITS['suite_seconds']
        for name in STUDY.INPUTS:
            target = output/'input-quality'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(quality/name, target)
            require(REVIEW.digest(target) == hashes[name], 'quality changed during snapshot')
        pinned = output/'replay.bin'
        shutil.copyfile(binary, pinned)
        pinned.chmod(0o700)
        require(REVIEW.digest(pinned) == binary_sha, 'installed executable changed during pinning')
        (output/'evaluation-protocol.md').write_bytes(assets['protocol'])
        REVIEW.save(output/'evaluation-policy.json', dict(policy=CORE.POLICY, limits=LIMITS, profiles=CORE.PROFILES,
            cycle_policy=CORE.CYCLE.POLICY, original_cost_policy=CORE.CYCLE.FROZEN.POLICY, protocol_sha256=CORE.PROTOCOL_SHA256))
        cases = [dict(case_id=f'run-{child:06d}--{profile["id"]}', child=child, profile=profile['id'],
            previously_cost_probed=child in selected[:4], status='not_run', reason='Not admitted.', policy=None)
            for child in selected for profile in CORE.PROFILES]
        rows = [dict(child=row['run'], selected=row['run'] in selected, previously_cost_probed=row['run'] in selected[:4],
            status='not_run', reason='Not admitted.' if row['run'] in selected else 'Outside fixed development cohort.', feature=None)
            for row in frozen['runs']]
        report = dict(development_evaluation_version=1, evaluation_id=CORE.POLICY['evaluation_id'],
            created_at_utc=datetime.now(timezone.utc).isoformat(), status='incomplete', origin=origin,
            selected_children=selected, previously_cost_probed_children=selected[:4], policy=CORE.POLICY, limits=LIMITS,
            rows=rows, cases=cases, totals=None, audit=None, error=None, source_unchanged=False,
            quality_unchanged=False, code_unchanged=False, actual_execution_known=False,
            portfolio_profit_evaluated=False, live_orders_enabled=False, full_window_verified=False, exploratory=True)
        try:
            admit(output, deadline, LIMITS['source_allowance_bytes'])
            report['audit'] = fresh_quality(pinned, experiment, output/'quality-check', frozen, manifest, before, deadline)
            for row in rows:
                if not row['selected']:
                    continue
                child_cases = [case for case in cases if case['child'] == row['child']]
                try:
                    admit(output, deadline, LIMITS['source_allowance_bytes'])
                except (ValueError, OSError) as error:
                    row['reason'] = str(error)
                    for case in child_cases: case['reason'] = str(error)
                    progress(row, child_cases)
                    continue
                try:
                    market = load_market(pinned, root/f'run-{row["child"]:06d}/session',
                        output/'markets'/f'run-{row["child"]:06d}', row['child'], before, origin, deadline)
                    require(COST.used_bytes(output/'markets'/f'run-{row["child"]:06d}') <= LIMITS['source_allowance_bytes'],
                        'source exceeded reserved output bound')
                    row['feature'] = market['feature']
                    if market['feature'] is None:
                        row.update(status='no_signal', reason='No directional feature after the fixed warmup.')
                        for case in child_cases: case.update(status='no_signal', reason=row['reason'])
                        progress(row, child_cases)
                        continue
                    REVIEW.save(output/'markets'/f'run-{row["child"]:06d}'/'selected-feature.json', market['feature'])
                except ERRORS as error:
                    row.update(status='unavailable', reason=str(error)[:1200])
                    for case in child_cases: case.update(status='unavailable', reason=row['reason'])
                    progress(row, child_cases)
                    continue
                for case, profile in zip(child_cases, CORE.PROFILES):
                    try:
                        admit(output, deadline, LIMITS['case_allowance_bytes'])
                    except (ValueError, OSError) as error:
                        case['reason'] = str(error)
                        continue
                    folder = output/'cases'/case['case_id']
                    folder.mkdir()
                    try:
                        entry = CORE.CYCLE.FROZEN.entry_scenario(market['feature'], profile['assumptions'])
                        policy = CYCLE.run_case(pinned, market, entry, market['feature'], folder/'policy', deadline, folder)
                        require(COST.used_bytes(folder) <= LIMITS['case_allowance_bytes'], 'case exceeded reserved output bound')
                        case.update(status='verified', reason=None, policy=compact(policy))
                        REVIEW.save(folder/'case-result.json', case)
                    except ERRORS as error:
                        case.update(status='unavailable', reason=str(error)[:1200], policy=None)
                row.update(status='completed' if all(c['status'] == 'verified' for c in child_cases) else 'incomplete', reason=None)
                progress(row, child_cases)
        except ERRORS as error:
            report['error'] = str(error)[:1200]
        try:
            after = REVIEW.inventory(experiment)
            REVIEW.save(output/'source-after.json', after)
            report['source_unchanged'] = before == after
            report['quality_unchanged'] = STUDY.quality_inputs(quality) == hashes
            report['code_unchanged'] = code == {key: REVIEW.digest(path) for key, path in files.items()} \
                and binary_sha == REVIEW.digest(binary) == REVIEW.digest(pinned)
        except ERRORS as error:
            report['error'] = str(error)[:1200]
        if not all(report[key] for key in ('source_unchanged', 'quality_unchanged', 'code_unchanged')):
            report.update(status='source_changed', error='Source, quality, installed executable or evaluation producer changed.')
            for case in cases: case.update(status='unavailable', reason='Changed evidence; metrics not admitted.', policy=None)
        elif report['audit'] is not None and all(case['status'] in ('verified', 'no_signal') for case in cases):
            report['status'] = 'completed'
        report['totals'] = CORE.summarize(cases)
        inventory = {p.relative_to(output).as_posix(): REVIEW.digest(p)
            for p in sorted(output.rglob('*')) if p.is_file()}
        REVIEW.save(output/'audit-inventory.json', dict(audit_inventory_version=1, files=inventory))
        report['provenance'] = dict(source_inventory_sha256=manifest['source_inventory_sha256'],
            input_quality_hashes=hashes, installed_binary_sha256=binary_sha, code_hashes=code,
            protocol_sha256=CORE.PROTOCOL_SHA256,
            audit_inventory=dict(file='audit-inventory.json', files=len(inventory),
                sha256=REVIEW.digest(output/'audit-inventory.json')))
        require(COST.used_bytes(output) <= LIMITS['output_bytes']-LIMITS['report_reserve_bytes'], 'evaluation exceeded report reserve')
        require(len(QUALITY.encoded(report)) <= 4*MIB, 'evaluation report exceeds bound')
        REVIEW.save(output/'evaluation-report.json', report)
        with (output/'evaluation.html').open('x') as stream:
            stream.write(QUALITY.render(report, assets['template'].decode(), assets['theme'].decode()))
        return report


def readout(report):
    result = {key: report[key] for key in ('status', 'evaluation_id', 'source_unchanged', 'quality_unchanged',
        'code_unchanged', 'selected_children', 'totals', 'error')}
    result.update(actual_execution='unknown', exploratory=True, baseline_cases=[], nonverified_cases=[])
    for row in report['cases']:
        if row['status'] not in ('verified', 'no_signal'):
            result['nonverified_cases'].append(dict(case=row['case_id'], status=row['status'], reason=row['reason']))
        if row['profile'] != 'baseline': continue
        m = None if row['policy'] is None else row['policy']['metrics']
        result['baseline_cases'].append(dict(case=row['case_id'], status=row['status'],
            outcome=None if m is None else m['outcome'], conditional_closed_pnl=None if m is None else m['conditional_closed_pnl'],
            fees=None if m is None else m['fees'], ending_position=None if m is None else m['ending_position_quantity'],
            pending_orders=None if m is None else m['pending_order_ids']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('binary', 'experiment', 'quality', 'output-dir', 'quality-template', 'cost-template', 'template', 'theme', 'protocol'):
        parser.add_argument('--'+option, type=Path, required=True)
    parser.add_argument('--origin', choices=('captured-public-data', 'synthetic-fixture'), required=True)
    args = parser.parse_args()
    try:
        report = generate(args.binary, args.experiment, args.quality, args.output_dir, args.origin.replace('-', '_'),
            args.quality_template, args.cost_template, args.template, args.theme, args.protocol)
    except ERRORS as error:
        parser.exit(2, 'Evaluation refused: '+str(error)+'\n')
    print(json.dumps(readout(report), indent=2))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__': raise SystemExit(main())
