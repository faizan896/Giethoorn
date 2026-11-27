"""Exact retained-cost identities and censored-window distinctions."""
import copy
from fractions import Fraction
import unittest

try:
    from . import momentum_explain_core as CORE
    from .test_momentum_core import timeline, event
except ImportError:
    import momentum_explain_core as CORE
    from test_momentum_core import timeline, event


def window_events(end=65000):
    events=timeline(end=end)
    for e in events:
        e['frame']['event_kind']='market_observed'; e['repeated_exchange_time']=False
    return events


def quote(mid):
    return dict(bid=CORE.text(Fraction(mid)-1),ask=CORE.text(Fraction(mid)+1),bid_size='10',ask_size='10')


def order(identity,side,sequence,mid,fill,quantity='0.25'):
    ref=quote(mid);touch=ref['ask' if side=='buy' else 'bid']
    q=Fraction(quantity);s=1 if side=='buy' else -1
    return dict(order=dict(id=identity,side=side,quantity=quantity,after_market_sequence=sequence,limit_price='1000'),
        native_final_order=dict(filled_quantity=quantity,status='filled',rejection=None,rejection_detail=None),
        request_monotonic_ns='0',assumed_arrival_ns='1',outcome='filled',reference_quote=ref,
        reference_eligible=True,reference_age_ns='1',marketable=True,available_quantity='2.5',
        touch_price=touch,assumed_fill_price=fill,assumed_fee='0.01',
        spread_cost=CORE.text(s*q*(Fraction(touch)-Fraction(mid))),
        slippage_cost=CORE.text(s*q*(Fraction(fill)-Fraction(touch))))


def cost_case(short=False):
    events=window_events();feature=CORE.R002.select(events,1)['feature']
    events[0]['link']['quote']=quote('110' if short else '100')
    events[1]['link']['quote']=quote('100' if short else '110')
    orders=[order('entry','sell' if short else 'buy',1,'109' if short else '101','107.9' if short else '102.1'),
        order('close','buy' if short else 'sell',2,'101' if short else '109','102.1' if short else '107.9')]
    metrics=dict(outcome='closed_under_assumptions',ending_position_quantity='0',pending_order_ids=[],
        conditional_closed_pnl='1.43',fees='0.02',close_decision_status='close_compiled',retry_decision_status='already_flat')
    return events,feature,dict(assumptions=dict(top_size_fraction='0.25')),dict(orders=orders,metrics=metrics)


