#!/usr/bin/env python3
"""Bounded, offline sensitivity matrix for fixed recorded IOC scenarios."""
import argparse
import copy
from decimal import Decimal, localcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

PROJECT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('batch_execution', PROJECT/'ops/paper_execution.py')
EXECUTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXECUTION)
MIB = 1024 * 1024
REPORT_RESERVE = 4 * MIB
SOURCE_ALLOWANCE = 64 * MIB
CASE_ALLOWANCE = 128 * MIB
IDENTIFIER = re.compile(r'[a-z0-9][a-z0-9_-]{0,31}\Z')
DECIMAL = re.compile(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z')
ASSUMPTIONS = {'fee_rate', 'slippage_bps', 'top_size_fraction', 'latency_ms', 'quote_wait_ms'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_keys(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), 'invalid '+label+' fields')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, limit=MIB):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            'invalid or oversized file: '+str(path.name))
    with path.open('rb') as source:
        raw = source.read(limit+1)
    require(len(raw) <= limit, 'file grew beyond limit')
    return raw


def parse_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key: '+key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: require(False, 'nonfinite JSON number'))


def write_json(path, value):
    with path.open('xb') as destination:
        destination.write(json.dumps(value, indent=2, ensure_ascii=False).encode()+b'\n')
        destination.flush()
        os.fsync(destination.fileno())


def validate_assumptions(value):
    exact_keys(value, ASSUMPTIONS, 'assumption')
    for key, minimum, maximum in [('fee_rate', '0', '0.01'), ('slippage_bps', '0', '1000'),
                                  ('top_size_fraction', '0', '1')]:
        text = value[key]
        require(type(text) is str and len(text) <= 60 and DECIMAL.fullmatch(text),
                key+' must be a plain positive decimal string')
        number = Decimal(text)
        require(Decimal(minimum) <= number <= Decimal(maximum)
                and (key != 'top_size_fraction' or number > 0), key+' out of range')
    for key, minimum in [('latency_ms', 0), ('quote_wait_ms', 1)]:
        require(type(value[key]) is int and minimum <= value[key] <= 60000, key+' out of range')


def load_manifest(path):
    raw = read(path)
    manifest = parse_json(raw)
    exact_keys(manifest, ('batch_version', 'label', 'baseline_profile', 'datasets', 'profiles', 'limits'), 'manifest')
    require(type(manifest['batch_version']) is int and manifest['batch_version'] == 1, 'unsupported batch version')
    require(type(manifest['label']) is str and 1 <= len(manifest['label']) <= 160, 'invalid batch label')
    for group in ['datasets', 'profiles']:
        values = manifest[group]
        require(type(values) is list and 1 <= len(values) <= 8, group+' must contain 1..8 entries')
        seen = set()
        for value in values:
            exact_keys(value, ('id', 'label', 'recording', 'scenario', 'origin', 'feed') if group == 'datasets'
                       else ('id', 'label', 'assumptions'), group)
            require(type(value['id']) is str and IDENTIFIER.fullmatch(value['id']) and '--' not in value['id'] and value['id'] not in seen,
                    'invalid or duplicate '+group+' id')
            seen.add(value['id'])
            require(type(value['label']) is str and 1 <= len(value['label']) <= 100, 'invalid entry label')
            if group == 'profiles':
                validate_assumptions(value['assumptions'])
            else:
                require(value['origin'] in ('captured_public_data', 'synthetic_fixture')
                        and value['feed'] in ('bbo', 'depth'), 'explicit source origin/feed required')
                for key in ['recording', 'scenario']:
                    require(type(value[key]) is str and 1 <= len(value[key]) <= 4096, 'invalid input path')
    require(len(manifest['datasets'])*len(manifest['profiles']) <= 32, 'batch exceeds 32 cases')
    require(type(manifest['baseline_profile']) is str and manifest['baseline_profile'] in [p['id'] for p in manifest['profiles']], 'baseline profile missing')
    limits = manifest['limits']
    exact_keys(limits, ('max_output_bytes', 'min_free_bytes', 'native_timeout_seconds', 'suite_timeout_seconds'), 'limit')
    for key, low, high in [('max_output_bytes', 256*MIB, 2048*MIB), ('min_free_bytes', 1024*MIB, 1024**4),
                            ('native_timeout_seconds', 1, 600), ('suite_timeout_seconds', 1, 3600)]:
        require(type(limits[key]) is int and low <= limits[key] <= high, key+' out of range')
    return raw, manifest


