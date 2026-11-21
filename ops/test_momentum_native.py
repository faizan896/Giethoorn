"""Native R002 golden cases; original engine and source producers stay fixed."""
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
    from . import momentum_local as RUN, test_model_compare_native as FIXTURE
except ImportError:
    import momentum_local as RUN
    import test_model_compare_native as FIXTURE

BINARY=FIXTURE.BINARY


def quotes(end=65010,direction='up',future=None,partial=False,scale='100'):
    base=Decimal(scale);current=base*(Decimal('1.002') if direction=='up' else Decimal('0.998'))
    rows=[]
    for t in range(10,end+1,500):
        mid=base if t<30010 else current if future is None or t<60010 else Decimal(future)
        bid_size='0.001' if partial and t==60010 else '0.004'
        rows.append((t,str(mid-Decimal('0.01')),str(mid+Decimal('0.01')),bid_size,'0.004',100000+t))
    return rows


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native executable required')
class MomentumNativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def prepare(self,**kwargs):
        market,source=FIXTURE.market(self.root,quotes=kwargs.pop('quotes',None) or quotes(),**kwargs)
        feature=RUN.CORE.select(market['events'],1)['feature'];self.assertIsNotNone(feature)
        return market,source,feature

    def run_case(self,market=None,feature=None,name='case',profile=0,**kwargs):
        if market is None:market,_,feature=self.prepare(**kwargs)
        entry=RUN.CORE.entry_scenario(feature,RUN.CORE.PROFILES[profile])
        value=RUN.run_case(BINARY,market,entry,feature,self.root/name,time.monotonic()+60)
        return value,market,feature

    def test_full_close_at_thirty_seconds_has_hand_computed_exact_costs(self):
        value,_,f=self.run_case();m=value['metrics']
        self.assertEqual(value['close_compilation']['decision']['monotonic_ns'],str(f['monotonic_ns']+30000000000))
        self.assertEqual(m['entry_quantity'],'0.001');self.assertEqual(m['close_quantity'],'0.001')
        self.assertEqual(m['conditional_closed_pnl'],'-0.000140240001')
        self.assertEqual(m['fees'],'0.0001002000010');self.assertEqual(m['ending_position_quantity'],'0')
        self.assertEqual(len(value['orders']),2);self.assertTrue(value['causal_prefix_verified'])

    def test_partial_first_close_adds_only_residual_without_double_charging_screen(self):
        value,_,_=self.run_case(quotes=quotes(partial=True));m=value['metrics']
        self.assertEqual(m['close_quantity'],'0.00025');self.assertEqual(m['retry_requested_quantity'],'0.00075')
        self.assertEqual(m['retry_quantity'],'0.00075');self.assertEqual(m['ending_position_quantity'],'0')
        self.assertEqual(m['conditional_closed_pnl'],'-0.000140240001')
        self.assertEqual(m['fees'],'0.000100200001000');self.assertEqual(len(value['orders']),3)

    def test_short_entry_closes_its_own_position_with_exact_native_accounting(self):
        value,_,_=self.run_case(quotes=quotes(direction='down'));m=value['metrics']
        self.assertEqual(value['orders'][0]['order']['side'],'sell');self.assertEqual(value['orders'][1]['order']['side'],'buy')
        self.assertEqual(m['conditional_closed_pnl'],'-0.000139760001');self.assertEqual(m['ending_position_quantity'],'0')

    def test_future_change_can_change_net_without_changing_selected_entry(self):
        first,market,f=self.run_case(name='flat')
        other=self.root/'other';other.mkdir();second_market,_=FIXTURE.market(other,quotes=quotes(future='100.5'))
        f2=RUN.CORE.select(second_market['events'],1)['feature'];self.assertEqual(f,f2)
        second,_,_=self.run_case(market=second_market,feature=f2,name='moved')
        self.assertEqual(first['orders'][0],second['orders'][0])
        self.assertEqual(second['metrics']['conditional_closed_pnl'],'0.000159580014')

    def test_source_end_before_close_retains_exposure_and_missing_label(self):
        value,market,f=self.run_case(quotes=quotes(end=35010));m=value['metrics']
        self.assertEqual(m['close_decision_status'],'missing_decision');self.assertEqual(m['ending_position_quantity'],'0.001')
        self.assertIsNone(m['conditional_closed_pnl']);self.assertEqual(len(value['orders']),1)
        self.assertEqual(RUN.CORE.label(market['events'],f)['status'],'unavailable')

    def test_source_end_before_entry_arrival_keeps_pending_entry_unknown(self):
        value,_,_=self.run_case(quotes=quotes(end=30010),finish=30050);m=value['metrics']
        self.assertEqual(m['pending_order_ids'],['entry']);self.assertEqual(m['ending_position_quantity'],'0')
        self.assertIsNone(m['conditional_closed_pnl']);self.assertEqual(len(value['orders']),1)

    def test_first_close_arrival_after_source_end_is_pending_without_overlapping_retry(self):
        value,_,_=self.run_case(quotes=quotes(end=60010),finish=60050);m=value['metrics']
        self.assertEqual(m['pending_order_ids'],['close']);self.assertEqual(m['retry_decision_status'],'first_close_unresolved')
        self.assertIsNone(m['retry_requested_quantity']);self.assertEqual(len(value['orders']),2)

    def test_partial_extra_close_retains_inventory_without_fourth_order(self):
        q=quotes(partial=True);q=[(t,b,a,'0.001' if t>=60010 else bs,ask,ex) for t,b,a,bs,ask,ex in q]
        value,_,_=self.run_case(quotes=q);m=value['metrics']
        self.assertEqual(m['retry_quantity'],'0.00025');self.assertEqual(m['ending_position_quantity'],'0.0005')
        self.assertIsNone(m['conditional_closed_pnl']);self.assertEqual(len(value['orders']),3)

    def test_native_notional_cap_rejects_instead_of_resizing_entry(self):
        value,_,_=self.run_case(quotes=quotes(scale='200000'));m=value['metrics']
        self.assertEqual(m['entry_outcome'],'request_rejected');self.assertEqual(m['entry_quantity'],'0')
        self.assertIsNone(m['conditional_closed_pnl']);self.assertEqual(len(value['orders']),1)

    def test_native_loss_halt_prevents_first_and_additional_requests(self):
        value,_,_=self.run_case(quotes=quotes(scale='65000',future='40000'));m=value['metrics']
        self.assertEqual(m['close_decision_status'],'risk_halted');self.assertEqual(len(value['orders']),1)
        self.assertEqual(m['ending_position_quantity'],'0.001');self.assertIsNone(m['conditional_closed_pnl'])

    def test_tampered_first_close_side_size_limit_anchor_or_receipt_is_refused(self):
        value,market,f=self.run_case();folder=self.root/'case'
        entry=RUN.ORIGINAL.obj(folder/'entry-scenario.json');plan=RUN.ORIGINAL.obj(folder/'first-close-scenario.json')
        receipt=RUN.ORIGINAL.obj(folder/'first-close-compilation.json')
        control=RUN.CYCLE.ledger_rows(folder/'entry-control');final=RUN.CYCLE.ledger_rows(folder/'first-close')
        for key,v in [('quantity','0.002'),('side','buy'),('limit_price','200'),('after_market_sequence',8)]:
            changed=copy.deepcopy(plan);changed['orders'][1][key]=v
            with self.assertRaises(ValueError):RUN.CORE.verify_close(entry,changed,market['events'],f,receipt,control,final)
        changed=copy.deepcopy(receipt);changed['known_position']='0.002'
        with self.assertRaises(ValueError):RUN.CORE.verify_close(entry,plan,market['events'],f,changed,control,final)

    def test_changed_retained_control_is_refused_after_additional_replay(self):
        market,_,f=self.prepare(quotes=quotes(partial=True));proxy=RUN.MODEL.proxy
        def corrupt(*args,**kwargs):
            value=proxy(*args,**kwargs)
            if args[3].name=='retry':
                target=args[3].parent/'first-close/paper-input.jsonl';target.write_bytes(target.read_bytes()+b'\n')
            return value
        with patch.object(RUN.MODEL,'proxy',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'control artifacts changed'):self.run_case(market=market,feature=f)

    def test_same_source_repeats_exact_plans_results_and_ledgers(self):
        market,source,f=self.prepare(quotes=quotes(partial=True));before=RUN.REVIEW.inventory(source)
        a,_,_=self.run_case(market=market,feature=f,name='a');b,_,_=self.run_case(market=market,feature=f,name='b')
        self.assertEqual(a,b);self.assertEqual(RUN.REVIEW.inventory(source),before)
        for name in ['compiled-scenario.json','retry-compilation.json','retry/paper-input.jsonl','retry/paper-updates.jsonl']:
            self.assertEqual((self.root/'a'/name).read_bytes(),(self.root/'b'/name).read_bytes())

    def test_fresh_source_loader_verifies_native_normalization_and_saves_before_label(self):
        _,source,_=self.prepare(quotes=quotes(end=35010))
        inventory={f'supervision/run-000001/session/{p.name}':dict(bytes=p.stat().st_size,sha256=RUN.REVIEW.digest(p)) for p in source.iterdir()}
        label=RUN.CORE.label
        def guarded(events,feature):
            self.assertTrue((self.root/'fresh/selected-feature.json').is_file())
            self.assertTrue((self.root/'fresh/selection-audit.json').is_file())
            return label(events,feature)
        with patch.object(RUN.CORE,'label',side_effect=guarded):
            market=RUN.load_market(BINARY,source,self.root/'fresh',1,inventory,'synthetic_fixture',time.monotonic()+60)
        self.assertIsNotNone(market['feature']);self.assertEqual(market['label']['status'],'unavailable')
        self.assertTrue((self.root/'fresh/normalization-audit.json').is_file())

    def test_source_loader_rejects_changed_source_identity(self):
        _,source,_=self.prepare()
        inventory={f'supervision/run-000001/session/{p.name}':dict(bytes=p.stat().st_size,sha256='0'*64) for p in source.iterdir()}
        with self.assertRaisesRegex(ValueError,'source differs'):
            RUN.load_market(BINARY,source,self.root/'fresh',1,inventory,'synthetic_fixture',time.monotonic()+60)

    def test_native_source_rejects_zero_size_before_feature_admission(self):
        q=quotes(end=35010);q=[(t,b,a,'0' if t==20010 else bs,ask,ex) for t,b,a,bs,ask,ex in q]
        with self.assertRaisesRegex(ValueError,'invalid size'):
            FIXTURE.market(self.root,quotes=q)

    def test_all_six_profiles_keep_same_entry_feature_with_independent_fill_costs(self):
        market,_,f=self.prepare();values=[]
        for i in range(6):
            value,_,_=self.run_case(market=market,feature=f,name=f'profile-{i}',profile=i);values.append(value)
        self.assertTrue(all(v['orders'][0]['order']==values[0]['orders'][0]['order'] for v in values))
        self.assertEqual(Decimal(values[0]['metrics']['fees']),Decimal(values[1]['metrics']['fees'])*5)
        self.assertEqual(Decimal(values[2]['metrics']['fees']),0)
        self.assertEqual(values[4]['metrics']['entry_quantity'],'0.0004')
        self.assertEqual(values[4]['metrics']['close_quantity'],'0.0004')
        self.assertTrue(all(v['metrics']['ending_position_quantity']=='0' for v in values))
        self.assertLess(Decimal(values[5]['metrics']['conditional_closed_pnl']),Decimal(values[0]['metrics']['conditional_closed_pnl']))

    def test_retry_remains_subject_to_native_notional_cap(self):
        value,_,_=self.run_case(quotes=quotes(future='200000'));m=value['metrics']
        self.assertEqual(m['close_outcome'],'request_rejected');self.assertEqual(m['retry_outcome'],'request_rejected')
        self.assertEqual(m['ending_position_quantity'],'0.001');self.assertEqual(len(value['orders']),3)
        self.assertIsNone(m['conditional_closed_pnl'])

    def test_native_loader_retains_no_signal_without_invented_profit(self):
        q=quotes();q=[(t,'99.99','100.01',bs,ask,ex) for t,b,a,bs,ask,ex in q]
        _,source=FIXTURE.market(self.root,quotes=q)
        inventory={f'supervision/run-000001/session/{p.name}':dict(bytes=p.stat().st_size,sha256=RUN.REVIEW.digest(p)) for p in source.iterdir()}
        market=RUN.load_market(BINARY,source,self.root/'fresh',1,inventory,'synthetic_fixture',time.monotonic()+60)
        self.assertIsNone(market['feature']);self.assertEqual(market['label']['reason'],'no_signal')
        self.assertGreater(market['selection']['counts']['abstentions'],0)

    def test_reconnected_fresh_acknowledged_quote_can_close_an_existing_position(self):
        initial=[json.loads(line) for line in (FIXTURE.PROJECT/'fixtures/hyperliquid-combined-v2.jsonl').read_text().splitlines()][:7]
        extra=[(59000,1,dict(type='connection_closed',reason='synthetic reconnect')),
            (59200,2,dict(type='connection_attempt',endpoint='wss://synthetic.invalid/ws')),(59201,2,dict(type='connection_opened'))]
        for i,row in enumerate(initial[3:],59202):extra.append((i,2,row['event']))
        for t in (60010,60510,61010):
            payload=dict(channel='bbo',data=dict(coin='BTC',time=100000+t,
                bbo=[dict(px='100.19',sz='0.004',n=1),dict(px='100.21',sz='0.004',n=1)]))
            extra.append((t,2,dict(type='text_received',text=json.dumps(payload))))
        value,market,f=self.run_case(quotes=quotes(end=58510),extra=extra,finish=62000,end_connection=2)
        self.assertEqual(value['close_compilation']['decision']['connection_id'],2)
        self.assertEqual(value['metrics']['ending_position_quantity'],'0')
        self.assertEqual(RUN.CORE.label(market['events'],f)['status'],'unavailable')

    def test_later_equal_time_quote_cannot_choose_first_close_price_or_anchor(self):
        q=quotes();q.append((60010,'199.99','200.01','0.004','0.004',160011))
        value,_,_=self.run_case(quotes=q)
        self.assertEqual(value['close_compilation']['decision']['quote']['bid'],'100.19')
        self.assertEqual(value['orders'][1]['order']['limit_price'],'100.169962')
        self.assertTrue(value['causal_prefix_verified'])

    def test_extra_close_arrival_after_eof_stays_pending_with_known_inventory(self):
        value,_,_=self.run_case(quotes=quotes(end=60510,partial=True),finish=60550);m=value['metrics']
        self.assertEqual(m['retry_outcome'],'pending_at_source_end');self.assertEqual(m['pending_order_ids'],['close-retry'])
        self.assertEqual(m['ending_position_quantity'],'0.00075');self.assertIsNone(m['conditional_closed_pnl'])

    def test_reused_entry_control_cannot_replace_its_original_artifact_hash(self):
        market,_,f=self.prepare(quotes=quotes(end=35010));verify=RUN.CORE.verify_close
        def corrupt(*args):
            audit=verify(*args)
            target=self.root/'case/entry-control/paper-input.jsonl'
            target.write_bytes(target.read_bytes()+b'\n')
            return audit
        with patch.object(RUN.CORE,'verify_close',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'retained control artifacts changed'):
                self.run_case(market=market,feature=f)


if __name__=='__main__':unittest.main()
