"""Pure inspection of saved IOC timelines; never generates orders or fills."""
from bisect import bisect_left
from decimal import Decimal
import json


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def stamps(value):
    if isinstance(value, dict):
        return {key: str(item) if item is not None and key.endswith(('_ns', '_ms')) else stamps(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [stamps(item) for item in value]
    return value


def market_events(original, frames, links):
    require(len(frames) == len(links) == len(original)+1, 'market timeline length differs')
    result, previous_exchange = [], {}
    for i, (source, frame, link) in enumerate(zip(original, frames, links), 1):
        require(source['sequence'] == frame['sequence'] == link['market_sequence'] == i
                and source['monotonic_ns'] == frame['monotonic_ns'] == link['monotonic_ns']
                and source['connection_id'] == link['connection_id'] and source['local_time_ns'] == link['local_time_ns']
                and not link['generated_end'], 'market source reference differs')
        if result:
            require(source['monotonic_ns'] >= result[-1]['time'], 'source clock regressed')
        quote = link['quote']
        usable = frame['event_kind'] == 'market_observed'
        if usable:
            require(quote is not None and quote['sequence'] == i and frame['account']['mark_fresh']
                    and frame['risk']['market_status'] == 'fresh', 'native opportunity lacks a usable original quote')
        channel = None
        if source['event']['type'] == 'text_received':
            try:
                payload = json.loads(source['event']['text'])
                channel = payload.get('channel') if isinstance(payload, dict) else None
            except (ValueError, TypeError):
                pass  # Other text is not a selected-feed opportunity; native replay validated it.
        repeated = False
        if quote is not None:
            old = previous_exchange.get(source['connection_id'])
            repeated = old == quote['exchange_time_ms']
            previous_exchange[source['connection_id']] = quote['exchange_time_ms']
        result.append(dict(sequence=i, time=source['monotonic_ns'], usable=usable,
            source=source, frame=frame, link=link, channel=channel, repeated_exchange_time=repeated))
    require(links[-1]['generated_end'] and frames[-1]['complete'], 'missing generated market end')
    return result


def event_view(event, requested_at, labels=()):
    if event is None:
        return None
    source, frame, link = event['source'], event['frame'], event['link']
    state = (link.get('feeds') or {}).get('bbo')
    return stamps(dict(sequence=event['sequence'], connection_id=source['connection_id'],
        monotonic_ns=event['time'], offset_ns=event['time']-requested_at, local_time_ns=source['local_time_ns'],
        source_event=source['event']['type'], channel=event['channel'], native_event=frame['event_kind'],
        usable_opportunity=event['usable'], market_status=frame['risk']['market_status'],
        feed_state=state, quote=link['quote'], repeated_exchange_time=event['repeated_exchange_time'], labels=list(labels)))


def boundary_gap(events, times, boundary, requested_at):
    index = bisect_left(times, boundary)
    before = events[index-1] if index else None
    after = events[index] if index < len(events) else None
    return dict(before=event_view(before, requested_at), at_or_after=event_view(after, requested_at),
                recorded_gap_ns=None if before is None or after is None else str(after['time']-before['time']))


def diagnose(execution, rows, events):
    plan = execution['scenario']
    declared = plan['assumptions']
    final_orders = {order['id']: order for order in execution['paper']['orders']}
    require(len(final_orders) == len(plan['orders']), 'order inventory differs')
    result = []
    times = [event['time'] for event in events]
    for intended in plan['orders']:
        order_id = intended['id']
        final = final_orders[order_id]
        steps = [(frame, link, step) for frame, link, step in rows if step['order_id'] == order_id]
        requests = [row for row in steps if row[2]['phase'] == 'scenario_request']
        require(len(requests) == 1 and steps[0] == requests[0], 'missing or duplicated order request')
        request, request_link, request_step = requests[0]
        sequence = intended['after_market_sequence']
        event = events[sequence-1]
        require(request_link['market_sequence'] == sequence and request['event_kind'] == 'order_requested'
                and request['order']['id'] == order_id, 'request anchor differs')
        now = event['time']
        arrival = now+declared['latency_ms']*1_000_000
        expiry = arrival+declared['quote_wait_ms']*1_000_000
        require(request_step['arrival_ns'] == arrival and request_step['expiry_ns'] == expiry,
                'declared order window differs from request receipt')
        later = events[sequence:]
        first_quote = next((e for e in later if e['usable']), None)
        post_arrival = next((e for e in later if e['usable'] and e['time'] >= arrival), None)
        in_window = [e for e in later if arrival <= e['time'] < expiry]
        opportunities = [e for e in in_window if e['usable']]
        resolution = None
        if request['order']['status'] == 'rejected':
            require(len(steps) == 1 and final['status'] == 'rejected' and not final['accepted'],
                    'request-rejected order has later assumed transitions')
            classification, resolution = 'request_rejected', event
        else:
            require(request['order']['status'] == 'pending_new', 'unsupported request state')
            candidate = next((e for e in later if e['time'] >= expiry or (e['time'] >= arrival and e['usable'])), None)
            if candidate is None:
                require(len(steps) == 1 and final['status'] == 'pending_new'
                        and order_id in execution['pending_order_ids'], 'unresolved source end was changed')
                classification = 'pending_at_source_end'
            elif candidate['time'] >= expiry:
                require(len(steps) == 2 and steps[1][2]['phase'] == 'assumed_expiry_reject'
                        and steps[1][1]['market_sequence'] == candidate['sequence']
                        and steps[1][2]['arrival_ns'] == arrival and steps[1][2]['expiry_ns'] == expiry
                        and final['status'] == 'rejected' and not opportunities,
                        'expiry disagrees with recorded opportunity/observed boundary')
                resolution = candidate
                classification = 'expired_at_quote_boundary' if candidate['usable'] and candidate['time'] == expiry else 'expired_no_opportunity'
            else:
                require(steps[1][2]['phase'] == 'assumed_accept'
                        and all(link['market_sequence'] == candidate['sequence'] for _, link, _ in steps[1:])
                        and steps[1][2]['arrival_ns'] == arrival and steps[1][2]['expiry_ns'] == expiry
                        and final['status'] in ('filled', 'cancelled'), 'IOC did not resolve on its first native opportunity')
                phases = [step['phase'] for _, _, step in steps[1:]]
                filled = Decimal(final['filled_quantity'])
                if final['status'] == 'filled':
                    require(phases == ['assumed_accept', 'assumed_fill'], 'invalid full-fill lifecycle')
                    classification = 'filled'
                elif filled > 0:
                    require(phases == ['assumed_accept', 'assumed_fill', 'ioc_remainder_cancel', 'assumed_cancel_ack'],
                            'invalid partial IOC lifecycle')
                    classification = 'partial_fill_cancelled'
                else:
                    require(phases == ['assumed_accept', 'ioc_remainder_cancel', 'assumed_cancel_ack'], 'invalid no-fill IOC lifecycle')
                    classification = 'no_fill_cancelled'
                resolution = candidate
        chosen = {}
        def include(e, label):
            if e is not None:
                chosen.setdefault(e['sequence'], set()).add(label)
        include(event, 'request')
        include(first_quote, 'first_native_quote_after_request')
        include(post_arrival, 'first_native_quote_at_or_after_arrival')
        include(resolution, 'observed_resolution')
        gaps = {}
        for label, boundary in [('arrival', arrival), ('expiry', expiry)]:
            gap = boundary_gap(events, times, boundary, now)
            gaps[label] = gap
            for side in ('before', 'at_or_after'):
                if gap[side] is not None:
                    include(events[gap[side]['sequence']-1], side+'_'+label)
        reason = final.get('rejection_detail') or final.get('rejection')
        result.append(dict(order_diagnostic_version=1, order_id=order_id, side=intended['side'],
            classification=classification, historical_order_status=final['status'], rejection=reason,
            requested_quantity=intended['quantity'], filled_quantity=final['filled_quantity'],
            remaining_quantity=final['remaining_quantity'], limit_price=intended['limit_price'],
            request_sequence=sequence, request_ns=str(now), arrival_ns=str(arrival), expiry_ns=str(expiry),
            arrival_offset_ns=str(arrival-now), expiry_offset_ns=str(expiry-now),
            latency_ms=declared['latency_ms'], quote_wait_ms=declared['quote_wait_ms'],
            expiry_is_exclusive=True, request_risk=request['risk'],
            observed_resolution=event_view(resolution, now), first_native_quote_after_request=event_view(first_quote, now),
            first_native_quote_at_or_after_arrival=event_view(post_arrival, now),
            native_opportunities_in_window=len(opportunities), source_events_in_window=len(in_window),
            selected_bbo_messages_in_window=sum(e['channel'] == 'bbo' for e in in_window),
            unusable_source_states_in_window=sum(e['frame']['risk']['market_status'] != 'fresh' for e in in_window),
            repeated_exchange_times_in_window=sum(e['repeated_exchange_time'] for e in in_window),
            source_gaps=gaps, timeline=[event_view(events[n-1], now, sorted(labels)) for n, labels in sorted(chosen.items())],
            ending_position_quantity=execution['paper']['account']['position_quantity'],
            ending_pending_order_ids=execution['pending_order_ids'], component_cause='unknown'))
    return result
