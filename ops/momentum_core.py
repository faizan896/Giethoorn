"""Pure R002 prefix selection, native close compilation and research gates."""
from collections import Counter, deque
import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json

if __package__:
    from . import bounded_exit_core as BOUND, evaluation_core as ECONOMICS
else:
    import bounded_exit_core as BOUND
    import evaluation_core as ECONOMICS

FROZEN = BOUND.FROZEN
SIGNAL = FROZEN.SIGNAL
CYCLE = BOUND.CYCLE
require = FROZEN.require
PROTOCOL_SHA256 = '1e84c6beeb92f7522c4e1a2d571e4990466705b51318198264849417e5e03c02'
POLICY_SHA256 = 'd6ee87006f5c39800da3be2e1a8a678a0d7b29f73b1f6bb5fb5218931245907b'
POLICY = json.loads('{"actual_execution_known":false,"additional_close_id":"close-retry","additional_close_requires_settled_native_control":true,"additional_close_window_end":"actual_source_eof","candidate_selection":"first_native_accepted_unique_bbo_per_bin_without_replacement","clock_discontinuity_ns":1000000000,"coin":"BTC","cost_screen":{"buffer_bps":"2","fee_screen_is_an_execution_charge":false,"hurdle":"current_spread_bps+14","negative_equality_qualifies":true,"past_move":"10000*(current_mid-reference_mid)/reference_mid","positive_equality_qualifies":true,"profile":"baseline","round_trip_fee_bps":"10","round_trip_slippage_bps":"2","spread":"10000*(ask-bid)/((bid+ask)/2)"},"cycles_per_child_profile":1,"development_screen":{"baseline_and_each_third_net_strictly_positive":true,"chronological_thirds":"floor(N/3),floor(N/3),remainder_of_frozen_children","min_baseline_closed":30,"min_baseline_closed_per_third":10,"min_closed_per_required_stress_profile":30,"primary_profile":"baseline","required_profiles_have_no_unresolved_or_unavailable_cases":true,"required_stress_nets_strictly_positive":true,"required_stress_profiles":["delay-stress","liquidity-stress","slippage-stress"],"success":"candidate_for_separately_predeclared_new_data_confirmation_only"},"entry_selection":"first_qualifying_candidate_before_forward_labels_or_execution","experiment_id":"r002-cost-momentum-001","exploratory":true,"feature_version":1,"first_candidate_bin_ns":30000000000,"first_close_max_ns":31000000000,"first_close_min_ns":30000000000,"first_close_reconnected_quote_allowed":true,"first_close_selection":"first_fresh_new_native_bbo_in_window_without_replacement","full_window_verified":false,"history_connection_crossing":false,"limit_envelope_bps":"2","limits":{"case_allowance_bytes":402653184,"free_reserve_bytes":1073741824,"max_cases":768,"max_children":128,"max_considered_bins_per_child":4096,"max_history_observations":10000,"max_requests_per_case":3,"native_seconds":30,"outer_timeout_seconds":3660,"output_bytes":17179869184,"report_reserve_bytes":33554432,"source_allowance_bytes":134217728,"suite_seconds":3600},"live_orders_enabled":false,"lookback_ns":30000000000,"max_abs_position":"0.001","max_additional_closes":1,"max_close_quote_age_ns":250000000,"max_feature_quote_age_ns":250000000,"max_history_bbo_gap_ns":1000000000,"max_loss":"10","max_order_notional":"100","max_working_orders":1,"network":"mainnet","partition":"development","policy_version":1,"portfolio_profit_evaluated":false,"prediction_diagnostic":{"filters_entry":false,"max_bbo_gap_ns":1000000000,"max_label_ns":30250000000,"min_label_ns":30000000000,"same_connection":true},"profiles":[{"assumptions":{"fee_rate":"0.0005","latency_ms":100,"quote_wait_ms":250,"slippage_bps":"1","top_size_fraction":"0.25"},"fee_bps":"5","id":"baseline"},{"assumptions":{"fee_rate":"0.0001","latency_ms":100,"quote_wait_ms":250,"slippage_bps":"1","top_size_fraction":"0.25"},"fee_bps":"1","id":"lower-fee"},{"assumptions":{"fee_rate":"0","latency_ms":100,"quote_wait_ms":250,"slippage_bps":"1","top_size_fraction":"0.25"},"fee_bps":"0","id":"zero-fee"},{"assumptions":{"fee_rate":"0.0005","latency_ms":250,"quote_wait_ms":250,"slippage_bps":"1","top_size_fraction":"0.25"},"fee_bps":"5","id":"delay-stress"},{"assumptions":{"fee_rate":"0.0005","latency_ms":100,"quote_wait_ms":250,"slippage_bps":"1","top_size_fraction":"0.10"},"fee_bps":"5","id":"liquidity-stress"},{"assumptions":{"fee_rate":"0.0005","latency_ms":100,"quote_wait_ms":250,"slippage_bps":"2","top_size_fraction":"0.25"},"fee_bps":"5","id":"slippage-stress"}],"r002_research_protocol_version":1,"reference_tolerance_ns":250000000,"report_version":1,"sampling_bin_ns":5000000000,"sampling_origin":"first_source_monotonic_timestamp_per_child","signal_id":"btc-bbo-cost-momentum-002","starting_collateral":"10000","target_quantity":"0.001","unique_exchange_times_per_connection":true}')
PROFILES = POLICY['profiles']
LIMITS = POLICY['limits']


