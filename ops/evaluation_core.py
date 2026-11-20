"""Frozen cohort and exact, coverage-aware economics for independent R001 cycles."""
from decimal import Decimal, localcontext

if __package__:
    from . import proxy_policy_core as CYCLE
else:
    import proxy_policy_core as CYCLE

require = CYCLE.require
PROTOCOL_SHA256 = '04bbf2d74873df1e00208f08f30813b2a6cf8de3ad5aeec07822b69dcef2f9ce'
POLICY = dict(evaluation_policy_version=1, evaluation_id='r001-development-evaluation-001',
    partition='development', max_children=128, max_cases=768, cycles_per_child_profile=1,
    signal_policy=CYCLE.FROZEN.SIGNAL.POLICY, cycle_policy_id=CYCLE.POLICY['policy_id'],
    exploratory=True, actual_execution_known=False, portfolio_profit_evaluated=False,
    live_orders_enabled=False, full_window_verified=False)
PROFILES = CYCLE.FROZEN.PROFILES
STATUSES = ('verified', 'no_signal', 'unavailable', 'not_run')


def cohort(manifest):
    parts = manifest['candidate_partitions']
    require(parts['status'] == 'frozen_retrospective', 'frozen chronological partitions required')
    selected = parts['development']
    require(type(selected) is list and 0 < len(selected) <= POLICY['max_children']
        and all(type(n) is int and 1 <= n <= 999999 for n in selected)
        and selected == sorted(set(selected)), 'bounded ordered development cohort required; no truncation')
    require(not set(selected).intersection(parts['validation'] + parts['retrospective_test']),
        'development overlaps another partition')
    return list(selected)


def summarize(cases):
    result = dict(cases=len(cases), verified=0, no_signal=0, unavailable=0, not_run=0,
        entry_requests=0, close_requests=0, closed=0, unresolved=0, no_fills=0,
        actual_executions_known=0, profiles=[])
    profiles = {p['id']: dict(profile=p['id'], cases=0, verified=0, no_signal=0, unavailable=0, not_run=0,
        closed=0, unresolved=0, no_fills=0, positive_closed=0, negative_closed=0, zero_closed=0,
        coverage_complete=False, closed_cycle_net=None) for p in PROFILES}
    seen, values = set(), {p: [] for p in profiles}
    children = {row['child'] for row in cases}
    with localcontext() as context:
        context.prec = 100
        for row in cases:
            key = row['child'], row['profile']
            require(key not in seen and row['profile'] in profiles and row['status'] in STATUSES,
                'duplicate or unsupported evaluation case')
            seen.add(key)
            p = profiles[row['profile']]
            p['cases'] += 1
            p[row['status']] += 1
            result[row['status']] += 1
            if row['status'] != 'verified':
                require(row.get('policy') is None, 'unverified case gained policy metrics')
                continue
            policy = row['policy']
            m = policy['metrics']
            require(policy['causal_prefix_verified'] is True and m['actual_execution'] == 'unknown',
                'unverified causal policy or execution provenance')
            result['entry_requests'] += 1
            result['close_requests'] += m['close_requested_quantity'] is not None
            position = Decimal(m['ending_position_quantity'])
            require(position.is_finite(), 'nonfinite ending exposure')
            unresolved = position != 0 or bool(m['pending_order_ids'])
            net = m['conditional_closed_pnl']
            if net is not None:
                net = Decimal(net)
                require(net.is_finite() and not unresolved and m['outcome'] == 'closed_under_assumptions'
                    and Decimal(m['entry_quantity']) > 0 and m['assumed_fills'] > 0,
                    'closed P&L without a complete filled cycle')
                p['closed'] += 1
                result['closed'] += 1
                p['positive_closed' if net > 0 else 'negative_closed' if net < 0 else 'zero_closed'] += 1
                values[row['profile']].append(net)
            elif unresolved:
                p['unresolved'] += 1
                result['unresolved'] += 1
            else:
                require(m['assumed_fills'] == 0 and m['outcome'] == 'no_fills',
                    'settled filled cycle lacks closed P&L')
                p['no_fills'] += 1
                result['no_fills'] += 1
        for name, p in profiles.items():
            p['coverage_complete'] = p['cases'] == len(children) > 0 \
                and p['unavailable'] == p['not_run'] == p['unresolved'] == 0
            if p['coverage_complete'] and values[name]:
                p['closed_cycle_net'] = str(sum(values[name], Decimal(0)))
            result['profiles'].append(p)
    return result
