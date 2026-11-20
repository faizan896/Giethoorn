"""Native acceptance of explicitly hypothetical known-book decisions and costs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

try:
    from . import model_compare_local as RUN
except ImportError:
    import model_compare_local as RUN

PROJECT=Path(__file__).resolve().parent.parent
BINARY=Path(os.environ.get('GIETHOORN_TEST_BINARY',str(PROJECT/'target/debug/giethoorn'))).resolve()


def market(root,quotes=None,extra=(),stale=2000,finish=None,end_connection=1):
    source=root/'source';source.mkdir()
    prefix=[json.loads(line) for line in (PROJECT/'fixtures/hyperliquid-combined-v2.jsonl').read_text().splitlines()][:7]
    prefix[0]['event']['policy']=dict(profile='combined',depth_stale_after_ms=15000,bbo_stale_after_ms=stale,timer_interval_ms=min(250,stale))
    quotes=quotes or [(10,'99.99','100.01','0.004','0.004',100010),(500,'99.99','100.01','0.004','0.004',100500)]
    additions=[]
    for ms,bid,ask,bid_size,ask_size,exchange in quotes:
        value=dict(channel='bbo',data=dict(coin='BTC',time=exchange,bbo=[None if bid is None else dict(px=bid,sz=bid_size,n=1),
            None if ask is None else dict(px=ask,sz=ask_size,n=1)]))
        additions.append((ms,1,dict(type='text_received',text=json.dumps(value))))
    additions.extend(extra)
    additions.sort(key=lambda row:row[0])
    end=max(row[0] for row in additions)+2 if finish is None else finish
    additions.extend([(end-1,end_connection,dict(type='connection_closed',reason='synthetic source end')),
                      (end,0,dict(type='session_ended',reason='duration_elapsed'))])
    for ms,connection,event in additions:
        prefix.append(dict(schema_version=2,sequence=len(prefix)+1,local_time_ns=1000000000+ms*1000000,
                           monotonic_ns=ms*1000000,connection_id=connection,event=event))
    raw=b''.join(RUN.QUALITY.encoded(row)+b'\n' for row in prefix)
    (source/'segment-00000001.jsonl').write_bytes(raw)
    index=[dict(kind='header',container_version=1,event_schema_version=2,max_segment_bytes=1048576,max_session_bytes=2097152),
        dict(kind='segment',number=1,file='segment-00000001.jsonl',bytes=len(raw),first_sequence=1,last_sequence=len(prefix),sha256=hashlib.sha256(raw).hexdigest()),
        dict(kind='end',segments=1,records=len(prefix),data_bytes=len(raw))]
    (source/'index.jsonl').write_bytes(b''.join(RUN.QUALITY.encoded(row)+b'\n' for row in index))
    folder=root/'market'
    completed=subprocess.run([str(BINARY),'paper-market-replay','--input',str(source),'--output-dir',str(folder),
        '--origin','synthetic-fixture','--feed','bbo'],capture_output=True,text=True,timeout=10)
    if completed.returncode:raise ValueError(completed.stderr)
    frames=RUN.ORIGINAL.lines(folder/'paper-updates.jsonl');links=RUN.ORIGINAL.lines(folder/'market-links.jsonl')
    events=RUN.ORIGINAL.CORE.market_events(prefix,frames,links)
    return dict(directory=folder,events=events,original=prefix,report=json.loads(completed.stdout)),source


def scenario(orders=None,**assumptions):
    model={**dict(fee_rate='0.0005',slippage_bps='1',top_size_fraction='0.25',latency_ms=100,quote_wait_ms=250),**assumptions}
    return dict(scenario_version=1,label='Synthetic fixed requests for model comparison',starting_collateral='10000',
        max_abs_position='1',max_order_notional='1000',max_working_orders=16,max_loss='10',
        assumptions=model,
        orders=orders or [dict(id='entry',after_market_sequence=8,side='buy',quantity='0.001',limit_price='101')])


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native ledger executable required')
class ModelComparisonNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def run_proxy(self,source=None,plan=None,name='proxy',**kwargs):
        if source is None:source,_=market(self.root,**kwargs)
        return RUN.proxy(BINARY,source,plan or scenario(),self.root/name,time.monotonic()+40),source

    def test_quiet_window_uses_known_quote_while_original_model_expires(self):
        alternative,source=self.run_proxy()
        d=alternative['orders'][0]
        self.assertEqual(d['reference_quote']['sequence'],8)
        self.assertEqual(d['reference_age_ns'],'100000000')
        self.assertEqual(d['assumed_fill_price'],'100.020001')
        self.assertEqual(d['assumed_fee'],'0.0000500100005')
        self.assertEqual(alternative['metrics']['ending_position_quantity'],'0.001')
        self.assertIsNone(alternative['metrics']['conditional_closed_pnl'])
        plan=self.root/'old-scenario.json';RUN.REVIEW.save(plan,scenario())
        old=self.root/'old'
        done=subprocess.run([str(BINARY),'paper-execution-replay','--input',str(self.root/'source'),'--scenario',str(plan),
            '--output-dir',str(old),'--origin','synthetic-fixture','--feed','bbo'],capture_output=True,text=True,timeout=10)
        self.assertEqual(done.returncode,0,done.stderr)
        report=json.loads(done.stdout)
        self.assertEqual(report['paper']['orders'][0]['status'],'rejected')
        self.assertIn('expired',report['paper']['orders'][0]['rejection_detail'])

    def test_partial_fill_shares_capacity_and_preserves_open_exposure(self):
        orders=[dict(id=identity,after_market_sequence=8,side='buy',quantity='0.001',limit_price='101') for identity in ('first','second')]
        result,_=self.run_proxy(plan=scenario(orders=orders),quotes=[(10,'99.99','100.01','0.002','0.002',100010),(500,'99.99','100.01','0.002','0.002',100500)])
        self.assertEqual([d['assumed_fill_quantity'] for d in result['orders']],['0.0005','0'])
        self.assertEqual(result['orders'][0]['outcome'],'partial_fill_cancelled')
        self.assertEqual(result['orders'][1]['outcome'],'no_remaining_capacity')
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.0005')

    def test_round_trip_costs_match_hand_calculated_exact_native_accounting(self):
        orders=[dict(id='entry',after_market_sequence=8,side='buy',quantity='0.001',limit_price='101'),
            dict(id='close',after_market_sequence=9,side='sell',quantity='0.001',limit_price='99')]
        result,_=self.run_proxy(plan=scenario(orders=orders),quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (200,'99.99','100.01','0.004','0.004',100200),(500,'99.99','100.01','0.004','0.004',100500)])
        m=result['metrics']
        self.assertEqual(RUN.VERIFY.Decimal(m['fees']),RUN.VERIFY.Decimal('0.000100000001'))
        self.assertEqual(RUN.VERIFY.Decimal(m['spread_cost']),RUN.VERIFY.Decimal('0.00002'))
        self.assertEqual(RUN.VERIFY.Decimal(m['slippage_cost']),RUN.VERIFY.Decimal('0.00002'))
        self.assertEqual(m['conditional_closed_pnl'],'-0.000140000001')
        self.assertEqual(m['outcome'],'closed_under_assumptions')

    def test_equal_timestamp_sizes_do_not_replenish_consumed_liquidity(self):
        orders=[dict(id='a',after_market_sequence=8,side='buy',quantity='0.001',limit_price='101'),
                dict(id='b',after_market_sequence=9,side='buy',quantity='0.001',limit_price='101')]
        result,_=self.run_proxy(plan=scenario(orders=orders),quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (200,'99.990','100.010','5','5',100010),(500,'99.99','100.01','5','5',100500)])
        self.assertEqual([d['assumed_fill_quantity'] for d in result['orders']],['0.001','0'])

    def test_equal_timestamp_price_changes_disable_capacity(self):
        plan=scenario(orders=[dict(id='entry',after_market_sequence=9,side='buy',quantity='0.001',limit_price='101')])
        result,_=self.run_proxy(plan=plan,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (100,'100','100.02','0.004','0.004',100010),(500,'99.99','100.01','0.004','0.004',100500)])
        self.assertEqual(result['orders'][0]['outcome'],'no_remaining_capacity')

    def test_zero_latency_resolves_after_its_own_request(self):
        result,_=self.run_proxy(plan=scenario(latency_ms=0))
        d=result['orders'][0]
        self.assertEqual(d['outcome'],'filled');self.assertEqual(d['reference_age_ns'],'0')
        self.assertEqual(d['reference_quote']['sequence'],d['order']['after_market_sequence'])

    def test_equal_arrival_source_precedes_arrival_but_later_equal_time_quote_does_not(self):
        result,_=self.run_proxy(quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (110,'100','100.02','0.004','0.004',100110),(110,'100.1','100.12','0.004','0.004',100111),
            (500,'99.99','100.01','0.004','0.004',100500)])
        self.assertEqual(result['orders'][0]['reference_quote']['sequence'],9)
        self.assertEqual(result['orders'][0]['assumed_fill_price'],'100.030002')

    def test_reference_age_at_threshold_is_unusable_without_waiting_for_next_quote(self):
        result,_=self.run_proxy(stale=100)
        self.assertEqual(result['orders'][0]['outcome'],'no_usable_reference')
        self.assertEqual(result['metrics']['outcome'],'no_fills')

    def test_empty_or_disconnected_reference_cannot_bridge_to_later_data(self):
        for name,extra,quotes in [
            ('empty',(),[(10,'99.99','100.01','0.004','0.004',100010),(50,None,'100.01','0','0.004',100050),(500,'99.99','100.01','0.004','0.004',100500)]),
            ('closed',[(50,1,dict(type='connection_closed',reason='synthetic interrupted source'))],[(10,'99.99','100.01','0.004','0.004',100010)])]:
            root=self.root/name;root.mkdir()
            if name=='closed':
                # An actual connection-end event itself prevents a late arrival;
                # no fabricated reconnection or quote is added.
                extra=[(50,1,dict(type='connection_error',message='synthetic connection error'))]
            source,_=market(root,quotes=quotes,extra=extra,finish=300 if name=='closed' else None)
            result=RUN.proxy(BINARY,source,scenario(),root/'proxy',time.monotonic()+30)
            self.assertEqual(result['orders'][0]['outcome'],'no_usable_reference')

    def test_future_price_does_not_change_an_earlier_proxy_fill(self):
        a,_=self.run_proxy(name='a')
        folder=self.root/'other';folder.mkdir()
        source,_=market(folder,quotes=[(10,'99.99','100.01','0.004','0.004',100010),(500,'199.99','200.01','0.004','0.004',100500)])
        b,_=self.run_proxy(source=source,name='b')
        self.assertEqual(a['orders'],b['orders'])
        self.assertEqual(a['metrics']['fees'],b['metrics']['fees'])

    def test_source_end_before_arrival_retains_pending_request(self):
        result,_=self.run_proxy(quotes=[(10,'99.99','100.01','0.004','0.004',100010)],finish=20)
        self.assertEqual(result['orders'][0]['outcome'],'pending_at_source_end')
        self.assertEqual(result['metrics']['pending_order_ids'],['entry'])
        self.assertIsNone(result['metrics']['conditional_closed_pnl'])

    def test_source_end_equal_to_arrival_cannot_create_a_fill_from_a_closed_connection(self):
        result,_=self.run_proxy(quotes=[(10,'99.99','100.01','0.004','0.004',100010)],finish=110)
        self.assertEqual(result['orders'][0]['outcome'],'no_usable_reference')
        self.assertEqual(result['metrics']['assumed_fills'],0)

    def test_reconnect_does_not_reuse_the_previous_connections_book(self):
        initial=[json.loads(line) for line in (PROJECT/'fixtures/hyperliquid-combined-v2.jsonl').read_text().splitlines()][:7]
        extra=[(50,1,dict(type='connection_closed',reason='synthetic reconnect')),
            (100,2,dict(type='connection_attempt',endpoint='wss://synthetic.invalid/ws')),
            (101,2,dict(type='connection_opened'))]
        for n,row in enumerate(initial[3:],102):extra.append((n,2,row['event']))
        payload=dict(channel='bbo',data=dict(coin='BTC',time=100200,bbo=[dict(px='99.99',sz='0.004',n=1),dict(px='100.01',sz='0.004',n=1)]))
        extra.append((200,2,dict(type='text_received',text=json.dumps(payload))))
        result,_=self.run_proxy(quotes=[(10,'99.99','100.01','0.004','0.004',100010)],extra=extra,finish=400,end_connection=2)
        self.assertEqual(result['orders'][0]['outcome'],'no_usable_reference')

    def test_inflight_requests_can_resolve_after_halt_without_accepting_new_risk(self):
        orders=[dict(id=identity,after_market_sequence=8,side='buy',quantity='0.001',limit_price='101') for identity in ('a','b')]
        plan=scenario(orders=orders);plan['max_loss']='0.000001'
        result,_=self.run_proxy(plan=plan,quotes=[(10,'99.99','100.01','0.008','0.008',100010),(500,'99.99','100.01','0.008','0.008',100500)])
        self.assertEqual([d['outcome'] for d in result['orders']],['filled','filled'])
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.002')

    def test_fixed_later_requests_are_not_resized_to_alternative_fills(self):
        orders=[dict(id='entry',after_market_sequence=8,side='buy',quantity='0.001',limit_price='90'),
            dict(id='close',after_market_sequence=9,side='sell',quantity='0.001',limit_price='99')]
        result,_=self.run_proxy(plan=scenario(orders=orders),quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (200,'99.99','100.01','0.004','0.004',100200),(500,'99.99','100.01','0.004','0.004',100500)])
        self.assertEqual(result['orders'][0]['outcome'],'not_marketable')
        self.assertEqual(result['orders'][1]['order']['quantity'],'0.001')
        self.assertEqual(result['metrics']['ending_position_quantity'],'-0.001')

    def test_native_loss_halt_blocks_new_requests_but_keeps_open_exposure(self):
        orders=[dict(id='entry',after_market_sequence=8,side='buy',quantity='0.001',limit_price='101'),
            dict(id='close',after_market_sequence=9,side='sell',quantity='0.001',limit_price='99')]
        plan=scenario(orders=orders);plan['max_loss']='0.000001'
        result,_=self.run_proxy(plan=plan,quotes=[(10,'99.99','100.01','0.004','0.004',100010),
            (200,'99.99','100.01','0.004','0.004',100200),(500,'99.99','100.01','0.004','0.004',100500)])
        self.assertEqual(result['orders'][1]['outcome'],'request_rejected')
        self.assertEqual(result['orders'][1]['native_final_order']['rejection'],'halted')
        self.assertEqual(result['metrics']['ending_position_quantity'],'0.001')

    def test_repeat_has_exact_ledger_and_interval_prefixes_without_source_changes(self):
        source,raw=market(self.root)
        before=RUN.ORIGINAL.inventory(raw)
        a,_=self.run_proxy(source=source,name='a');b,_=self.run_proxy(source=source,name='b')
        self.assertEqual(a,b)
        for name in ('paper-input.jsonl','paper-updates.jsonl','comparison-links.jsonl'):
            self.assertEqual((self.root/'a'/name).read_bytes(),(self.root/'b'/name).read_bytes())
        self.assertEqual(RUN.ORIGINAL.inventory(raw),before)

    def test_independent_check_rejects_wrong_fee_and_future_reference(self):
        _,source=self.run_proxy()
        out=self.root/'proxy'
        records=RUN.ORIGINAL.lines(out/'paper-input.jsonl');links=RUN.ORIGINAL.lines(out/'comparison-links.jsonl')
        frames=RUN.ORIGINAL.lines(out/'paper-updates.jsonl');report=RUN.ORIGINAL.obj(out/'paper-report.json')
        decisions=RUN.ORIGINAL.obj(out/'decisions.json')['decisions'];base=RUN.ORIGINAL.lines(source['directory']/'paper-input.jsonl')
        bad=copy.deepcopy(links);next(row for row in bad if row['phase']=='assumed_fill')['fee']='100'
        with self.assertRaises(ValueError):RUN.VERIFY.verify(source['events'],base,scenario(),records,bad,frames,report,decisions)
        bad=copy.deepcopy(decisions);bad[0]['reference_quote']['sequence']=9
        with self.assertRaises(ValueError):RUN.VERIFY.verify(source['events'],base,scenario(),records,links,frames,report,bad)