def decimal_text(value):
    text = format(value, 'f')
    return '0' if value == 0 else text.rstrip('0').rstrip('.') if '.' in text else text


def fixed_plan(plan):
    return {key: value for key, value in plan.items() if key != 'assumptions'}


def summarize(case_root, expected_source, expected_scenario):
    report = parse_json(read(case_root/'replay/execution-replay.json', 4*MIB))
    audit = parse_json(read(case_root/'cost-audit.json'))
    run = parse_json(read(case_root/'run.json'))
    paper = report['paper']
    require(audit['status'] == 'verified' and paper['complete']
            and report['scenario_sha256'] == expected_scenario
            and paper['config']['source']['recording_sha256'] == expected_source
            and run['recording_sha256'] == expected_source, 'case evidence does not match frozen inputs')
    frames = [parse_json(line) for line in read(case_root/'replay/paper-updates.jsonl', 32*MIB).splitlines()]
    trace = [parse_json(line) for line in read(case_root/'replay/execution-trace.jsonl', 32*MIB).splitlines()]
    require(len(frames) == len(trace) == paper['records'], 'case trace count differs')
    path = dict(fills=[dict(order_id=f['assumed_fill']['order_id'], side=f['assumed_fill']['side'],
                           quantity=f['assumed_fill']['quantity'], market_sequence=t['market_sequence'])
                       for f, t in zip(frames, trace) if f['assumed_fill']],
                orders=[{k: order[k] for k in ['id', 'status', 'filled_quantity', 'remaining_quantity']}
                        for order in paper['orders']], pending=report['pending_order_ids'])
    account = paper['account']
    metrics = {key: account[key] for key in ['realized_pnl', 'unrealized_pnl', 'net_pnl', 'equity', 'position_quantity']}
    metrics.update({key: report[key] for key in ['fees', 'spread_cost', 'slippage_cost', 'pending_order_ids']})
    metrics.update(coin=paper['config']['coin'], quote_currency=paper['config']['quote_currency'],
                   requests=len(report['scenario']['orders']), fills=paper['assumed_fills'],
                   partial_fills=sum(f['assumed_fill'] is not None and f['order']['status'] == 'partially_filled' for f in frames),
                   cancelled_orders=sum(o['status'] == 'cancelled' for o in paper['orders']),
                   rejected_orders=sum(o['status'] == 'rejected' for o in paper['orders']),
                   pending_orders=len(report['pending_order_ids']),
                   valuation='flat_account' if Decimal(account['position_quantity']) == 0 else 'open_inventory_historical_mark',
                   source_end_reason=report['market']['source_report']['end_reason'],
                   execution_path_sha256=digest(canonical(path)))
    return metrics


def comparisons(cases, baseline):
    results = []
    for case in cases:
        base = next(c for c in cases if c['dataset_id'] == case['dataset_id'] and c['profile_id'] == baseline)
        pair = dict(case_id=case['id'], baseline_case_id=base['id'], deltas=None,
                    execution_path_changed=None, ending_inventory_changed=None, pending_changed=None)
        if base['status'] != 'verified' or case['status'] != 'verified':
            pair['unavailable_reason'] = 'Both case and baseline must verify.'
        else:
            a, b = base['metrics'], case['metrics']
            with localcontext() as context:
                context.prec = 100
                pair['deltas'] = {key: None if a[key] is None or b[key] is None
                                 else decimal_text(Decimal(b[key])-Decimal(a[key]))
                                 for key in ['net_pnl', 'fees', 'spread_cost', 'slippage_cost']}
            pair.update(execution_path_changed=a['execution_path_sha256'] != b['execution_path_sha256'],
                        ending_inventory_changed=Decimal(a['position_quantity']) != Decimal(b['position_quantity']),
                        pending_changed=sorted(a['pending_order_ids']) != sorted(b['pending_order_ids']))
        results.append(pair)
    return results


