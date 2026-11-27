"""Pure explanations of retained R002 windows, assumed fills and exact cashflows."""
from fractions import Fraction
from decimal import Decimal

if __package__:
    from . import momentum_core as R002, expiry_core as TIMELINE
else:
    import momentum_core as R002
    import expiry_core as TIMELINE

require = R002.require
POLICY = dict(diagnostic_version=1, diagnostic_id='r002-retained-diagnostic-001',
    experiment_id=R002.POLICY['experiment_id'], read_only=True,
    actual_execution_known=False, live_orders_enabled=False,
    portfolio_profit_evaluated=False, full_window_verified=False)


def number(value):
    require(type(value) is str and len(value) <= 512, 'bounded exact decimal string required')
    decimal = Decimal(value)
    require(decimal.is_finite() and abs(decimal.adjusted()) <= 512 and abs(decimal.as_tuple().exponent) <= 1024,
        'nonfinite or oversized exact decimal')
    return Fraction(decimal)


def text(value):
    """Render a terminating rational without rounding or floating point."""
    value = Fraction(value)
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0: denominator //= 2; twos += 1
    while denominator % 5 == 0: denominator //= 5; fives += 1
    require(denominator == 1 and max(twos, fives) <= 2048, 'nonterminating or oversized cost decimal')
    digits = max(twos, fives)
    scaled = abs(value.numerator) * 2**(digits-twos) * 5**(digits-fives)
    raw = str(scaled).zfill(digits+1)
    raw = (raw[:-digits]+'.'+raw[-digits:]).rstrip('0').rstrip('.') if digits else raw
    return ('-' if value < 0 else '')+raw


def midpoint(quote):
    require(quote is not None, 'filled order lacks original decision/reference quote')
    bid, ask = number(quote['bid']), number(quote['ask'])
    require(0 < bid < ask, 'invalid retained bid/ask')
    return (bid+ask)/2


def close_window(events, feature):
    require(events and feature is not None, 'selected retained source required')
    anchor = int(feature['monotonic_ns'])
    lower = anchor+R002.POLICY['first_close_min_ns']
    upper = anchor+R002.POLICY['first_close_max_ns']
    times = [event['time'] for event in events]
    inside = [event for event in events if lower <= event['time'] <= upper]
    eligible = [event for event in inside if R002.fresh(event)]
    end = events[-1]['time']
    status = 'eligible_close_quote_observed' if eligible else \
        'source_ended_before_close_window' if end < lower else \
        'source_ended_during_close_window_without_eligible_quote' if end < upper else \
        'no_eligible_quote_in_close_window'
    return dict(status=status, feature_monotonic_ns=str(anchor), window_start_ns=str(lower), window_end_ns=str(upper),
        actual_source_end_ns=str(end), observed_through_window_end=end >= upper,
        bbo_messages_in_window=sum(e['channel'] == 'bbo' for e in inside),
        eligible_native_bbo_in_window=len(eligible),
        selected_decision=TIMELINE.stamps(R002.close_decision(events, feature)),
        source_end=TIMELINE.event_view(events[-1], anchor),
        source_end_reason=events[-1]['source']['event'].get('reason'),
        lower_boundary=TIMELINE.boundary_gap(events,times,lower,anchor),
        upper_boundary=TIMELINE.boundary_gap(events,times,upper,anchor))


