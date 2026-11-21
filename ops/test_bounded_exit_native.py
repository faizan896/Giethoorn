"""Native golden cases for a single causal residual close, never a flatten loop."""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from . import bounded_exit_local as RUN, test_model_compare_native as FIXTURE
except ImportError:
    import bounded_exit_local as RUN
    import test_model_compare_native as FIXTURE

BINARY = FIXTURE.BINARY


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native executable required')
class BoundedExitNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def prepare(self,quotes=None,root=None,**kwargs):
        quotes=quotes or [(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'99.99','100.01','0.004','0.004',101200),
            (2000,'99.99','100.01','0.004','0.004',102000)]
        market,source=FIXTURE.market(root or self.root,quotes=quotes,**kwargs)
        market['frames']=RUN.ORIGINAL.lines(market['directory']/'paper-updates.jsonl')
        market['links']=RUN.ORIGINAL.lines(market['directory']/'market-links.jsonl')
        return market,source

    def run_case(self,market=None,entry=None,name='case',**kwargs):
        if market is None:market,_=self.prepare(**kwargs)
        feature=dict(monotonic_ns=10000000,sequence=8)
        value=RUN.run_case(BINARY,market,entry or FIXTURE.scenario(),feature,self.root/name,time.monotonic()+60)
        return value,market

    def test_partial_first_close_retries_only_residual_with_exact_native_costs(self):
        value,_=self.run_case();m=value['metrics']
        self.assertEqual(m['close_quantity'],'0.00025');self.assertEqual(m['retry_known_position'],'0.00075')
        self.assertEqual(m['retry_requested_quantity'],'0.00075');self.assertEqual(m['retry_quantity'],'0.00075')
        self.assertEqual(m['ending_position_quantity'],'0');self.assertEqual(m['total_close_quantity'],'0.00100')
        self.assertEqual(m['conditional_closed_pnl'],'-0.000140000001')
        self.assertEqual(m['fees'],'0.000100000001000')
        self.assertEqual(len(value['orders']),3);self.assertTrue(value['retry_prefix_verified'])

    def test_newly_closed_control_has_no_fabricated_return_improvement(self):
        value,_=self.run_case()
        cases=[dict(case_id='synthetic',child=1,profile='baseline',status='verified',
            policy=RUN.compact(value),control=RUN.EVAL.compact(value['single_close_control']))]
        current,old,pairs=RUN.CORE.summarize(cases)
        self.assertEqual(current['retry_requests'],1);self.assertEqual(current['close_requests'],2)
        self.assertIsNone(old['profiles'][0]['closed_cycle_net'])
        self.assertEqual(current['profiles'][0]['closed_cycle_net'],'-0.000140000001')
        self.assertEqual(pairs[0]['transition'],'unresolved_to_closed')
        self.assertIsNone(pairs[0]['conditional_closed_net_delta'])
        self.assertEqual(Decimal(pairs[0]['fee_delta']),Decimal('0.000037492500375'))

    def test_full_first_close_reuses_control_without_extra_request(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.004','0.004',101010),(1200,'99.99','100.01','0.004','0.004',101200)])
        self.assertEqual(value['retry_compilation']['status'],'already_flat')
        self.assertTrue(value['control_reused']);self.assertEqual(len(value['orders']),2)
        self.assertIsNone(value['metrics']['retry_requested_quantity'])
        self.assertFalse((self.root/'case/retry').exists())

    def test_nonmarketable_entry_has_no_close_or_zero_profit_trade(self):
        entry=FIXTURE.scenario();entry['orders'][0]['limit_price']='90'
        value,_=self.run_case(entry=entry)
        self.assertEqual(value['retry_compilation']['status'],'no_first_close')
        self.assertEqual(len(value['orders']),1);self.assertEqual(value['metrics']['ending_position_quantity'],'0')
        self.assertIsNone(value['metrics']['conditional_closed_pnl'])

    def test_missing_first_decision_does_not_invent_a_later_close(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (500,'99.99','100.01','0.004','0.004',100500)])
        self.assertEqual(value['retry_compilation']['status'],'no_first_close')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.001')
        self.assertEqual(len(value['orders']),1)

    def test_future_entry_fill_cannot_create_a_close_absent_from_the_control(self):
        value,_=self.run_case(entry=FIXTURE.scenario(latency_ms=1500))
        self.assertEqual(value['retry_compilation']['status'],'no_first_close')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.001')
        self.assertIsNone(value['metrics']['retry_requested_quantity'])

    def test_pending_first_close_never_overlaps_retry(self):
        value,_=self.run_case(entry=FIXTURE.scenario(latency_ms=1000),quotes=[
            (10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1800,'99.99','100.01','0.004','0.004',101800)],finish=1850)
        self.assertEqual(value['retry_compilation']['status'],'first_close_unresolved')
        self.assertEqual(value['metrics']['pending_order_ids'],['close'])
        self.assertEqual(len(value['orders']),2)

    def test_no_observed_retry_quote_preserves_residual_inventory(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010)],finish=1300)
        self.assertEqual(value['retry_compilation']['status'],'no_retry_quote')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.00075')
        self.assertIsNone(value['metrics']['conditional_closed_pnl'])

    def test_timer_is_not_a_new_retry_quote(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1300,'99.99','100.01','0.004','0.004',101300),
            (2000,'99.99','100.01','0.004','0.004',102000)],extra=[(1200,1,dict(type='feed_timer'))])
        self.assertEqual(value['retry_compilation']['decision']['monotonic_ns'],'1300000000')

    def test_empty_bbo_is_skipped_before_first_usable_new_quote(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,None,None,'0','0',101200),(1300,'99.99','100.01','0.004','0.004',101300),
            (2000,'99.99','100.01','0.004','0.004',102000)])
        self.assertEqual(value['retry_compilation']['decision']['monotonic_ns'],'1300000000')

    def test_partial_entry_caps_retry_at_its_actual_filled_residual(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.002',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'99.99','100.01','0.004','0.004',101200),
            (2000,'99.99','100.01','0.004','0.004',102000)])
        self.assertEqual(value['metrics']['entry_quantity'],'0.0005')
        self.assertEqual(value['metrics']['retry_requested_quantity'],'0.00025')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0')
        self.assertEqual(value['metrics']['conditional_closed_pnl'],'-0.0000700000005')

    def test_short_partial_close_retries_a_buy_without_reversing_inventory(self):
        entry=FIXTURE.scenario();entry['orders'][0].update(side='sell',limit_price='99')
        value,_=self.run_case(entry=entry,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.004','0.001',101010),
            (1200,'99.99','100.01','0.004','0.004',101200),
            (2000,'99.99','100.01','0.004','0.004',102000)])
        self.assertEqual(value['metrics']['retry_known_position'],'-0.00075')
        self.assertEqual(value['metrics']['retry_requested_quantity'],'0.00075')
        self.assertEqual(value['orders'][-1]['order']['side'],'buy')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0')

    def test_reconnect_requires_a_fresh_book_on_the_new_acknowledged_connection(self):
        initial=[json.loads(line) for line in (FIXTURE.PROJECT/'fixtures/hyperliquid-combined-v2.jsonl').read_text().splitlines()][:7]
        extra=[(1150,1,dict(type='connection_closed',reason='synthetic reconnect')),
            (1200,2,dict(type='connection_attempt',endpoint='wss://synthetic.invalid/ws')),
            (1201,2,dict(type='connection_opened'))]
        for n,row in enumerate(initial[3:],1202):extra.append((n,2,row['event']))
        payload=dict(channel='bbo',data=dict(coin='BTC',time=101250,
            bbo=[dict(px='99.99',sz='0.004',n=1),dict(px='100.01',sz='0.004',n=1)]))
        extra.append((1250,2,dict(type='text_received',text=json.dumps(payload))))
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010)],extra=extra,finish=1800,end_connection=2)
        self.assertEqual(value['retry_compilation']['decision']['connection_id'],2)
        self.assertEqual(value['retry_compilation']['decision']['monotonic_ns'],'1250000000')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0')

    def test_retry_reference_can_expire_after_its_fresh_decision(self):
        value,_=self.run_case(entry=FIXTURE.scenario(latency_ms=250),stale=200,quotes=[
            (10,'99.99','100.01','0.004','0.004',100010),
            (200,'99.99','100.01','0.004','0.004',100200),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'99.99','100.01','0.001','0.004',101200),
            (1400,'99.99','100.01','0.004','0.004',101400),
            (2000,'99.99','100.01','0.004','0.004',102000)])
        self.assertEqual(value['retry_compilation']['decision']['monotonic_ns'],'1400000000')
        self.assertEqual(value['metrics']['retry_outcome'],'no_usable_reference')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.00075')

    def test_no_first_close_audit_refuses_a_different_reused_ledger(self):
        entry=FIXTURE.scenario();entry['orders'][0]['limit_price']='90'
        value,market=self.run_case(entry=entry);folder=self.root/'case'
        old=RUN.ORIGINAL.obj(folder/'single-close/compiled-scenario.json')
        receipt=RUN.ORIGINAL.obj(folder/'retry-compilation.json')
        control=RUN.CYCLE.ledger_rows(folder/'single-close/control');changed=copy.deepcopy(control)
        changed[2][0]['account']['fees']='1'
        with self.assertRaises(ValueError):RUN.CORE.verify_retry(old,old,market['events'],receipt,control,changed)

    def test_equal_time_first_close_completion_is_known_before_retry_request(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1110,'99.99','100.01','0.001','0.004',101110),
            (2000,'99.99','100.01','0.004','0.004',102000)])
        self.assertEqual(value['retry_compilation']['decision']['monotonic_ns'],'1110000000')
        self.assertEqual(value['retry_compilation']['first_close_state']['status'],'cancelled')
        self.assertEqual(value['metrics']['retry_requested_quantity'],'0.00075')
        self.assertEqual(value['metrics']['retry_outcome'],'no_remaining_capacity')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.00075')

    def test_later_source_at_same_timestamp_cannot_change_retry_limit(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1110,'99.99','100.01','0.001','0.004',101110),
            (1110,'199.99','200.01','0.004','0.004',101111),
            (2000,'199.99','200.01','0.004','0.004',102000)])
        receipt=value['retry_compilation'];retry=value['orders'][-1]['order']
        self.assertEqual(receipt['decision']['quote']['bid'],'99.99')
        self.assertEqual(retry['limit_price'],'99.970002');self.assertEqual(receipt['decision']['sequence'],10)

    def test_future_control_cancel_cannot_be_used_before_its_action_time(self):
        entry=FIXTURE.scenario();entry['orders'][0].update(side='sell',limit_price='99')
        value,_=self.run_case(entry=entry,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.004','0.004',101010),
            (1050,'109.99','110.01','0.004','0.004',101050),
            (1200,'109.99','110.01','0.004','0.004',101200),
            (2000,'109.99','110.01','0.004','0.004',102000)])
        self.assertEqual(value['single_close_control']['metrics']['close_outcome'],'not_marketable')
        self.assertEqual(value['retry_compilation']['decision']['monotonic_ns'],'1200000000')
        self.assertEqual(value['metrics']['retry_known_position'],'-0.001')
        self.assertEqual(value['orders'][-1]['order']['side'],'buy')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0')

    def test_partial_retry_retains_exposure_and_never_adds_a_fourth_request(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'99.99','100.01','0.001','0.004',101200),
            (2000,'99.99','100.01','0.004','0.004',102000)])
        self.assertEqual(value['metrics']['retry_quantity'],'0.00025')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.0005')
        self.assertIsNone(value['metrics']['conditional_closed_pnl']);self.assertEqual(len(value['orders']),3)

    def test_retry_arrival_beyond_eof_stays_pending(self):
        value,_=self.run_case(finish=1250,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'99.99','100.01','0.004','0.004',101200)])
        self.assertEqual(value['metrics']['retry_outcome'],'pending_at_source_end')
        self.assertEqual(value['metrics']['pending_order_ids'],['close-retry'])
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.00075')

    def test_risk_halt_stops_retry_without_bypassing_native_guard(self):
        entry=FIXTURE.scenario();entry['max_loss']='0.000001'
        value,_=self.run_case(entry=entry)
        self.assertEqual(value['retry_compilation']['status'],'risk_halted')
        self.assertEqual(value['single_close_control']['metrics']['close_outcome'],'request_rejected')
        self.assertEqual(len(value['orders']),2);self.assertEqual(value['metrics']['ending_position_quantity'],'0.001')

    def test_extra_order_is_still_subject_to_native_notional_rejection(self):
        entry=FIXTURE.scenario();entry['max_order_notional']='0.101'
        value,_=self.run_case(entry=entry,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'999.99','1000.01','0.004','0.004',101200),
            (2000,'999.99','1000.01','0.004','0.004',102000)])
        self.assertEqual(value['metrics']['retry_outcome'],'request_rejected')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.00075')
        self.assertEqual(len(value['orders']),3)

    def test_book_becoming_empty_after_candidate_can_reject_the_retry_reference(self):
        value,_=self.run_case(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'99.99','100.01','0.004','0.004',101200),
            (1250,None,None,'0','0',101250),(2000,'99.99','100.01','0.004','0.004',102000)])
        self.assertEqual(value['metrics']['retry_outcome'],'no_usable_reference')
        self.assertEqual(value['metrics']['ending_position_quantity'],'0.00075')

    def test_future_price_does_not_change_retry_request_or_prefix(self):
        a,_=self.run_case(name='a');other=self.root/'other';other.mkdir()
        market,_=self.prepare(root=other,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),
            (1200,'99.99','100.01','0.004','0.004',101200),
            (2000,'199.99','200.01','0.004','0.004',102000)])
        b,_=self.run_case(market=market,name='b')
        self.assertEqual(a['orders'][-1]['order'],b['orders'][-1]['order'])
        self.assertEqual(a['retry_prefix_audit'],b['retry_prefix_audit'])

    def test_zero_latency_retains_exact_control_prefix(self):
        value,_=self.run_case(entry=FIXTURE.scenario(latency_ms=0))
        self.assertTrue(value['retry_prefix_verified']);self.assertEqual(value['metrics']['ending_position_quantity'],'0')

    def test_tampered_retry_quantity_side_limit_anchor_receipt_or_prefix_is_refused(self):
        value,market=self.run_case();folder=self.root/'case'
        old=RUN.ORIGINAL.obj(folder/'single-close/compiled-scenario.json')
        plan=RUN.ORIGINAL.obj(folder/'compiled-scenario.json');receipt=RUN.ORIGINAL.obj(folder/'retry-compilation.json')
        control=RUN.CYCLE.ledger_rows(folder/'single-close/final');final=RUN.CYCLE.ledger_rows(folder/'retry')
        for key,new in (('quantity','0.001'),('side','buy'),('limit_price','1'),('after_market_sequence',11)):
            changed=copy.deepcopy(plan);changed['orders'][-1][key]=new
            with self.assertRaises(ValueError):RUN.CORE.verify_retry(old,changed,market['events'],receipt,control,final)
        changed=copy.deepcopy(receipt);changed['known_position']='0.001'
        with self.assertRaises(ValueError):RUN.CORE.verify_retry(old,plan,market['events'],changed,control,final)
        changed=copy.deepcopy(final);changed[2][0]['account']['fees']='1'
        with self.assertRaisesRegex(ValueError,'prefix'):RUN.CORE.verify_retry(old,plan,market['events'],receipt,control,changed)

    def test_repeated_plans_ledgers_and_control_results_are_exact_and_source_unchanged(self):
        market,source=self.prepare();before=RUN.ORIGINAL.inventory(source)
        a,_=self.run_case(market=market,name='a');b,_=self.run_case(market=market,name='b')
        self.assertEqual(a,b);self.assertEqual(before,RUN.ORIGINAL.inventory(source))
        for name in ('compiled-scenario.json','retry-compilation.json','retry/paper-input.jsonl',
                     'retry/comparison-links.jsonl','retry/paper-updates.jsonl'):
            self.assertEqual((self.root/'a'/name).read_bytes(),(self.root/'b'/name).read_bytes())

    def test_mutated_retained_control_is_rejected_even_if_memory_prefix_still_matches(self):
        original=RUN.MODEL.proxy
        def mutate(*args,**kwargs):
            value=original(*args,**kwargs)
            if args[3].name=='retry':
                path=self.root/'case/single-close/final/paper-input.jsonl'
                path.write_bytes(path.read_bytes()+b' ')
            return value
        with patch.object(RUN.MODEL,'proxy',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'control artifacts changed'):self.run_case()
