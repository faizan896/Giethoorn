"""Native golden checks for exits compiled from the proxy's own causal state."""
import copy
import os
from pathlib import Path
import tempfile
import time
import unittest

try:
    from . import proxy_policy_local as RUN,test_model_compare_native as FIXTURE
except ImportError:
    import proxy_policy_local as RUN
    import test_model_compare_native as FIXTURE

BINARY=FIXTURE.BINARY


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native ledger executable required')
class CausalProxyNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def prepare(self,root=None,quotes=None,**kwargs):
        root=root or self.root
        quotes=quotes or [(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.004','0.004',101010),(2000,'99.99','100.01','0.004','0.004',102000)]
        market,source=FIXTURE.market(root,quotes=quotes,**kwargs)
        market['frames']=RUN.ORIGINAL.lines(market['directory']/'paper-updates.jsonl')
        market['links']=RUN.ORIGINAL.lines(market['directory']/'market-links.jsonl')
        return market,source

    def run_policy(self,market=None,entry=None,name='policy',**kwargs):
        if market is None:market,_=self.prepare(**kwargs)
        feature=dict(monotonic_ns=10000000,sequence=8)
        return RUN.run_case(BINARY,market,entry or FIXTURE.scenario(),feature,self.root/name,time.monotonic()+45),market

    def test_full_entry_closes_own_quantity_and_exact_hand_calculated_costs(self):
        result,_=self.run_policy();m=result['metrics']
        self.assertEqual(m['known_position_at_decision'],'0.001')
        self.assertEqual(m['close_requested_quantity'],'0.001');self.assertEqual(m['close_quantity'],'0.001')
        self.assertEqual(m['ending_position_quantity'],'0')
        self.assertEqual(m['conditional_closed_pnl'],'-0.000140000001')
        self.assertTrue(result['causal_prefix_verified']);self.assertFalse(result['control_reused'])

    def test_partial_entry_compiles_partial_close_without_reversal(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.002',100010),
            (1010,'99.99','100.01','0.004','0.004',101010),(2000,'99.99','100.01','0.004','0.004',102000)])
        m=result['metrics']
        self.assertEqual(m['entry_quantity'],'0.0005');self.assertEqual(m['close_requested_quantity'],'0.0005')
        self.assertEqual(m['close_quantity'],'0.0005');self.assertEqual(m['ending_position_quantity'],'0')
        self.assertEqual(m['conditional_closed_pnl'],'-0.0000700000005')

    def test_short_entry_compiles_a_buy_close_for_its_own_absolute_quantity(self):
        for size,quantity in (('0.004','0.001'),('0.002','0.0005')):
            with self.subTest(size=size):
                root=self.root/size;root.mkdir()
                market,_=self.prepare(root=root,quotes=[(10,'99.99','100.01',size,'0.004',100010),
                    (1010,'99.99','100.01','0.004','0.004',101010),(2000,'99.99','100.01','0.004','0.004',102000)])
                entry=FIXTURE.scenario();entry['orders'][0].update(side='sell',limit_price='99')
                result,_=self.run_policy(market=market,entry=entry,name='short-'+size)
                self.assertEqual(result['metrics']['known_position_at_decision'],'-'+quantity)
                self.assertEqual(result['metrics']['close_requested_quantity'],quantity)
                self.assertEqual(result['orders'][1]['order']['side'],'buy')
                self.assertEqual(result['metrics']['ending_position_quantity'],'0')

    def test_nonmarketable_entry_never_creates_a_close_or_zero_profit_trade(self):
        entry=FIXTURE.scenario();entry['orders'][0]['limit_price']='90'
        result,_=self.run_policy(entry=entry)
        self.assertEqual(result['metrics']['close_decision_status'],'flat_no_close')
        self.assertEqual(result['metrics']['entry_quantity'],'0');self.assertIsNone(result['metrics']['close_requested_quantity'])
        self.assertIsNone(result['metrics']['conditional_closed_pnl']);self.assertTrue(result['control_reused'])
        self.assertFalse((self.root/'policy/final').exists())

    def test_stale_arrival_rejection_does_not_create_a_close(self):
        result,_=self.run_policy(stale=100)
        self.assertEqual(result['metrics']['entry_outcome'],'no_usable_reference')
        self.assertEqual(result['metrics']['close_decision_status'],'flat_no_close')
        self.assertEqual(len(result['orders']),1)

    def test_native_entry_risk_rejection_is_preserved_without_replacement(self):
        entry=FIXTURE.scenario();entry['max_order_notional']='0.05'
        result,_=self.run_policy(entry=entry)
        self.assertEqual(result['metrics']['entry_outcome'],'request_rejected')
        self.assertEqual(result['metrics']['close_decision_status'],'flat_no_close')
        self.assertEqual(len(result['orders']),1)

    def test_no_decision_retains_entry_exposure_without_forced_close(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (500,'99.99','100.01','0.004','0.004',100500)])
        self.assertEqual(result['metrics']['close_decision_status'],'missing_decision')
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.001')
        self.assertIsNone(result['metrics']['conditional_closed_pnl'])
        self.assertFalse(result['causal_prefix_audit']['decision_available'])

    def test_source_end_before_entry_arrival_retains_pending_entry(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.004',100010)],finish=20)
        self.assertEqual(result['metrics']['pending_order_ids'],['entry'])
        self.assertEqual(result['metrics']['close_decision_status'],'missing_decision')
        self.assertEqual(result['metrics']['ending_position_quantity'],'0')
        self.assertIsNone(result['metrics']['conditional_closed_pnl'])

    def test_later_control_fill_cannot_supply_an_earlier_close_quantity(self):
        result,_=self.run_policy(entry=FIXTURE.scenario(latency_ms=1500))
        self.assertEqual(result['metrics']['close_decision_status'],'unresolved_entry')
        self.assertEqual(result['metrics']['known_position_at_decision'],'0')
        self.assertEqual(result['close_compilation']['working_orders'],1)
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.001')
        self.assertIsNone(result['metrics']['close_requested_quantity'])
        self.assertTrue(result['control_reused'])

    def test_equal_time_entry_arrival_is_included_before_close_request(self):
        result,_=self.run_policy(entry=FIXTURE.scenario(latency_ms=1000),finish=2500)
        self.assertEqual(result['metrics']['known_position_at_decision'],'0.001')
        self.assertEqual(result['metrics']['close_requested_quantity'],'0.001')
        self.assertEqual(result['metrics']['ending_position_quantity'],'0')
        self.assertTrue(result['causal_prefix_verified'])

    def test_later_equal_timestamp_source_is_excluded_from_decision_prefix(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.004','0.004',101010),(1010,'199.99','200.01','0.004','0.004',101011),
            (2000,'199.99','200.01','0.004','0.004',102000)])
        receipt=result['close_compilation']
        self.assertEqual(receipt['decision']['sequence'],9)
        self.assertEqual(receipt['decision']['quote']['bid'],'99.99')
        plan=RUN.ORIGINAL.obj(self.root/'policy/compiled-scenario.json')
        self.assertEqual(plan['orders'][1]['limit_price'],'99.970002')
        self.assertTrue(result['causal_prefix_verified'])

    def test_observed_timer_can_supply_the_unchanged_close_decision(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1000,'99.99','100.01','0.004','0.004',101000),(2000,'99.99','100.01','0.004','0.004',102000)],
            extra=[(1010,1,dict(type='feed_timer'))])
        d=result['close_compilation']['decision']
        self.assertEqual(d['monotonic_ns'],'1010000000')
        self.assertEqual(d['quote_age_ns'],'10000000')
        self.assertEqual(d['sequence'],10)

    def test_late_observed_decision_is_not_interpolated_to_horizon(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (2000,'99.99','100.01','0.004','0.004',102000)],finish=2500)
        d=result['close_compilation']['decision']
        self.assertEqual(d['monotonic_ns'],'2000000000');self.assertEqual(d['late_by_ns'],'990000000')

    def test_pending_exit_at_source_end_retains_position_and_unavailable_pnl(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.004','0.004',101010)],finish=1050)
        self.assertEqual(result['metrics']['close_outcome'],'pending_at_source_end')
        self.assertEqual(result['metrics']['pending_order_ids'],['close'])
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.001')
        self.assertIsNone(result['metrics']['conditional_closed_pnl'])

    def test_partial_exit_keeps_remaining_inventory(self):
        result,_=self.run_policy(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.001','0.004',101010),(2000,'99.99','100.01','0.001','0.004',102000)])
        self.assertEqual(result['metrics']['close_requested_quantity'],'0.001')
        self.assertEqual(result['metrics']['close_quantity'],'0.00025')
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.00075')
        self.assertIsNone(result['metrics']['conditional_closed_pnl'])

    def test_loss_halt_is_not_bypassed_to_force_the_exit(self):
        entry=FIXTURE.scenario();entry['max_loss']='0.000001'
        result,_=self.run_policy(entry=entry)
        self.assertEqual(result['metrics']['close_decision_status'],'close_compiled')
        self.assertEqual(result['metrics']['close_outcome'],'request_rejected')
        self.assertEqual(result['orders'][1]['native_final_order']['rejection'],'halted')
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.001')

    def test_future_price_and_control_position_do_not_change_compiled_prefix(self):
        a,_=self.run_policy(name='a')
        other=self.root/'other';other.mkdir()
        market,_=self.prepare(root=other,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (1010,'99.99','100.01','0.004','0.004',101010),(2000,'199.99','200.01','0.004','0.004',102000)])
        b,_=self.run_policy(market=market,name='b')
        self.assertEqual(a['close_compilation']['prefix_sha256'],b['close_compilation']['prefix_sha256'])
        self.assertEqual(RUN.ORIGINAL.obj(self.root/'a/compiled-scenario.json'),RUN.ORIGINAL.obj(self.root/'b/compiled-scenario.json'))

    def test_oversized_wrong_side_limit_or_changed_prefix_is_refused(self):
        result,_=self.run_policy()
        root=self.root/'policy';entry=RUN.ORIGINAL.obj(root/'entry-scenario.json');plan=RUN.ORIGINAL.obj(root/'compiled-scenario.json')
        receipt=RUN.ORIGINAL.obj(root/'close-compilation.json');decision=receipt['decision']
        control,final=RUN.ledger_rows(root/'control'),RUN.ledger_rows(root/'final')
        for key,value in (('quantity','0.002'),('side','buy'),('limit_price','200')):
            bad=copy.deepcopy(plan);bad['orders'][1][key]=value
            with self.assertRaises(ValueError):RUN.CORE.verify_close(entry,bad,decision,receipt,control,final)
        bad=copy.deepcopy(final);bad[2][0]['account']['fees']='1'
        with self.assertRaisesRegex(ValueError,'prefix'):RUN.CORE.verify_close(entry,plan,decision,receipt,control,bad)

    def test_repeat_keeps_exact_plans_ledgers_and_original_source(self):
        market,source=self.prepare();before=RUN.ORIGINAL.inventory(source)
        a,_=self.run_policy(market=market,name='a');b,_=self.run_policy(market=market,name='b')
        self.assertEqual(a,b)
        for name in ('compiled-scenario.json','close-compilation.json','causal-prefix-audit.json','final/paper-input.jsonl','final/paper-updates.jsonl'):
            self.assertEqual((self.root/'a'/name).read_bytes(),(self.root/'b'/name).read_bytes())
        self.assertEqual(RUN.ORIGINAL.inventory(source),before)