def used_bytes(root):
    total = 0
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'unexpected output symlink')
        if path.is_file():
            total += path.stat().st_size
    return total


def admission(root, limits, deadline, allowance):
    if time.monotonic() >= deadline:
        return 'Suite time budget exhausted.'
    if used_bytes(root)+allowance+REPORT_RESERVE > limits['max_output_bytes']:
        return 'Output budget cannot admit the next bounded operation.'
    if shutil.disk_usage(root).free < limits['min_free_bytes']+allowance+REPORT_RESERVE:
        return 'Free-space reserve cannot admit the next bounded operation.'
    return None


def native_timeout(limits, deadline, calls=1):
    remaining = (deadline-time.monotonic())/calls
    require(remaining > 0, 'suite deadline reached')
    return min(limits['native_timeout_seconds'], remaining)


def render_report(report):
    template = (PROJECT/'web/batch.html').read_text()
    require(template.count('__BATCH_BOOT__') == template.count('__GIETHOORN_THEME__') == 1, 'invalid batch template')
    boot = canonical(report).decode().replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = template.replace('__GIETHOORN_THEME__', (PROJECT/'web/theme.css').read_text()).replace('__BATCH_BOOT__', boot)
    require(len(html.encode()) <= 2*MIB, 'batch view exceeds report reserve')
    return html


