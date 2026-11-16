#!/usr/bin/env python3
"""Build an offline controlled IOC lab and independently verify its costs."""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PROJECT = Path(__file__).resolve().parent.parent
MAX_FILE = 32 * 1024 * 1024
FINANCIAL_FIELDS = frozenset(('fee_rate', 'slippage_bps', 'top_size_fraction', 'starting_collateral',
                             'max_abs_position', 'max_order_notional', 'max_loss', 'limit_price', 'quantity'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE,
            'invalid or oversized execution artifact')
    return path.read_bytes()


def semantic_scenario(value, field=None):
    # Rust normalizes exact decimal strings; the fingerprint still binds raw bytes.
    if isinstance(value, dict):
        return {key: semantic_scenario(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [semantic_scenario(item) for item in value]
    return Decimal(value) if field in FINANCIAL_FIELDS else value


def verify_costs(report, frames, links, trace, original):
    """Decimal algebra, original book sizes and timing; no strategy inference."""
    plan = report['scenario']
    model = plan['assumptions']
    orders = {order['id']: order for order in plan['orders']}
    sums = dict(spread_cost=Decimal(0), slippage_cost=Decimal(0), fees=Decimal(0))
    current_quote = None
    requests = set()
    initial_capacity, consumed, last_prices, ambiguous = {}, {}, {}, set()
    fills = 0
    with localcontext() as context:
        context.prec = 100
        for frame, link, step in zip(frames, links, trace):
            source = original[link['market_sequence']-1]
            require(source['sequence'] == link['market_sequence']
                    and source['monotonic_ns'] == link['monotonic_ns'] == frame['monotonic_ns']
                    and source['local_time_ns'] == link['local_time_ns']
                    and source['connection_id'] == link['connection_id'], 'execution link differs from original event')
            if frame['event_kind'] == 'market_observed':
                current_quote = link['quote']
                require(current_quote and current_quote['sequence'] == source['sequence'],
                        'market mark lacks its original quote')
                payload = json.loads(source['event']['text'])['data']
                feed = report['paper']['config']['source']['feed']
                levels = payload['bbo'] if feed == 'bbo' else [next(level for level in levels if Decimal(level['sz']) > 0) for levels in payload['levels']]
                identity = (current_quote['connection_id'], current_quote['exchange_time_ms'])
                prices = tuple(Decimal(level['px']) for level in levels)
                if identity in last_prices and last_prices[identity] != prices:
                    ambiguous.add(identity)
                last_prices[identity] = prices
                for side, level in enumerate(levels):
                    initial_capacity.setdefault(identity+(side,), Decimal(level['sz'])*Decimal(model['top_size_fraction']))
            if frame['event_kind'] == 'order_requested':
                order = frame['order']
                intended = orders.get(order['id'])
                require(intended and intended['after_market_sequence'] == source['sequence']
                        and order['id'] not in requests and order['side'] == intended['side']
                        and Decimal(order['quantity']) == Decimal(intended['quantity'])
                        and Decimal(order['limit_price']) == Decimal(intended['limit_price']),
                        'order request differs from the fixed scenario')
                requests.add(order['id'])
            fill = frame['assumed_fill']
            if fill:
                fills += 1
                intended = orders[fill['order_id']]
                sent = original[intended['after_market_sequence']-1]
                arrival = sent['monotonic_ns'] + model['latency_ms'] * 1000000
                expiry = arrival + model['quote_wait_ms'] * 1000000
                require(step['phase'] == 'assumed_fill' and not frame['duplicate']
                        and source['sequence'] > sent['sequence']
                        and arrival <= source['monotonic_ns'] < expiry
                        and step['arrival_ns'] == arrival and step['expiry_ns'] == expiry
                        and frame['account']['mark_fresh'] and frame['risk']['market_status'] == 'fresh'
                        and current_quote and current_quote['sequence'] == source['sequence'],
                        'assumed fill violates causality, freshness or its timing window')
                payload = json.loads(source['event']['text'])['data']
                feed = report['paper']['config']['source']['feed']
                side = 1 if fill['side'] == 'buy' else 0
                level = payload['bbo'][side] if feed == 'bbo' else next(level for level in payload['levels'][side] if Decimal(level['sz']) > 0)
                touch = Decimal(level['px'])
                require(touch == Decimal(current_quote['ask' if side == 1 else 'bid']),
                        'fill touch price differs from original book')
                quantity, price = Decimal(fill['quantity']), Decimal(fill['price'])
                capacity = Decimal(level['sz']) * Decimal(model['top_size_fraction'])
                require(0 < quantity <= Decimal(step['available_quantity']) <= capacity,
                        'assumed fill exceeds the source top-size cap')
                identity = (current_quote['connection_id'], current_quote['exchange_time_ms'])
                key = identity+(side,)
                consumed[key] = consumed.get(key, Decimal(0))+quantity
                require(identity not in ambiguous and consumed[key] <= initial_capacity[key],
                        'assumed fills reuse ambiguous or already-consumed liquidity')
                slippage_rate = Decimal(model['slippage_bps']) / Decimal(10000)
                expected_price = touch * (1 + slippage_rate if side == 1 else 1 - slippage_rate)
                fee = price * quantity * Decimal(model['fee_rate'])
                spread = abs(touch-Decimal(current_quote['mid'])) * quantity
                slippage = abs(price-touch) * quantity
                require(price == expected_price and Decimal(step['touch_price']) == touch
                        and Decimal(fill['fee']) == Decimal(step['fee']) == fee
                        and Decimal(step['spread_cost']) == spread and Decimal(step['slippage_cost']) == slippage,
                        'assumed fill price or cost decomposition disagrees with Decimal verification')
            else:
                require(all(Decimal(step[key]) == 0 for key in ['fee', 'spread_cost', 'slippage_cost']),
                        'non-fill event charged an execution cost')
            sums['fees'] += Decimal(step['fee'])
            sums['spread_cost'] += Decimal(step['spread_cost'])
            sums['slippage_cost'] += Decimal(step['slippage_cost'])
            require(all(Decimal(step['cumulative_costs'][key]) == value for key, value in sums.items()),
                    'cumulative execution costs disagree')
        require(requests == set(orders), 'scenario requests are missing')
        require(fills == report['paper']['assumed_fills']
                and all(Decimal(report[key]) == value for key, value in sums.items()),
                'execution cost totals disagree')
        account = report['paper']['account']
        balance = Decimal(plan['starting_collateral']) + Decimal(account['realized_pnl']) - sums['fees']
        require(Decimal(account['collateral_balance']) == balance and Decimal(account['fees']) == sums['fees'],
                'collateral algebra disagrees')
        if account['equity'] is not None:
            require(Decimal(account['equity']) == balance + Decimal(account['unrealized_pnl'])
                    and Decimal(account['net_pnl']) == Decimal(account['equity'])-Decimal(plan['starting_collateral']),
                    'equity or net PnL algebra disagrees')
    return dict(status='verified', assumed_fills=fills, **{key: str(value) for key, value in sums.items()})


def generate(binary, recording, scenario, output, origin, feed='bbo', *, render_view=True, timeout_secs=120):
    binary, recording, scenario, output = binary.resolve(), recording.resolve(), scenario.resolve(), output.resolve()
    require(origin in ('captured_public_data', 'synthetic_fixture') and feed in ('bbo', 'depth'),
            'explicit supported source origin/feed required')
    require(type(timeout_secs) in (int, float) and 0 < timeout_secs <= 600,
            'native replay timeout must be in (0,600] seconds')
    require(binary.is_file() and os.access(binary, os.X_OK), 'replay executable required')
    require(recording.is_dir() and not output.is_relative_to(recording), 'output must be outside the source recording')
    raw_scenario = read(scenario)
    require(len(raw_scenario) <= 64*1024, 'scenario exceeds 64 KiB limit')
    scenario_sha = hashlib.sha256(raw_scenario).hexdigest()
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    os.umask(0o077)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    command = [str(binary), 'paper-execution-replay', '--input', str(recording), '--scenario', str(scenario),
               '--output-dir', str(output/'replay'), '--origin', origin.replace('_', '-'), '--feed', feed]
    with (output/'command.stdout').open('xb') as stdout, (output/'command.stderr').open('xb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                check=False, timeout=timeout_secs)
    require(result.returncode == 0, 'execution replay failed; diagnostics retained')
    replay = output/'replay'
    execution = json.loads(read(replay/'execution-replay.json'))
    report = json.loads(read(replay/'paper-report.json'))
    frames = [json.loads(line) for line in read(replay/'paper-updates.jsonl').splitlines()]
    links = [json.loads(line) for line in read(replay/'market-links.jsonl').splitlines()]
    trace = [json.loads(line) for line in read(replay/'execution-trace.jsonl').splitlines()]
    require(execution['execution_model_version'] == 1 and execution['mode'] == 'offline_controlled_ioc'
            and execution['scenario_orders_enabled'] is True and execution['strategy_enabled'] is False
            and execution['full_window_verified'] is False and execution['paper'] == report,
            'unsupported or inconsistent execution envelope')
    require(read(replay/'scenario.json') == raw_scenario and execution['scenario_sha256'] == scenario_sha
            and semantic_scenario(execution['scenario']) == semantic_scenario(json.loads(raw_scenario)),
            'scenario provenance disagrees')
    source = report['config']['source']
    manifest = execution['market']['source']
    require(report['paper_model_version'] == 3 and report['fill_model'] == 'assumed_next_fresh_quote_ioc_v1'
            and source['kind'] == 'recorded_execution' and source['origin'] == manifest['origin'] == origin
            and source['feed'] == feed and source['scenario_sha256'] == scenario_sha
            and source['assumptions'] == execution['scenario']['assumptions']
            and report['config']['fee_rate'] == source['assumptions']['fee_rate'], 'execution source/model disagrees')
    files = manifest['files']
    require(manifest['manifest_version'] == 1 and [f['file'] for f in files] == sorted({f['file'] for f in files}),
            'invalid source manifest')
    original = []
    for entry in files:
        require(re.fullmatch(r'index\.jsonl|segment-[0-9]{8}\.jsonl', entry['file']) is not None,
                'invalid source filename')
        raw = read(replay/'market/source'/entry['file'])
        require(len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256'], 'source copy changed')
        if entry['file'].startswith('segment-'):
            original.extend(json.loads(line) for line in raw.splitlines())
    digest = hashlib.sha256(b'giethoorn-recorded-market-v1\0'+json.dumps(files, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    require(source['recording_sha256'] == manifest['recording_sha256'] == digest, 'source fingerprint disagrees')
    require(execution['market']['source_report']['complete'] and execution['market']['source_storage']['finalized']
            and len(original) == execution['market']['source_report']['records'], 'source is not finalized')
    require(report['complete'] and 1 < len(frames) <= 10000 and len(frames) == len(links) == len(trace) == report['records']
            and frames[-1]['complete'] and all(not f['complete'] for f in frames[:-1]), 'invalid execution frame count')
    base_sequences = []
    for i, (frame, link, step) in enumerate(zip(frames, links, trace), 1):
        require(frame['sequence'] == link['paper_sequence'] == step['paper_sequence'] == i
                and frame['source'] == source and frame['paper_model_version'] == 3 and frame['mode'] == 'paper'
                and link['market_sequence'] == step['market_sequence'], 'execution frames or source links disagree')
        if step['phase'] == 'market':
            base_sequences.append(link['market_sequence'])
    require(base_sequences == list(range(1, len(original)+1)) and links[-1]['generated_end']
            and all(not link['generated_end'] for link in links[:-1])
            and trace[-1]['phase'] == 'replay_end', 'market timeline was dropped, duplicated or prematurely ended')
    require(frames[-1]['account'] == report['account'] and frames[-1]['risk'] == report['risk'], 'final account disagrees')
    pending = sorted(o['id'] for o in report['orders'] if o['status'] == 'pending_new')
    require(sorted(execution['pending_order_ids']) == pending, 'pending orders disagree')
    audit = verify_costs(execution, frames, links, trace, original)
    (output/'cost-audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    replay_command = [str(binary), 'paper-replay', '--input', str(replay/'paper-input.jsonl')]
    with (output/'replayed-updates.jsonl').open('xb') as stdout, (output/'replayed-report.json').open('xb') as stderr:
        checked = subprocess.run(replay_command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                 check=False, timeout=timeout_secs)
    require(checked.returncode == 0 and read(output/'replayed-updates.jsonl') == read(replay/'paper-updates.jsonl')
            and json.loads(read(output/'replayed-report.json')) == report, 'independent ledger replay disagrees')
    require(hashlib.sha256(binary.read_bytes()).hexdigest() == binary_sha, 'replay executable changed during export')
    (output/'run.json').write_text(json.dumps(dict(schema_version=1, command=command, replay_check_command=replay_command,
        binary_sha256=binary_sha, recording_sha256=digest, scenario_sha256=scenario_sha,
        paper_model_version=3, strategy_enabled=False, full_window_verified=False,
        rendered_view=render_view, native_timeout_seconds=timeout_secs), indent=2)+'\n')
    if not render_view:
        return replay/'execution-replay.json'
    boot = json.dumps(dict(report=report, frames=frames, market=dict(links=links, replay=execution['market']),
        execution=dict(report=execution, trace=trace)), separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (PROJECT/'web/paper.html').read_text()
    require(template.count('__PAPER_BOOT__') == template.count('__GIETHOORN_THEME__') == 1, 'invalid Paper Lab template')
    html = template.replace('__GIETHOORN_THEME__', (PROJECT/'web/theme.css').read_text()).replace('__PAPER_BOOT__', boot)
    require(len(html.encode()) <= 16*1024*1024, 'portable execution view exceeds 16 MiB limit')
    with (output/'paper-lab.html').open('x') as destination:
        destination.write(html)
    return output/'paper-lab.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--origin', choices=('captured-public-data', 'synthetic-fixture'), required=True)
    parser.add_argument('--feed', choices=('bbo', 'depth'), default='bbo')
    parser.add_argument('--no-view', action='store_true', help='Verify and retain replay evidence without generating HTML.')
    parser.add_argument('--timeout-seconds', type=float, default=120, help='Timeout for each native replay subprocess.')
    args = parser.parse_args()
    print(generate(args.binary, args.input, args.scenario, args.output_dir, args.origin.replace('-', '_'),
                   args.feed, render_view=not args.no_view, timeout_secs=args.timeout_seconds))