def ratio(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def display(value):
    return SIGNAL.fixed(SIGNAL.rounded_ticks(value), 12)


def fresh(event):
    return BOUND.fresh_candidate(event, event['frame'])


def prices(event):
    """Verify original positive sizes/prices against their new native BBO quote."""
    source, quote = event['source'], event['link']['quote']
    payload = json.loads(source['event']['text'])
    data = payload['data']
    bid, ask = data['bbo']
    b, a = SIGNAL.positive(bid['px']), SIGNAL.positive(ask['px'])
    for side in (bid,ask):
        size = side['sz']
        require(type(size) is str and len(size) <= 128, 'bounded R002 BBO size required')
        value = Decimal(size)
        require(value.is_finite() and value >= 0 and abs(value.adjusted()) <= 128, 'invalid R002 BBO size')
    require(payload['channel'] == 'bbo' and data['coin'] == POLICY['coin']
        and data['time'] == quote['exchange_time_ms'] and b < a
        and b == SIGNAL.positive(quote['bid']) and a == SIGNAL.positive(quote['ask']),
        'R002 original BBO differs from native quote')
    return b, a, (b+a)/2


def positive_sizes(event):
    sizes = json.loads(event['source']['event']['text'])['data']['bbo']
    prices(event)
    return all(Decimal(side['sz']) > 0 for side in sizes)


def verify_normalization(events, observations):
    seen = set()
    accepted = set()
    for observation in observations:
        sequence = observation['sequence']
        require(type(sequence) is int and 1 <= sequence <= len(events) and sequence not in seen, 'R002 normalized reference duplicated or outside source')
        seen.add(sequence)
        event = events[sequence-1]
        require(all(observation[k] == event['source'][k] for k in ('sequence','connection_id','local_time_ns','monotonic_ns'))
            and observation['coin'] == POLICY['coin'], 'R002 normalized source identity differs')
        if observation['kind'] == 'bbo' and observation.get('quote') is not None:
            require(observation['quote'] == event['link']['quote']
                and observation['feeds']['bbo'] == event['link']['feeds']['bbo'], 'R002 independently normalized BBO differs')
            if fresh(event): accepted.add(sequence)
    require(accepted == {e['sequence'] for e in events if fresh(e)}, 'R002 native BBO opportunity membership differs')
    return dict(status='verified',bbo_opportunities=len(accepted))


def point(event):
    b, a, mid = prices(event)
    return dict(sequence=event['sequence'], monotonic_ns=event['time'],
        local_time_ns=event['source']['local_time_ns'], connection_id=event['source']['connection_id'],
        exchange_time_ms=event['link']['quote']['exchange_time_ms'], bid=event['link']['quote']['bid'],
        ask=event['link']['quote']['ask'], mid=ratio(mid), mid_display=display(mid),
        quote_age_ns=event['time']-event['link']['quote']['monotonic_ns'])


def fraction(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


def movement(current, reference):
    b, a = SIGNAL.positive(current['bid']), SIGNAL.positive(current['ask'])
    mid, previous = (b+a)/2, fraction(reference['mid'])
    move, spread = (mid-previous)/previous*10000, (a-b)/mid*10000
    cost, hurdle = spread+12, spread+14
    return dict(past_move_bps=ratio(move), current_spread_bps=ratio(spread),
        assumed_round_trip_cost_bps=ratio(cost), entry_hurdle_bps=ratio(hurdle),
        past_move_bps_display=display(move), spread_bps_display=display(spread),
        hurdle_bps_display=display(hurdle), prediction='up' if move >= hurdle else 'down' if move <= -hurdle else 'abstain')


def select(events, child):
    """Stops at the first qualifying feature. No label or execution is read."""
    require(events and len(events) < 10000, 'bounded R002 source required')
    start = events[0]['time']
    history, seen, candidates, missing = deque(), {}, [], Counter()
    previous, last_unique, connection = None, None, None
    next_bin = POLICY['first_candidate_bin_ns']//POLICY['sampling_bin_ns']
    first_bin, digest, resets = next_bin, hashlib.sha256(), Counter()
    selected = None
    for index, event in enumerate(events, 1):
        require(event['sequence'] == index, 'R002 source sequence differs')
        now, source = event['time'], event['source']
        digest.update(FROZEN.encoded(source)+b'\n')
        reason = None
        if previous is not None:
            require(now >= previous['time'], 'R002 source monotonic clock regressed')
            wall_delta = source['local_time_ns']-previous['source']['local_time_ns']
            if wall_delta < 0 or abs(wall_delta-(now-previous['time'])) >= POLICY['clock_discontinuity_ns']:
                reason = 'clock_discontinuity'
        if source['connection_id'] != connection:
            reason = 'connection_changed'
            connection = source['connection_id']
        feed = (event['link'].get('feeds') or {}).get('bbo') or {}
        if feed.get('acknowledged') is not True or feed.get('status') != 'fresh':
            reason = 'bbo_unusable'
        if last_unique is not None and now-last_unique > POLICY['max_history_bbo_gap_ns']:
            reason = 'bbo_gap_over_1000ms'
        usable = fresh(event)
        if usable and not positive_sizes(event): reason = 'nonpositive_bbo_size'
        if reason:
            history.clear(); last_unique = None; resets[reason] += 1
        previous = event
        if not usable or not positive_sizes(event):
            continue
        timestamp = event['link']['quote']['exchange_time_ms']
        used = seen.setdefault(connection, set())
        if timestamp in used:
            continue
        used.add(timestamp)
        current = point(event)
        history.append(current); last_unique = now
        require(len(history) <= LIMITS['max_history_observations'], 'R002 history observation bound exceeded')
        lower = now-POLICY['lookback_ns']
        while history and history[0]['monotonic_ns'] < lower:
            history.popleft()
        bin_number = (now-start)//POLICY['sampling_bin_ns']
        if bin_number < next_bin:
            continue
        require(bin_number-first_bin+1 <= LIMITS['max_considered_bins_per_child'], 'R002 candidate bin bound exceeded')
        missing['bins_without_candidate'] += bin_number-next_bin
        next_bin = bin_number+1
        reference = history[0] if history and history[0]['monotonic_ns'] <= lower+POLICY['reference_tolerance_ns'] else None
        row = dict(feature_version=1, signal_id=POLICY['signal_id'], child=child, bin=bin_number,
            **current, status='missing_history', prediction=None, reason='reference_or_continuous_history_unavailable',
            reference=None, source_prefix_sha256=digest.hexdigest())
        if reference is None:
            missing['history_unavailable'] += 1
        else:
            row.update(movement(current, reference), reference=copy.deepcopy(reference), status='eligible', reason=None)
            if row['prediction'] == 'abstain': missing['abstentions'] += 1
        candidates.append(row)
        if row['prediction'] in ('up','down'):
            selected = copy.deepcopy(row)
            break
    if selected is None:
        last_bin = (events[-1]['time']-start)//POLICY['sampling_bin_ns']
        require(max(0,last_bin-first_bin+1) <= LIMITS['max_considered_bins_per_child'], 'R002 candidate bin bound exceeded')
        missing['bins_without_candidate'] += max(0,last_bin-next_bin+1)
    considered = len(candidates)+missing['bins_without_candidate']
    return dict(selection_version=1, signal_id=POLICY['signal_id'], status='selected' if selected else 'no_signal',
        feature=selected, candidates=candidates, counts=dict(considered_bins=considered, candidates=len(candidates),
            bins_without_candidate=missing['bins_without_candidate'], missing_history=missing['history_unavailable'],
            abstentions=missing['abstentions']), history_resets=dict(resets), source_prefix_sha256=digest.hexdigest())


def verify_selection(events, child, receipt):
    require(select(events, child) == receipt, 'R002 selection receipt differs from its causal prefix')
    f = receipt['feature']
    if f is not None:
        quote, ref = events[f['sequence']-1], events[f['reference']['sequence']-1]
        b, a, m = prices(quote); _, _, old = prices(ref)
        move = (m-old)*10000/old
        hurdle = (a-b)*10000/m+14
        require(fraction(f['past_move_bps']) == move and fraction(f['entry_hurdle_bps']) == hurdle
            and f['prediction'] == ('up' if move >= hurdle else 'down' if move <= -hurdle else 'abstain'),
            'R002 independently checked signal arithmetic differs')
    return dict(status='verified', feature_available=f is not None, source_prefix_sha256=receipt['source_prefix_sha256'])


def entry_scenario(feature, profile):
    require(feature['signal_id'] == POLICY['signal_id'] and feature['prediction'] in ('up','down'), 'R002 directional feature required')
    require(profile in PROFILES, 'R002 frozen execution profile required')
    side = 'buy' if feature['prediction'] == 'up' else 'sell'
    return dict(scenario_version=1, label='R002 exploratory cost-screened momentum',
        **{k:POLICY[k] for k in ('starting_collateral','max_abs_position','max_order_notional','max_working_orders','max_loss')},
        assumptions=copy.deepcopy(profile['assumptions']), orders=[dict(id='entry',side=side,
            after_market_sequence=feature['sequence'], quantity=POLICY['target_quantity'],
            limit_price=FROZEN.limit_price(side,feature['bid'],feature['ask']))])


def verify_entry(feature, entry):
    profile = next((p for p in PROFILES if p['assumptions'] == entry['assumptions']),None)
    require(profile is not None and entry == entry_scenario(feature,profile), 'R002 entry changed frozen sizing, risk or assumptions')
    order = entry['orders'][0]
    with localcontext() as context:
        context.prec = 100
        buy = feature['prediction'] == 'up'
        price = Decimal(feature['ask' if buy else 'bid'])
        require(Decimal(order['quantity']) == Decimal('0.001') and order['side'] == ('buy' if buy else 'sell')
            and order['after_market_sequence'] == feature['sequence']
            and Decimal(order['limit_price']) == price*(Decimal('1.0002') if buy else Decimal('0.9998')),
            'R002 independent entry side, size, limit or anchor differs')
    return dict(status='verified',profile=profile['id'],feature_source_prefix_sha256=feature['source_prefix_sha256'])


def close_decision(events, feature):
    for event in events[feature['sequence']:]:
        delta = event['time']-feature['monotonic_ns']
        if delta > POLICY['first_close_max_ns']: break
        if delta >= POLICY['first_close_min_ns'] and fresh(event):
            prices(event)
            return dict(sequence=event['sequence'],monotonic_ns=event['time'],
                connection_id=event['source']['connection_id'],quote=copy.deepcopy(event['link']['quote']),
                quote_age_ns=event['time']-event['link']['quote']['monotonic_ns'],
                late_by_ns=delta-POLICY['first_close_min_ns'])
    return None


def compile_close(entry, decision, control):
    receipt = dict(status='missing_decision',decision=copy.deepcopy(decision),known_position=None,
        working_orders=None,risk_at_decision=None,prefix_records=None,prefix_sha256=None)
    plan = copy.deepcopy(entry)
    if decision is None: return plan, receipt
    rows = CYCLE.prefix_rows(*control, decision)
    position, state, orders = BOUND.native_state(rows,entry)
    settled = state['risk']['working_orders'] == 0 and all(
        o['status'] in BOUND.TERMINAL and not o['cancel_pending'] for o in orders.values())
    status = 'unresolved_entry' if not settled else 'flat_no_close' if position == 0 else 'risk_halted' if state['risk']['halted'] else 'close_compiled'
    receipt.update(status=status,known_position=FROZEN.text(position),working_orders=state['risk']['working_orders'],
        risk_at_decision=copy.deepcopy(state['risk']),prefix_records=len(rows),prefix_sha256=FROZEN.fingerprint(rows))
    if status == 'close_compiled':
        side = 'sell' if position > 0 else 'buy'
        plan['orders'].append(dict(id='close',side=side,after_market_sequence=decision['sequence'],
            quantity=FROZEN.text(position.copy_abs()),limit_price=FROZEN.limit_price(side,decision['quote']['bid'],decision['quote']['ask'])))
    return plan, receipt


def verify_close(entry, plan, events, feature, receipt, control, final):
    decision = close_decision(events,feature)
    expected, state = compile_close(entry,decision,control)
    require(plan == expected and all(receipt.get(k) == v for k,v in state.items()), 'R002 first close changed its frozen native decision')
    if decision is None:
        require(control == final, 'missing R002 close gained a different ledger')
        return dict(status='verified',decision_available=False,prefix_records=None,prefix_sha256=None)
    before, after = CYCLE.prefix_rows(*control,decision), CYCLE.prefix_rows(*final,decision,final=True)
    require(before == after, 'R002 first close changed complete control prefix')
    position, _, _ = BOUND.native_state(before,entry)
    if len(plan['orders']) == 2:
        close = plan['orders'][1]
        with localcontext() as context:
            context.prec = 100
            price = Decimal(decision['quote']['bid' if position > 0 else 'ask'])
            limit = price*(Decimal('0.9998') if position > 0 else Decimal('1.0002'))
            require(Decimal(close['quantity']) == position.copy_abs() and close['side'] == ('sell' if position > 0 else 'buy')
                and Decimal(close['limit_price']) == limit, 'R002 independent close size/side/limit differs')
    return dict(status='verified',decision_available=True,prefix_records=len(before),prefix_sha256=FROZEN.fingerprint(before))


def label(events, feature):
    result = dict(status='unavailable',reason='source_end',future=None,signed_mid_change_bps=None)
    if feature is None: return dict(result,reason='no_signal')
    last, previous = feature['monotonic_ns'], events[feature['sequence']-1]
    seen = {e['link']['quote']['exchange_time_ms'] for e in events[:feature['sequence']] if fresh(e)
        and e['source']['connection_id'] == feature['connection_id']}
    for event in events[feature['sequence']:]:
        source, now = event['source'], event['time']
        reason = None
        if source['connection_id'] != feature['connection_id']: reason = 'connection_changed'
        wall = source['local_time_ns']-previous['source']['local_time_ns']
        if wall < 0 or abs(wall-(now-previous['time'])) >= POLICY['clock_discontinuity_ns']: reason = 'clock_discontinuity'
        feed = (event['link'].get('feeds') or {}).get('bbo') or {}
        if feed.get('acknowledged') is not True or feed.get('status') != 'fresh': reason = reason or 'bbo_unusable'
        if now-last > POLICY['prediction_diagnostic']['max_bbo_gap_ns']: reason = reason or 'bbo_gap_over_1000ms'
        if now-feature['monotonic_ns'] > POLICY['prediction_diagnostic']['max_label_ns']: reason = reason or 'label_window_expired'
        if reason: return dict(result,reason=reason)
        previous = event
        if not fresh(event): continue
        timestamp = event['link']['quote']['exchange_time_ms']
        if timestamp in seen: continue
        seen.add(timestamp); last = now
        if now-feature['monotonic_ns'] >= POLICY['prediction_diagnostic']['min_label_ns']:
            future = point(event)
            change = (fraction(future['mid'])-fraction(feature['mid']))/fraction(feature['mid'])*10000
            if feature['prediction'] == 'down': change = -change
            return dict(status='labelled',reason=None,future=future,signed_mid_change_bps=ratio(change))
    return result


def summarize(cases, selected, invalid=False):
    require({(c['child'],c['profile']) for c in cases} == {(n,p['id']) for n in selected for p in PROFILES}
        and len(cases) == len(selected)*len(PROFILES), 'R002 complete frozen case membership differs')
    totals = ECONOMICS.summarize(cases)
    totals['first_close_requests'] = totals['close_requests']
    totals['retry_requests'] = sum(c['policy']['metrics']['retry_requested_quantity'] is not None for c in cases if c['status'] == 'verified')
    totals['close_requests'] += totals['retry_requests']
    for profile in totals['profiles']:
        profile['retry_requests'] = sum(c['policy']['metrics']['retry_requested_quantity'] is not None for c in cases
            if c['profile'] == profile['profile'] and c['status'] == 'verified')
    size = len(selected)//3
    thirds = [selected[:size],selected[size:2*size],selected[2*size:]]
    groups = [dict(children=group,totals=ECONOMICS.summarize([c for c in cases if c['child'] in group])) for group in thirds]
    by_id = {p['profile']:p for p in totals['profiles']}
    baseline = by_id['baseline']
    required = [baseline]+[by_id[k] for k in POLICY['development_screen']['required_stress_profiles']]
    third_baselines = [g['totals']['profiles'][0] for g in groups]
    if invalid: classification = 'invalid'
    elif any(p['unavailable'] or p['not_run'] or p['unresolved'] for p in required): classification = 'incomplete'
    elif any(p['closed'] < 30 for p in required) or any(p['closed'] < 10 for p in third_baselines): classification = 'insufficient_data'
    elif Decimal(baseline['closed_cycle_net']) <= 0 or any(Decimal(p['closed_cycle_net']) <= 0 for p in third_baselines): classification = 'no_positive_development_evidence'
    elif any(Decimal(p['closed_cycle_net']) <= 0 for p in required[1:]): classification = 'cost_sensitive_candidate'
    else: classification = 'candidate_for_separately_predeclared_new_data_confirmation_only'
    return totals, dict(classification=classification,thirds=groups,
        no_trade_reference=dict(kind='defined_idle_reference',requests=0,fees='0',position='0',trading_pnl='0'),
        actual_execution_known=False,production_gate_completed=False)
