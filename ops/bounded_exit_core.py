"""One residual close chosen from a causal, settled native control prefix."""
import copy
from decimal import Decimal, localcontext

if __package__:
    from . import proxy_policy_core as CYCLE, evaluation_core as ECONOMICS
else:
    import proxy_policy_core as CYCLE
    import evaluation_core as ECONOMICS

FROZEN = CYCLE.FROZEN
require = CYCLE.require
PROTOCOL_SHA256 = '894827116ac7023bba4c10c9b0ae511d08ff18b124b36cbbf6d446df4649e2c7'
POLICY = dict(bounded_exit_policy_version=1, policy_id='r001-bounded-exit-002',
    control_policy_id=CYCLE.POLICY['policy_id'], partition='development',
    max_children=128, max_cases=768, max_requests_per_case=3, max_additional_closes=1,
    retry_id='close-retry', new_bbo_only=True, exploratory=True,
    actual_execution_known=False, portfolio_profit_evaluated=False,
    live_orders_enabled=False, full_window_verified=False)
TERMINAL = ('filled', 'cancelled', 'rejected')


def prefix(control, decision, final=False):
    records, links, frames = control
    require(len(records) == len(links) == len(frames), 'native prefix lengths differ')
    rows = []
    for record, link, frame in zip(records, links, frames):
        if link['phase'] == 'replay_end' or link['known_source_sequence'] > decision['sequence'] \
                or record['monotonic_ns'] > decision['monotonic_ns']:
            break
        if link['phase'] == 'request' and record['event']['id'] == POLICY['retry_id']:
            require(final, 'one-close control contains an extra request')
            break
        rows.append([record, link, frame])
    require(rows and rows[-1][1]['known_source_sequence'] == decision['sequence']
        and sum(link['phase'] == 'source' for _, link, _ in rows) == decision['sequence'],
        'retry decision source boundary is missing')
    return rows


def native_state(rows, plan):
    orders = {}
    with localcontext() as context:
        context.prec = 100
        fills = Decimal(0)
        for _, _, frame in rows:
            if frame['order'] is not None:
                orders[frame['order']['id']] = frame['order']
            fill = frame['assumed_fill']
            if fill is not None:
                fills += Decimal(fill['quantity']) * (1 if fill['side'] == 'buy' else -1)
        state = rows[-1][2]
        position = Decimal(state['account']['position_quantity'])
        entry = orders.get('entry')
        require(entry is not None, 'native entry state missing')
        entered = Decimal(entry['filled_quantity'])
        require(position.is_finite() and position == fills and abs(position) <= min(entered,
            Decimal(plan['orders'][0]['quantity']), Decimal(FROZEN.POLICY['target_quantity'])),
            'residual inventory differs from native fills or exceeds entry')
        require(position == 0 or (position > 0) == (plan['orders'][0]['side'] == 'buy'),
            'control inventory reversed entry direction')
    return position, state, orders


def fresh_candidate(event, state):
    quote = event['link']['quote']
    feed = (event['link'].get('feeds') or {}).get('bbo') or {}
    return event['usable'] and event['channel'] == 'bbo' and quote is not None \
        and quote['sequence'] == event['sequence'] and quote['connection_id'] == event['source']['connection_id'] \
        and feed.get('acknowledged') is True and feed.get('status') == 'fresh' \
        and 0 <= event['time'] - quote['monotonic_ns'] <= FROZEN.POLICY['max_quote_age_ns'] \
        and state['account']['mark_fresh'] is True and state['risk']['market_status'] == 'fresh'