def generate(binary, manifest_path, output):
    manifest_path = manifest_path.absolute()
    raw, manifest = load_manifest(manifest_path)
    binary = binary.resolve()
    require(binary.is_file() and os.access(binary, os.X_OK) and binary.stat().st_size <= 128*MIB,
            'bounded executable required')
    output = output.resolve()
    for dataset in manifest['datasets']:
        source = (manifest_path.parent/dataset['recording']).resolve()
        require(not output.is_relative_to(source), 'output must be outside every source')
    output.parent.mkdir(parents=True, exist_ok=True)
    require(shutil.disk_usage(output.parent).free >= manifest['limits']['min_free_bytes']+binary.stat().st_size+REPORT_RESERVE,
            'insufficient initial free-space reserve')
    output.mkdir(mode=0o700)
    started = time.monotonic()
    deadline = started+manifest['limits']['suite_timeout_seconds']
    pinned = output/'replay.bin'
    shutil.copyfile(binary, pinned)
    pinned.chmod(0o700)
    binary_sha = digest(read(pinned, 128*MIB))
    require(binary_sha == digest(read(binary, 128*MIB)), 'binary changed while pinning')
    (output/'manifest.json').write_bytes(raw)
    for name in ['datasets', 'scenarios', 'cases']:
        (output/name).mkdir()
    cases = [dict(id=d['id']+'--'+p['id'], dataset_id=d['id'], profile_id=p['id'], status='not_run',
                  reason='Not admitted.', metrics=None) for d in manifest['datasets'] for p in manifest['profiles']]
    snapshots = []
    for dataset in manifest['datasets']:
        rows = [c for c in cases if c['dataset_id'] == dataset['id']]
        snapshot = dict(dataset_id=dataset['id'], status='not_run')
        snapshots.append(snapshot)
        reason = admission(output, manifest['limits'], deadline, SOURCE_ALLOWANCE)
        if reason:
            snapshot['reason'] = reason
            for row in rows:
                row['reason'] = reason
            continue
        root = output/'datasets'/dataset['id']
        root.mkdir()
        try:
            plan_raw = read(manifest_path.parent/dataset['scenario'], 64*1024)
            plan = parse_json(plan_raw)
            require(type(plan) is dict and 'assumptions' in plan, 'invalid base scenario')
            validate_assumptions(plan['assumptions'])
            (root/'base-scenario.json').write_bytes(plan_raw)
            command = [str(pinned), 'paper-market-replay', '--input', str((manifest_path.parent/dataset['recording']).resolve()),
                       '--output-dir', str(root/'market'), '--origin', dataset['origin'].replace('_', '-'), '--feed', dataset['feed']]
            with (root/'snapshot.stdout').open('xb') as stdout, (root/'snapshot.stderr').open('xb') as stderr:
                result = subprocess.run(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                        timeout=native_timeout(manifest['limits'], deadline), check=False)
            require(result.returncode == 0, 'source snapshot failed; diagnostics retained')
            source_manifest = parse_json(read(root/'market/source-manifest.json'))
            market = parse_json(read(root/'market/market-replay.json', 4*MIB))
            require(source_manifest['origin'] == dataset['origin'] and market['source_report']['complete']
                    and market['source_storage']['finalized'], 'source snapshot is not finalized')
            source_sha = source_manifest['recording_sha256']
            require(source_sha == market['source']['recording_sha256'], 'snapshot fingerprint differs')
            for entry in source_manifest['files']:
                require(Path(entry['file']).name == entry['file'], 'unsafe snapshot file')
                data = read(root/'market/source'/entry['file'], 16*MIB)
                require(digest(data) == entry['sha256'] and len(data) == entry['bytes'], 'snapshot file differs')
            snapshot.update(status='verified', recording_sha256=source_sha, base_scenario_sha256=digest(plan_raw),
                            fixed_plan_sha256=digest(canonical(fixed_plan(plan))),
                            source_records=market['source_report']['records'],
                            source_end_reason=market['source_report']['end_reason'])
        except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
            snapshot.update(status='failed', reason=type(error).__name__+': '+str(error)[:400])
            for row in rows:
                row.update(status='failed', reason='Dataset preparation failed: '+snapshot['reason'])
            continue
        for row, profile in zip(rows, manifest['profiles']):
            reason = admission(output, manifest['limits'], deadline, CASE_ALLOWANCE)
            if reason:
                row['reason'] = reason
                continue
            try:
                scenario = copy.deepcopy(plan)
                scenario['assumptions'] = profile['assumptions']
                require(fixed_plan(scenario) == fixed_plan(plan), 'fixed order plan changed')
                scenario_path = output/'scenarios'/(row['id']+'.json')
                write_json(scenario_path, scenario)
                scenario_sha = digest(read(scenario_path))
                row.update(recording_sha256=source_sha, scenario_sha256=scenario_sha,
                           fixed_plan_sha256=snapshot['fixed_plan_sha256'],
                           profile_sha256=digest(canonical(profile)), artifacts='cases/'+row['id'])
                EXECUTION.generate(pinned, root/'market/source', scenario_path, output/row['artifacts'],
                                   dataset['origin'], dataset['feed'], render_view=False,
                                   timeout_secs=native_timeout(manifest['limits'], deadline, 2))
                row['metrics'] = summarize(output/row['artifacts'], source_sha, scenario_sha)
                row.update(status='verified', reason=None)
            except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                row.update(status='failed', reason=type(error).__name__+': '+str(error)[:400], metrics=None)
    counts = {status: sum(c['status'] == status for c in cases) for status in ['verified', 'failed', 'not_run']}
    report = dict(batch_report_version=1, mode='offline_ioc_sensitivity', label=manifest['label'],
                  status='incomplete' if counts['not_run'] else 'completed_with_failures' if counts['failed'] else 'verified',
                  strategy_enabled=False, calibrated=False, full_window_verified=False,
                  manifest_sha256=digest(raw), binary_sha256=binary_sha, baseline_profile=manifest['baseline_profile'],
                  datasets=manifest['datasets'], profiles=manifest['profiles'], limits=manifest['limits'],
                  snapshots=snapshots, cases=cases, comparisons=comparisons(cases, manifest['baseline_profile']), counts=counts,
                  elapsed_seconds=round(time.monotonic()-started, 3), budget_enforcement='Admission checks between bounded native operations.')
    require(digest(read(pinned, 128*MIB)) == binary_sha, 'pinned binary changed during batch')
    report['artifact_bytes_before_report'] = used_bytes(output)
    write_json(output/'batch-report.json', report)
    with (output/'batch-lab.html').open('x') as destination:
        destination.write(render_report(report))
    return output/'batch-lab.html', report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    path, report = generate(args.binary, args.manifest, args.output_dir)
    print(path)
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
