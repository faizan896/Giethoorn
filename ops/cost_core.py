"""Causal R001 paper-policy compilation; no I/O, clocks or live orders."""
import copy
from decimal import Decimal, localcontext
import hashlib
import json

if __package__:
    from . import study_core as SIGNAL
else:
    import study_core as SIGNAL

POLICY = dict(cost_policy_version=1, policy_id='r001-ioc-probe-001',
    signal_policy=SIGNAL.POLICY, partition='development', max_children=4,
    warmup_ns=5_000_000_000, close_after_ns=1_000_000_000, max_quote_age_ns=250_000_000,
    limit_envelope_bps='2', target_quantity='0.001', starting_collateral='10000',
    max_abs_position='0.001', max_order_notional='100', max_working_orders=1, max_loss='10',
    cycles_per_child=1, independent_flat_start=True, exploratory=True,
    live_orders_enabled=False, portfolio_profit_evaluated=False)


def profile(name, fee='0.0005', slip='1', fraction='0.25', delay=100):
    return dict(id=name, fee_bps=format((Decimal(fee)*10000).normalize(), 'f'), assumptions=dict(fee_rate=fee, slippage_bps=slip,
        top_size_fraction=fraction, latency_ms=delay, quote_wait_ms=250))


PROFILES = [profile('baseline'), profile('lower-fee', fee='0.0001'), profile('zero-fee', fee='0'),
            profile('delay-stress', delay=250), profile('liquidity-stress', fraction='0.10'),
            profile('slippage-stress', slip='2')]
require = SIGNAL.require


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def text(value):
    require(value.is_finite(), 'nonfinite policy amount')
    return '0' if value == 0 else format(value, 'f').rstrip('0').rstrip('.') if value.as_tuple().exponent < 0 else format(value, 'f')


def limit_price(side, bid, ask):
    with localcontext() as context:
        context.prec = 100
        rate = Decimal(POLICY['limit_envelope_bps'])/10000
        return text(Decimal(ask if side == 'buy' else bid)*(1+rate if side == 'buy' else 1-rate))


def entry_scenario(feature, assumptions):
    require(feature['study_id'] == SIGNAL.POLICY['study_id'] and feature['feature_version'] == 1
            and feature['prediction'] in ('up', 'down'), 'directional R001 feature required')
    side = 'buy' if feature['prediction'] == 'up' else 'sell'
    return dict(scenario_version=1, label='R001 exploratory paper probe', assumptions=copy.deepcopy(assumptions),
        **{key: POLICY[key] for key in ('starting_collateral', 'max_abs_position', 'max_order_notional',
                                       'max_working_orders', 'max_loss')},
        orders=[dict(id='entry', after_market_sequence=feature['sequence'], side=side,
                     quantity=POLICY['target_quantity'], limit_price=limit_price(side, feature['bid'], feature['ask']))])


def close_decision(feature, market):
    """First observed usable event at the horizon; never interpolate a clock."""
    target = feature['monotonic_ns']+POLICY['close_after_ns']
    quote = None
    for frame, link in market:
        if link['generated_end']:
            continue
        if frame['event_kind'] == 'market_observed' and link['quote'] is not None:
            quote = link['quote']
        now = link['monotonic_ns']
        if now < target or not frame['account']['mark_fresh'] or frame['risk']['market_status'] != 'fresh':
            continue
        if quote is None or quote['connection_id'] != link['connection_id']:
            continue
        age = now-quote['monotonic_ns']
        if 0 <= age <= POLICY['max_quote_age_ns']:
            return dict(decision_version=1, sequence=link['market_sequence'], monotonic_ns=now,
                connection_id=link['connection_id'], target_ns=target, late_by_ns=now-target,
                quote=copy.deepcopy(quote), quote_age_ns=age)
    return None


def prefix_rows(rows, decision):
    """Control includes all transitions at the decision; compiled stops before close."""
    result = []
    for frame, link, step in rows:
        if link['generated_end'] or link['market_sequence'] > decision['sequence']:
            break
        if step['phase'] == 'scenario_request' and step['order_id'] == 'close':
            break
        normalized = copy.deepcopy(frame)
        # The scenario adds a close, so its raw fingerprint must change. No
        # accounting, risk, event, source-recording or order fields are removed.
        normalized['source'].pop('scenario_sha256', None)
        result.append([normalized, link, step])
    require(result and result[-1][1]['market_sequence'] == decision['sequence'], 'causal prefix boundary missing')
    return result