class RetainedCostTests(unittest.TestCase):
    def test_hand_computed_long_and_short_identity_is_exact(self):
        for short in (False,True):
            d=CORE.explain_case(*cost_case(short))['closed_decomposition']
            self.assertEqual(d,dict(decision_midpoint_cashflow_usdc='2.5',arrival_change_usdc='0.5',
                spread_usdc='0.5',slippage_usdc='0.05',fees_usdc='0.02',closed_net_usdc='1.43',identity_verified=True))

    def test_favourable_arrival_cost_stays_negative(self):
        events,feature,scenario,value=cost_case()
        value['orders']=[order('entry','buy',1,'99','100.1'),order('close','sell',2,'111','109.9')]
        value['metrics']['conditional_closed_pnl']='2.43'
        self.assertEqual(CORE.explain_case(events,feature,scenario,value)['closed_decomposition']['arrival_change_usdc'],'-0.5')

    def test_native_net_or_per_fill_cost_tampering_fails_identity(self):
        args=cost_case();args[3]['metrics']['conditional_closed_pnl']='1.4300000000000000001'
        with self.assertRaisesRegex(ValueError,'identity differs'):CORE.explain_case(*args)
        args=cost_case();args[3]['orders'][0]['spread_cost']='0'
        with self.assertRaisesRegex(ValueError,'components differ'):CORE.explain_case(*args)

    def test_open_case_retains_fill_costs_without_cashflow_pnl(self):
        events,feature,scenario,value=cost_case();value['orders']=value['orders'][:1]
        value['metrics'].update(outcome='open_exposure',ending_position_quantity='0.25',conditional_closed_pnl=None,fees='0.01')
        d=CORE.explain_case(events,feature,scenario,value)
        self.assertIsNone(d['closed_decomposition']);self.assertEqual(d['known_fees_usdc'],'0.01')
        self.assertIsNotNone(d['orders'][0]['cost'])

    def test_open_case_with_invented_closed_pnl_is_rejected(self):
        args=cost_case();args[3]['metrics']['outcome']='open_exposure'
        with self.assertRaisesRegex(ValueError,'gained closed'):CORE.explain_case(*args)

    def test_closed_case_with_pending_order_is_rejected(self):
        args=cost_case();args[3]['metrics']['pending_order_ids']=['close']
        with self.assertRaisesRegex(ValueError,'exposure'):CORE.explain_case(*args)

    def test_partial_capacity_requires_verified_marketable_remaining_size(self):
        events,_,scenario,value=cost_case();o=value['orders'][0]
        o['order']['quantity']='0.5';o['available_quantity']='0.25';o['outcome']='partial_fill_cancelled'
        d=CORE.order_detail(events,o,scenario['assumptions'])
        self.assertEqual(d['explanation'],'remaining_assumed_capacity_limited');self.assertEqual(d['nominal_top_capacity'],'2.5')
        o['available_quantity']='0.3'
        self.assertEqual(CORE.order_detail(events,o,scenario['assumptions'])['explanation'],'partial_fill_cancelled')

    def test_no_fill_and_native_reason_stay_separate_from_closed_zero_profit(self):
        events,_,scenario,value=cost_case();o=value['orders'][0]
        o.update(assumed_fee='0',outcome='not_marketable',marketable=False)
        o['native_final_order'].update(filled_quantity='0',status='cancelled',rejection_detail='retained reason')
        d=CORE.order_detail(events,o,scenario['assumptions']);self.assertIsNone(d['cost'])
        self.assertEqual(d['explanation'],'not_marketable');self.assertEqual(d['native_rejection_detail'],'retained reason')

    def test_fraction_rendering_and_decimal_bounds_preserve_all_digits(self):
        for raw in ('-0.000000000000000000000123','123456789012345678901234567890.125','0','1e-100'):
            self.assertEqual(Fraction(CORE.text(CORE.number(raw))),Fraction(raw))
        for raw in ('NaN','Infinity','1e999999999','0e-999999999'):
            with self.assertRaises(ValueError):CORE.number(raw)
        with self.assertRaises(ValueError):CORE.text(Fraction(1,3))


class CloseWindowTests(unittest.TestCase):
    def explain(self,events):return CORE.close_window(events,dict(sequence=61,monotonic_ns=30000000000))

    def test_actual_source_eof_before_window_is_censored_not_liquidity_failure(self):
        d=self.explain(window_events(35000));self.assertEqual(d['status'],'source_ended_before_close_window')
        self.assertEqual(d['actual_source_end_ns'],'35000000000');self.assertIsNone(d['lower_boundary']['at_or_after'])

    def test_source_eof_inside_window_differs_from_fully_observed_no_quote(self):
        for end,status in [(60500,'source_ended_during_close_window_without_eligible_quote'),(61000,'no_eligible_quote_in_close_window')]:
            events=window_events(end)
            for e in events:
                if e['time']>=60000000000:e['usable']=False
            self.assertEqual(self.explain(events)['status'],status)

    def test_inclusive_start_and_end_use_original_first_eligible_quote(self):
        events=window_events();d=self.explain(events)
        self.assertEqual(d['selected_decision']['monotonic_ns'],'60000000000')
        for e in events:
            if e['time']<61000000000:e['usable']=False
        self.assertEqual(self.explain(events)['selected_decision']['monotonic_ns'],'61000000000')

    def test_stale_unacknowledged_timer_and_depth_cannot_supply_close(self):
        for kind in ('stale','unacknowledged','timer','depth'):
            events=window_events()
            for e in events:
                if e['time']<60000000000:continue
                if kind=='stale':e['link']['feeds']['bbo']['status']='stale'
                elif kind=='unacknowledged':e['link']['feeds']['bbo']['acknowledged']=False
                else:e['channel']='timer' if kind=='timer' else 'l2Book'
            d=self.explain(events);self.assertEqual(d['eligible_native_bbo_in_window'],0)
            self.assertEqual(d['status'],'no_eligible_quote_in_close_window')

    def test_new_acked_connection_may_close_without_rewriting_entry(self):
        events=window_events()
        for e in events[120:]:e['source']['connection_id']=e['link']['quote']['connection_id']=2
        self.assertEqual(self.explain(events)['selected_decision']['connection_id'],2)


if __name__=='__main__':unittest.main()