def order_detail(events, decision, assumptions):
    order = decision['order']; final = decision['native_final_order']
    anchor = events[order['after_market_sequence']-1]
    requested, filled = number(order['quantity']), number(final['filled_quantity'])
    require(0 <= filled <= requested, 'retained order quantity differs')
    reference = decision.get('reference_quote')
    side = order['side']; require(side in ('buy','sell'), 'unsupported order side')
    top = None if reference is None else number(reference['ask_size' if side == 'buy' else 'bid_size'])
    available = decision.get('available_quantity')
    outcome = decision['outcome']
    capacity_limited = filled > 0 and filled < requested and decision.get('marketable') is True \
        and available is not None and filled == number(available)
    result = dict(id=order['id'],side=side,requested_quantity=order['quantity'],filled_quantity=final['filled_quantity'],
        outcome=outcome,explanation='remaining_assumed_capacity_limited' if capacity_limited else outcome,
        request_monotonic_ns=decision['request_monotonic_ns'],assumed_arrival_ns=decision['assumed_arrival_ns'],
        request_source_sequence=order['after_market_sequence'],decision_quote=TIMELINE.stamps(anchor['link']['quote']),
        reference_quote=reference,reference_eligible=decision.get('reference_eligible'),reference_age_ns=decision.get('reference_age_ns'),
        limit_price=order['limit_price'],marketable=decision.get('marketable'),
        touch_price=decision.get('touch_price'),assumed_fill_price=decision.get('assumed_fill_price'),
        top_size=None if top is None else text(top),top_size_fraction=assumptions['top_size_fraction'],
        nominal_top_capacity=None if top is None else text(top*number(assumptions['top_size_fraction'])),
        remaining_shared_capacity=available,native_status=final['status'],
        native_rejection=final.get('rejection'),native_rejection_detail=final.get('rejection_detail'),cost=None)
    if not filled:
        require(number(decision.get('assumed_fee') or '0') == 0, 'unfilled order gained fees')
        return result
    sign = 1 if side == 'buy' else -1
    d, m, t, f = midpoint(anchor['link']['quote']), midpoint(reference), number(decision['touch_price']), number(decision['assumed_fill_price'])
    cost = dict(decision_midpoint=text(d),arrival_midpoint=text(m),
        decision_midpoint_cashflow_usdc=text(-sign*filled*d),
        arrival_change_usdc=text(sign*filled*(m-d)),spread_usdc=text(sign*filled*(t-m)),
        slippage_usdc=text(sign*filled*(f-t)),fees_usdc=decision['assumed_fee'])
    require(number(cost['spread_usdc']) == number(decision['spread_cost'])
        and number(cost['slippage_usdc']) == number(decision['slippage_cost']), 'retained fill cost components differ')
    result['cost'] = cost
    return result


def explain_case(events, feature, scenario, value):
    metrics = value['metrics']
    orders = [order_detail(events,o,scenario['assumptions']) for o in value['orders']]
    fills = [o for o in orders if o['cost'] is not None]
    fees = sum((number(o['cost']['fees_usdc']) for o in fills), Fraction(0))
    require(fees == number(metrics['fees']), 'diagnostic fees differ from native ledger')
    decomposition = None
    if metrics['outcome'] == 'closed_under_assumptions':
        require(number(metrics['ending_position_quantity']) == 0 and not metrics['pending_order_ids'] and fills,
            'closed diagnostic has exposure or no fills')
        keys = ('decision_midpoint_cashflow_usdc','arrival_change_usdc','spread_usdc','slippage_usdc','fees_usdc')
        sums = {key:sum((number(o['cost'][key]) for o in fills),Fraction(0)) for key in keys}
        net = sums[keys[0]]-sum((sums[k] for k in keys[1:]),Fraction(0))
        require(net == number(metrics['conditional_closed_pnl']), 'exact price/cost identity differs from native closed net')
        decomposition = {key:text(amount) for key,amount in sums.items()}
        decomposition.update(closed_net_usdc=metrics['conditional_closed_pnl'],identity_verified=True)
    else:
        require(metrics['conditional_closed_pnl'] is None, 'open/no-fill case gained closed P&L')
    return dict(outcome=metrics['outcome'],ending_position_quantity=metrics['ending_position_quantity'],
        pending_order_ids=metrics['pending_order_ids'],known_fees_usdc=metrics['fees'],
        first_close_status=metrics['close_decision_status'],retry_status=metrics['retry_decision_status'],
        close_window=close_window(events,feature),orders=orders,closed_decomposition=decomposition)