def compile_close(entry, decision, rows):
    plan = copy.deepcopy(entry)
    if decision is None:
        return plan, dict(status='missing_decision', decision=None, known_position=None, prefix_sha256=None)
    prefix = prefix_rows(rows, decision)
    state = prefix[-1][0]
    position = Decimal(state['account']['position_quantity'])
    with localcontext() as context:
        context.prec = 100
        fills = sum((Decimal(frame['assumed_fill']['quantity'])*(1 if frame['assumed_fill']['side'] == 'buy' else -1)
                     for frame, _, _ in prefix if frame['assumed_fill'] is not None), Decimal(0))
    require(position == fills and position.copy_abs() <= Decimal(POLICY['target_quantity']), 'entry prefix exposure differs')
    require(state['risk']['working_orders'] == 0, 'entry is unresolved at the close decision')
    require(position == 0 or (position > 0) == (entry['orders'][0]['side'] == 'buy'), 'entry position reversed')
    receipt = dict(status='flat_no_close' if position == 0 else 'close_compiled', decision=decision,
        known_position=text(position), prefix_rows=len(prefix), prefix_sha256=fingerprint(prefix),
        last_control_paper_sequence=state['sequence'], risk_at_decision=state['risk'])
    if position != 0:
        side = 'sell' if position > 0 else 'buy'
        quote = decision['quote']
        plan['orders'].append(dict(id='close', after_market_sequence=decision['sequence'], side=side,
            quantity=text(position.copy_abs()), limit_price=limit_price(side, quote['bid'], quote['ask'])))
    return plan, receipt


def verify_prefix(control_rows, compiled_rows, decision):
    if decision is None:
        return None
    a, b = prefix_rows(control_rows, decision), prefix_rows(compiled_rows, decision)
    require(a == b, 'compiled close changed the entry prefix')
    return fingerprint(a)


def metrics(execution, rows, receipt):
    paper = execution['paper']
    orders = {order['id']: order for order in paper['orders']}
    entry, close = orders['entry'], orders.get('close')
    account = paper['account']
    position = Decimal(account['position_quantity'])
    pending = execution['pending_order_ids']
    entry_qty = Decimal(entry['filled_quantity'])
    closed = entry_qty > 0 and position == 0 and not pending
    require(not closed or (close is not None and Decimal(close['filled_quantity']) == entry_qty), 'close quantity differs')
    with localcontext() as context:
        context.prec = 100
        closed_net = text(Decimal(account['realized_pnl'])-Decimal(account['fees'])) if closed else None
    last_quote = None
    path = []
    for frame, link, step in rows:
        if frame['event_kind'] == 'market_observed' and link['quote'] is not None:
            last_quote = link['quote']
        if step['phase'] != 'market':
            fill = frame['assumed_fill']
            path.append(dict(phase=step['phase'], order_id=step['order_id'], market_sequence=step['market_sequence'],
                fill=None if fill is None else {key: fill[key] for key in ('order_id', 'side', 'quantity', 'price')},
                order=frame['order']))
    outcome = 'unresolved' if pending or position != 0 else 'closed' if closed else 'entry_rejected' if entry['status'] == 'rejected' else 'no_entry_fill'
    return dict(outcome=outcome, entry_quantity=entry['filled_quantity'],
        entry_requested_quantity=entry['quantity'], entry_status=entry['status'],
        entry_rejection=entry.get('rejection'), entry_rejection_detail=entry.get('rejection_detail'),
        close_requested_quantity=None if close is None else close['quantity'],
        close_quantity=None if close is None else close['filled_quantity'], close_status=None if close is None else close['status'],
        close_rejection=None if close is None else close.get('rejection'),
        close_rejection_detail=None if close is None else close.get('rejection_detail'),
        position_quantity=account['position_quantity'], pending_order_ids=pending, risk=paper['risk'],
        fees=execution['fees'], spread_cost=execution['spread_cost'], slippage_cost=execution['slippage_cost'],
        realized_pnl=account['realized_pnl'], closed_case_net_pnl=closed_net,
        historical_mark_open_pnl=account['unrealized_pnl'] if position != 0 else None,
        historical_mark_price=account['mark_price'] if position != 0 else None,
        historical_mark_source=last_quote if position != 0 else None,
        close_decision_status=receipt['status'], close_late_by_ns=None if receipt['decision'] is None else receipt['decision']['late_by_ns'],
        execution_path_sha256=fingerprint(path))