def select(plan, events, control):
    require(1 <= len(plan['orders']) <= 2 and plan['orders'][0]['id'] == 'entry'
        and (len(plan['orders']) == 1 or plan['orders'][1]['id'] == 'close'), 'original one-close plan required')
    receipt = dict(bounded_exit_policy_version=1, status='no_first_close', decision=None,
        known_position=None, entry_filled_quantity=None, first_close_state=None,
        risk_at_decision=None, working_orders=None, prefix_records=None, prefix_sha256=None,
        delay_from_first_request_ns=None)
    if len(plan['orders']) == 1:
        return receipt
    anchor = plan['orders'][1]['after_market_sequence']
    require(type(anchor) is int and 1 <= anchor <= len(events), 'original close anchor differs')
    anchor_time = events[anchor-1]['time']
    records, links, frames = control
    require(len(records) == len(links) == len(frames) and len(records) <= 10000, 'bounded native control required')
    rows, index, orders = [], 0, {}
    last = None
    with localcontext() as context:
        context.prec = 100
        fills = Decimal(0)
        for event in events:
            while index < len(records):
                record, link, frame = records[index], links[index], frames[index]
                if link['phase'] == 'replay_end' or link['known_source_sequence'] > event['sequence'] \
                        or record['monotonic_ns'] > event['time']:
                    break
                require(not (link['phase'] == 'request' and record['event']['id'] == POLICY['retry_id']),
                    'control contains an extra close')
                rows.append([record, link, frame]); index += 1
                if frame['order'] is not None:
                    orders[frame['order']['id']] = frame['order']
                fill = frame['assumed_fill']
                if fill is not None:
                    fills += Decimal(fill['quantity']) * (1 if fill['side'] == 'buy' else -1)
            if event['sequence'] <= anchor:
                continue
            require(rows and rows[-1][1]['known_source_sequence'] == event['sequence'], 'control/source prefix differs')
            state = rows[-1][2]
            first = orders.get('close')
            entry = orders.get('entry')
            require(entry is not None, 'native entry is missing before retry scan')
            position = Decimal(state['account']['position_quantity'])
            require(position == fills and abs(position) <= min(Decimal(entry['filled_quantity']),
                Decimal(plan['orders'][0]['quantity']), Decimal(FROZEN.POLICY['target_quantity'])),
                'control residual differs from known entry/fills')
            require(position == 0 or (position > 0) == (plan['orders'][0]['side'] == 'buy'), 'control position reversed')
            settled = first is not None and first['status'] in TERMINAL and not first['cancel_pending'] \
                and state['risk']['working_orders'] == 0 \
                and all(order['status'] in TERMINAL and not order['cancel_pending'] for order in orders.values())
            last = (event, position, state, entry, first, index, settled)
            if not settled:
                continue
            if position == 0:
                status = 'already_flat'
            elif not fresh_candidate(event, state):
                continue
            else:
                status = 'risk_halted' if state['risk']['halted'] else 'retry_compiled'
            break
        else:
            status = 'first_close_unresolved' if last is None or not last[-1] else 'no_retry_quote'
    require(last is not None, 'control has no observed source after first close')
    event, position, state, entry, first, count, _ = last
    quote = copy.deepcopy(event['link']['quote'])
    decision = dict(sequence=event['sequence'], monotonic_ns=event['time'],
        connection_id=event['source']['connection_id'], source_event=event['source']['event']['type'],
        quote=quote, quote_age_ns=None if quote is None else event['time']-quote['monotonic_ns'])
    receipt.update(status=status, decision=decision, known_position=FROZEN.text(position),
        entry_filled_quantity=entry['filled_quantity'], first_close_state=copy.deepcopy(first),
        risk_at_decision=copy.deepcopy(state['risk']), working_orders=state['risk']['working_orders'],
        prefix_records=count, prefix_sha256=FROZEN.fingerprint(rows[:count]),
        delay_from_first_request_ns=event['time']-anchor_time)
    return receipt


def compile_retry(plan, events, control):
    receipt = select(plan, events, control)
    result = copy.deepcopy(plan)
    if receipt['status'] == 'retry_compiled':
        position = Decimal(receipt['known_position'])
        side = 'sell' if position > 0 else 'buy'
        quote = receipt['decision']['quote']
        result['orders'].append(dict(id=POLICY['retry_id'], side=side,
            after_market_sequence=receipt['decision']['sequence'], quantity=FROZEN.text(position.copy_abs()),
            limit_price=FROZEN.limit_price(side, quote['bid'], quote['ask'])))
    return result, receipt


