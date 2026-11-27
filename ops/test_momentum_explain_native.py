"""Real native retained-input replays; fixture production is separate from diagnosis."""
import copy
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from . import momentum_explain_local as DIAG, test_momentum_native as FIXTURE
except ImportError:
    import momentum_explain_local as DIAG
    import test_momentum_native as FIXTURE

RUN=DIAG.RUN
BINARY=FIXTURE.BINARY


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native executable required')
class RetainedNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def prepare(self,**kwargs):
        _,source=FIXTURE.FIXTURE.market(self.root,quotes=kwargs.pop('quotes',None) or FIXTURE.quotes(),**kwargs)
        expected={f'supervision/run-000001/session/{p.name}':dict(bytes=p.stat().st_size,sha256=RUN.REVIEW.digest(p)) for p in source.iterdir()}
        market=RUN.load_market(BINARY,source,self.root/'fresh',1,expected,'synthetic_fixture',time.monotonic()+60)
        return market,expected

    def produce(self,market,profile=0):
        scenario=RUN.CORE.entry_scenario(market['feature'],RUN.CORE.PROFILES[profile])
        folder=self.root/f'case-{profile}'
        value=RUN.run_case(BINARY,market,scenario,market['feature'],folder,time.monotonic()+60)
        return value,folder

    def diagnose(self,market,folder,name='verification'):
        before=DIAG.inventory(folder,time.monotonic()+10)
        with patch.object(RUN,'run_case',side_effect=AssertionError('diagnostic cannot invoke producer')),\
             patch.object(RUN.MODEL,'proxy',side_effect=AssertionError('diagnostic cannot invoke proxy')):
            result=DIAG.verify_case(BINARY,market,folder,self.root/name,time.monotonic()+60)
        self.assertEqual(before,DIAG.inventory(folder,time.monotonic()+10))
        return result

    def test_source_cache_reproduces_exactly_and_changed_normalization_is_refused(self):
        market,expected=self.prepare()
        fresh,receipt=DIAG.verify_market(BINARY,self.root/'fresh',self.root/'check',1,expected,'synthetic_fixture',time.monotonic()+60)
        self.assertEqual(fresh['feature'],market['feature']);self.assertTrue(receipt['native_market_files_byte_equal'])
        target=self.root/'fresh/normalized.jsonl';target.write_bytes(target.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'native replay differs'):
            DIAG.verify_market(BINARY,self.root/'fresh',self.root/'changed',1,expected,'synthetic_fixture',time.monotonic()+60)

    def test_all_six_retained_profiles_have_exact_native_cost_identity_and_repeated_receipts(self):
        market,_=self.prepare(quotes=FIXTURE.quotes(partial=True))
        for profile in range(6):
            original,folder=self.produce(market,profile)
            value,e,receipt=self.diagnose(market,folder,f'check-{profile}')
            self.assertEqual(original,value);self.assertTrue(e['closed_decomposition']['identity_verified'])
            self.assertEqual(e['closed_decomposition']['closed_net_usdc'],original['metrics']['conditional_closed_pnl'])
            if profile==0:
                again=self.diagnose(market,folder,'repeat');self.assertEqual(again,(value,e,receipt))
                self.assertEqual(e['orders'][1]['explanation'],'remaining_assumed_capacity_limited')

    def test_retained_short_has_exact_native_identity(self):
        market,_=self.prepare(quotes=FIXTURE.quotes(direction='down'));_,folder=self.produce(market)
        _,e,_=self.diagnose(market,folder)
        self.assertEqual(e['orders'][0]['side'],'sell');self.assertEqual(e['closed_decomposition']['closed_net_usdc'],'-0.000139760001')

    def test_missing_close_before_source_eof_keeps_original_open_entry(self):
        market,_=self.prepare(quotes=FIXTURE.quotes(end=35010));_,folder=self.produce(market)
        _,e,r=self.diagnose(market,folder)
        self.assertEqual(e['close_window']['status'],'source_ended_before_close_window')
        self.assertEqual(e['ending_position_quantity'],'0.001');self.assertIsNone(e['closed_decomposition'])
        self.assertEqual(list(r['ledgers']),['entry-control'])

    def test_two_partial_exits_keep_residual_and_capacity_evidence(self):
        quotes=[(t,b,a,'0.001' if t>=60010 else bs,ask,ex) for t,b,a,bs,ask,ex in FIXTURE.quotes(partial=True)]
        market,_=self.prepare(quotes=quotes);_,folder=self.produce(market)
        _,e,_=self.diagnose(market,folder)
        self.assertEqual(e['ending_position_quantity'],'0.0005');self.assertIsNone(e['closed_decomposition'])
        for order in e['orders'][1:]:
            self.assertEqual(order['remaining_shared_capacity'],'0.00025')
            self.assertEqual(order['explanation'],'remaining_assumed_capacity_limited')

    def test_pending_arrival_stays_pending_without_invented_fill_or_cost(self):
        market,_=self.prepare(quotes=FIXTURE.quotes(end=30010),finish=30050);_,folder=self.produce(market)
        _,e,_=self.diagnose(market,folder)
        self.assertEqual(e['pending_order_ids'],['entry']);self.assertIsNone(e['closed_decomposition'])
        self.assertIsNone(e['orders'][0]['cost']);self.assertEqual(e['orders'][0]['outcome'],'pending_at_source_end')

    def test_native_notional_rejection_preserves_detail_and_no_fill(self):
        market,_=self.prepare(quotes=FIXTURE.quotes(scale='200000'));_,folder=self.produce(market)
        _,e,_=self.diagnose(market,folder)
        self.assertEqual(e['outcome'],'no_fills');self.assertEqual(e['orders'][0]['explanation'],'request_rejected')
        self.assertIsNotNone(e['orders'][0]['native_rejection']);self.assertIsNone(e['closed_decomposition'])

    def test_nonmarketable_arrival_preserves_no_fill_and_original_price_limit(self):
        quotes=FIXTURE.quotes()+[(30050,'100.23','100.25','0.004','0.004',130050)]
        market,_=self.prepare(quotes=quotes);_,folder=self.produce(market,5)
        _,e,_=self.diagnose(market,folder)
        self.assertEqual(e['outcome'],'no_fills');self.assertEqual(e['known_fees_usdc'],'0')
        self.assertEqual(e['orders'][0]['outcome'],'not_marketable');self.assertFalse(e['orders'][0]['marketable'])
        self.assertIsNone(e['orders'][0]['cost']);self.assertIsNone(e['closed_decomposition'])

    def test_tampered_retained_decision_receipt_is_rejected(self):
        market,_=self.prepare();_,folder=self.produce(market)
        path=folder/'first-close/decisions.json';r=RUN.ORIGINAL.obj(path)
        r['decisions'][0]['available_quantity']='99';path.write_text(__import__('json').dumps(r))
        with self.assertRaisesRegex(ValueError,'receipt differs'):self.diagnose(market,folder)

    def test_changed_checkpoint_or_missing_retained_control_is_refused(self):
        market,_=self.prepare();_,folder=self.produce(market)
        path=folder/'entry-control/checkpoints/0001.report.json';raw=path.read_bytes();path.write_bytes(raw+b' ')
        with self.assertRaisesRegex(ValueError,'checkpoint report fingerprint'):self.diagnose(market,folder)
        path.write_bytes(raw)
        retry=folder/'retry-compilation.json';value=RUN.ORIGINAL.obj(retry)
        value['retained_control_hashes'].pop(next(iter(value['retained_control_hashes'])))
        retry.write_text(__import__('json').dumps(value))
        with self.assertRaisesRegex(ValueError,'fingerprint set differs'):self.diagnose(market,folder,'missing-control')


if __name__=='__main__':unittest.main()