def verify_retry(control_plan, plan, events, receipt, control, final):
    expected = select(control_plan, events, control)
    require(all(receipt.get(key) == value for key, value in expected.items()), 'retry receipt differs from first eligible native state')
    require({k:v for k,v in plan.items() if k != 'orders'} == {k:v for k,v in control_plan.items() if k != 'orders'}
        and plan['orders'][:len(control_plan['orders'])] == control_plan['orders']
        and len(plan['orders']) <= POLICY['max_requests_per_case'], 'retry changed original requests or assumptions')
    decision = expected['decision']
    if decision is None:
        require(plan == control_plan and control == final, 'absent first close gained a retry or different ledger')
        return dict(status='verified', decision_available=False, prefix_records=None, prefix_sha256=None)
    before = prefix(control, decision)
    after = prefix(final, decision, final=True)
    require(before == after and len(before) == expected['prefix_records']
        and FROZEN.fingerprint(before) == expected['prefix_sha256'], 'retry changed the complete original native prefix')
    position, state, orders = native_state(before, control_plan)
    if expected['status'] != 'retry_compiled':
        require(plan == control_plan, 'ineligible control gained an additional close')
    else:
        retry = plan['orders'][-1]
        require(len(plan['orders']) == len(control_plan['orders'])+1 and retry['id'] == POLICY['retry_id']
            and retry['after_market_sequence'] == decision['sequence']
            and Decimal(retry['quantity']) == position.copy_abs() and retry['side'] == ('sell' if position > 0 else 'buy'),
            'extra close size, side or source anchor differs from known residual')
        require(not state['risk']['halted'] and state['risk']['working_orders'] == 0
            and orders['close']['status'] in TERMINAL and not orders['close']['cancel_pending'], 'retry bypassed native risk/order state')
        with localcontext() as context:
            context.prec = 100
            rate = Decimal(FROZEN.POLICY['limit_envelope_bps'])/10000
            expected_limit = Decimal(decision['quote']['bid' if position > 0 else 'ask']) * (1-rate if position > 0 else 1+rate)
            require(Decimal(retry['limit_price']) == expected_limit, 'retry limit differs from its known quote')
    return dict(status='verified', decision_available=True, prefix_records=len(before), prefix_sha256=expected['prefix_sha256'])


def summarize(cases):
    require(all(c['status'] == 'verified' or c.get('control') is None for c in cases),
        'unverified case retained control metrics')
    current = ECONOMICS.summarize(cases)
    controls = [dict(child=c['child'], profile=c['profile'], status=c['status'],
        policy=c['control'] if c['status'] == 'verified' else None) for c in cases]
    original = ECONOMICS.summarize(controls)
    current['first_close_requests'] = current['close_requests']
    current['retry_requests'] = 0
    comparisons = []
    with localcontext() as context:
        context.prec = 100
        for c in cases:
            pair = dict(case_id=c['case_id'], status=c['status'], transition=None, fee_delta=None,
                conditional_closed_net_delta=None, unavailable_reason='Both policy cases must verify.')
            if c['status'] == 'verified':
                old, new = c['control']['metrics'], c['policy']['metrics']
                def outcome(m):
                    return 'closed' if m['conditional_closed_pnl'] is not None else 'unresolved' \
                        if Decimal(m['ending_position_quantity']) != 0 or m['pending_order_ids'] else 'no_fills'
                pair.update(transition=outcome(old)+'_to_'+outcome(new),
                    fee_delta=str(Decimal(new['fees'])-Decimal(old['fees'])), unavailable_reason=None)
                if old['conditional_closed_pnl'] is not None and new['conditional_closed_pnl'] is not None:
                    pair['conditional_closed_net_delta'] = str(Decimal(new['conditional_closed_pnl'])-Decimal(old['conditional_closed_pnl']))
                else:
                    pair['unavailable_reason'] = 'Closed return comparison requires both cases to finish closed.'
                current['retry_requests'] += new['retry_requested_quantity'] is not None
            comparisons.append(pair)
        for p in current['profiles']:
            members = [c for c in cases if c['profile'] == p['profile'] and c['status'] == 'verified']
            p['retry_requests'] = sum(c['policy']['metrics']['retry_requested_quantity'] is not None for c in members)
            ids = {c['case_id'] for c in members}
            p['unresolved_to_closed'] = sum(pair['case_id'] in ids and pair['transition'] == 'unresolved_to_closed' for pair in comparisons)
            p['unresolved_to_unresolved'] = sum(pair['case_id'] in ids and pair['transition'] == 'unresolved_to_unresolved' for pair in comparisons)
    current['close_requests'] += current['retry_requests']
    return current, original, comparisons
