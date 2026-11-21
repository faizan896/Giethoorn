"""R002 causal histories, exact thresholds and complete research denominators."""
import copy
from decimal import Decimal
import json
import unittest

try:
    from . import momentum_core as CORE
    from .test_evaluation_core import policy
except ImportError:
    import momentum_core as CORE
    from test_evaluation_core import policy


def event(sequence, ms, mid='100', connection=1):
    value=Decimal(mid);bid=str(value-Decimal('0.01'));ask=str(value+Decimal('0.01'))
    now=int(Decimal(str(ms))*1000000)
    payload=dict(channel='bbo',data=dict(coin='BTC',time=100000+now//1000000,
        bbo=[dict(px=bid,sz='0.004',n=1),dict(px=ask,sz='0.004',n=1)]))
    source=dict(schema_version=2,sequence=sequence,monotonic_ns=now,local_time_ns=now+1000000000,
        connection_id=connection,event=dict(type='text_received',text=json.dumps(payload)))
    quote=dict(sequence=sequence,monotonic_ns=now,connection_id=connection,bid=bid,ask=ask,
        exchange_time_ms=payload['data']['time'])
    return dict(sequence=sequence,time=now,source=source,usable=True,channel='bbo',
        link=dict(quote=quote,feeds=dict(bbo=dict(acknowledged=True,status='fresh'))),
        frame=dict(account=dict(mark_fresh=True),risk=dict(market_status='fresh')))


def timeline(end=65000, direction='up'):
    return [event(i,t,'100' if t<30000 else '100.2' if direction=='up' else '99.8')
        for i,t in enumerate(range(0,end+1,500),1)]


def cases(children, net='1'):
    result=[]
    for child in children:
        for p in CORE.PROFILES:
            value=policy(net=net);value['metrics'].update(retry_requested_quantity=None)
            result.append(dict(case_id=f'run-{child:06d}--{p["id"]}',child=child,profile=p['id'],status='verified',policy=value))
    return result


class MomentumSelectionTests(unittest.TestCase):
    def test_exact_up_down_small_flat_and_spread_cost_examples(self):
        for b,a,old,direction in [('99.99','100.01','99.8','up'),('99.99','100.01','100.2','down'),
            ('99.99','100.01','99.9','abstain'),('99','101','99.8','abstain'),('99.99','100.01','100','abstain'),
            ('10014.9984','10017.0016','10000','up'),('9983.0016','9984.9984','10000','down')]:
            with self.subTest(b=b,a=a,old=old):
                r=CORE.movement(dict(bid=b,ask=a),dict(mid=CORE.ratio(CORE.Fraction(old))))
                self.assertEqual(r['prediction'],direction)
                self.assertEqual(CORE.fraction(r['entry_hurdle_bps'])-CORE.fraction(r['current_spread_bps']),14)

    def test_first_causal_feature_preserves_exact_reference_and_prefix(self):
        events=timeline();r=CORE.select(events,7);f=r['feature']
        self.assertEqual(f['monotonic_ns'],30000000000);self.assertEqual(f['reference']['sequence'],1)
        self.assertEqual(f['prediction'],'up');self.assertEqual(r['counts']['candidates'],1)
        self.assertEqual(CORE.verify_selection(events,7,r)['status'],'verified')

    def test_short_signal_uses_same_frozen_cost_hurdle(self):
        f=CORE.select(timeline(direction='down'),1)['feature'];self.assertEqual(f['prediction'],'down')
        self.assertEqual(CORE.entry_scenario(f,CORE.PROFILES[0])['orders'][0]['side'],'sell')

    def test_future_prices_labels_and_source_end_cannot_change_selected_feature(self):
        original=timeline();a=CORE.select(original,1)
        changed=copy.deepcopy(original)
        for e in changed:
            if e['time']>a['feature']['monotonic_ns']:
                e['source']['event']['text']='future hostile non-feature text';e['usable']=False
        self.assertEqual(a,CORE.select(changed,1))
        self.assertEqual(a,CORE.select(original[:a['feature']['sequence']],1))

    def test_first_abstaining_quote_cannot_be_replaced_in_the_same_bin(self):
        events=timeline();events[60]=event(61,30000,'100')
        events.insert(61,event(0,30100,'100.2'))
        for i,e in enumerate(events,1):e['sequence']=e['source']['sequence']=e['link']['quote']['sequence']=i
        r=CORE.select(events,1)
        self.assertEqual(r['candidates'][0]['prediction'],'abstain')
        self.assertEqual(r['feature']['monotonic_ns'],35000000000)

    def test_history_gap_over_one_second_prevents_entry(self):
        events=[e for e in timeline(end=35000) if not 15000000000<=e['time']<16000000000]
        # Keep sequence identity after removing a known interval.
        for i,e in enumerate(events,1):e['sequence']=e['source']['sequence']=e['link']['quote']['sequence']=i
        r=CORE.select(events,1);self.assertIsNone(r['feature']);self.assertGreater(r['counts']['missing_history'],0)

    def test_one_second_gap_boundary_remains_eligible(self):
        events=[e for e in timeline() if e['time']!=15000000000]
        for i,e in enumerate(events,1):e['sequence']=e['source']['sequence']=e['link']['quote']['sequence']=i
        self.assertIsNotNone(CORE.select(events,1)['feature'])

    def test_reconnect_and_observed_unusable_feed_reset_history(self):
        for reason in ('reconnect','unusable'):
            events=timeline(end=35000)
            if reason=='reconnect':
                for e in events[40:]:e['source']['connection_id']=e['link']['quote']['connection_id']=2
            else:events[40]['link']['feeds']['bbo']['status']='stale';events[40]['usable']=False
            self.assertIsNone(CORE.select(events,1)['feature'],reason)

    def test_wall_clock_step_resets_history_without_becoming_network_latency(self):
        events=timeline(end=35000)
        for e in events[40:]:e['source']['local_time_ns']+=1000000000
        r=CORE.select(events,1);self.assertIsNone(r['feature']);self.assertIn('clock_discontinuity',r['history_resets'])

    def test_monotonic_regression_is_source_failure(self):
        events=timeline();events[10]['time']=-1
        with self.assertRaisesRegex(ValueError,'clock regressed'):CORE.select(events,1)

    def test_duplicate_exchange_times_never_refresh_unique_history(self):
        events=timeline(end=35000)
        for e in events:
            e['link']['quote']['exchange_time_ms']=100000
            p=json.loads(e['source']['event']['text']);p['data']['time']=100000;e['source']['event']['text']=json.dumps(p)
        r=CORE.select(events,1);self.assertIsNone(r['feature']);self.assertEqual(r['counts']['candidates'],0)

    def test_depth_and_timer_events_cannot_supply_a_candidate(self):
        events=timeline(end=35000)
        for e in events[60:]:e['channel']='l2Book';e['usable']=False
        r=CORE.select(events,1);self.assertIsNone(r['feature']);self.assertEqual(r['counts']['candidates'],0)

    def test_missing_reference_is_not_interpolated_or_replaced(self):
        events=timeline(end=35000);events[0]['usable']=False
        r=CORE.select(events,1)
        self.assertEqual(r['candidates'][0]['status'],'missing_history')
        self.assertEqual(r['feature']['monotonic_ns'],35000000000)

    def test_raw_prices_and_coin_must_match_native_normalization(self):
        for key,value in [('bid','1'),('exchange_time_ms',2)]:
            events=timeline();events[0]['link']['quote'][key]=value
            with self.assertRaises(ValueError):CORE.select(events,1)

    def test_same_selected_feature_is_used_with_all_six_cost_profiles(self):
        f=CORE.select(timeline(),1)['feature'];plans=[CORE.entry_scenario(f,p) for p in CORE.PROFILES]
        self.assertTrue(all(p['orders']==plans[0]['orders'] for p in plans))
        self.assertEqual([p['assumptions'] for p in plans],[p['assumptions'] for p in CORE.PROFILES])

    def test_label_can_be_missing_without_filtering_entry(self):
        events=timeline(end=35000);r=CORE.select(events,1)
        self.assertIsNotNone(r['feature']);self.assertEqual(CORE.label(events,r['feature'])['status'],'unavailable')

    def test_label_uses_first_unique_future_quote_and_exact_signed_movement(self):
        events=timeline();f=CORE.select(events,1)['feature'];label=CORE.label(events,f)
        self.assertEqual(label['status'],'labelled');self.assertEqual(label['future']['monotonic_ns'],60000000000)
        self.assertEqual(CORE.fraction(label['signed_mid_change_bps']),0)

    def test_close_horizon_is_thirty_seconds_and_inclusive_one_second_late(self):
        events=timeline();f=CORE.select(events,1)['feature']
        self.assertEqual(CORE.close_decision(events,f)['monotonic_ns'],60000000000)
        for e in events:
            if 60000000000<=e['time']<61000000000:e['usable']=False
        self.assertEqual(CORE.close_decision(events,f)['monotonic_ns'],61000000000)
        events[122]['usable']=False
        self.assertIsNone(CORE.close_decision(events,f))

    def test_tampered_selection_receipt_or_prediction_is_refused(self):
        events=timeline();r=CORE.select(events,1);r['feature']['prediction']='down'
        with self.assertRaisesRegex(ValueError,'receipt differs'):CORE.verify_selection(events,1,r)

    def test_reference_tolerance_boundary_is_inclusive_without_interpolation(self):
        for offset,eligible in [(250000000,True),(250000001,False)]:
            events=timeline(end=30000);events[0]['usable']=False
            added=event(0,0,'100');added['time']=added['source']['monotonic_ns']=added['link']['quote']['monotonic_ns']=offset
            added['source']['local_time_ns']=offset+1000000000
            events.insert(1,added)
            for i,e in enumerate(events,1):e['sequence']=e['source']['sequence']=e['link']['quote']['sequence']=i
            r=CORE.select(events,1)
            self.assertEqual(r['feature'] is not None,eligible)

    def test_missing_forward_quality_does_not_replace_the_frozen_entry(self):
        events=timeline();selected=CORE.select(events,1)
        events[100]['link']['feeds']['bbo']['status']='stale';events[100]['usable']=False
        self.assertEqual(CORE.select(events,1),selected)
        self.assertEqual(CORE.label(events,selected['feature'])['status'],'unavailable')

    def test_entry_cannot_change_risk_quantity_fee_or_protective_limit(self):
        f=CORE.select(timeline(),1)['feature'];entry=CORE.entry_scenario(f,CORE.PROFILES[0])
        self.assertEqual(CORE.verify_entry(f,entry)['status'],'verified')
        for key,value in [('quantity','0.002'),('side','sell'),('limit_price','1000')]:
            wrong=copy.deepcopy(entry);wrong['orders'][0][key]=value
            with self.assertRaises(ValueError):CORE.verify_entry(f,wrong)

    def test_finite_bin_admission_refuses_without_truncating(self):
        events=[event(1,0),event(2,(4096+7)*5000)]
        with self.assertRaisesRegex(ValueError,'bin bound'):CORE.select(events,1)


class MomentumResearchGateTests(unittest.TestCase):
    def test_positive_complete_synthetic_cohort_only_earns_new_data_candidate(self):
        selected=list(range(1,31));t,g=CORE.summarize(cases(selected),selected)
        self.assertEqual(g['classification'],'candidate_for_separately_predeclared_new_data_confirmation_only')
        self.assertEqual([len(v['children']) for v in g['thirds']],[10,10,10])
        self.assertFalse(g['production_gate_completed']);self.assertEqual(t['cases'],180)

    def test_missing_negative_and_zero_baseline_evidence_cannot_advance(self):
        selected=list(range(1,31))
        for net in ('-1','0'):
            _,g=CORE.summarize(cases(selected,net),selected)
            self.assertEqual(g['classification'],'no_positive_development_evidence')

    def test_required_stress_loss_is_cost_sensitive_even_with_profitable_baseline(self):
        selected=list(range(1,31));rows=cases(selected)
        for c in rows:
            if c['profile']=='slippage-stress':c['policy']['metrics']['conditional_closed_pnl']='-1'
        self.assertEqual(CORE.summarize(rows,selected)[1]['classification'],'cost_sensitive_candidate')

    def test_open_pending_and_not_run_are_incomplete_with_no_complete_profile_net(self):
        selected=list(range(1,31))
        for kind in ('open','pending','not_run'):
            rows=cases(selected)
            if kind=='not_run':rows[0].update(status='not_run',policy=None)
            else:
                rows[0]['policy']=policy(net=None,position='0.001' if kind=='open' else '0',pending=['close'] if kind=='pending' else None)
                rows[0]['policy']['metrics']['retry_requested_quantity']=None
            t,g=CORE.summarize(rows,selected);self.assertEqual(g['classification'],'incomplete')
            self.assertIsNone(t['profiles'][0]['closed_cycle_net'])

    def test_insufficient_counts_and_unbalanced_chronological_coverage_stay_insufficient(self):
        selected=list(range(1,34));rows=cases(selected)
        for c in rows:
            if c['child'] in (1,2):c.update(status='no_signal',policy=None)
        self.assertEqual(CORE.summarize(rows,selected)[1]['classification'],'insufficient_data')
        small=list(range(1,6));self.assertEqual(CORE.summarize(cases(small),small)[1]['classification'],'insufficient_data')

    def test_unavailable_returns_never_become_zero_profit_trades(self):
        selected=[1,2,3];rows=cases(selected)
        for c in rows:c.update(status='no_signal',policy=None)
        t,g=CORE.summarize(rows,selected);self.assertEqual(g['classification'],'insufficient_data')
        self.assertTrue(all(p['closed_cycle_net'] is None for p in t['profiles']))

    def test_invalid_evidence_overrides_even_positive_synthetic_results(self):
        selected=list(range(1,31));self.assertEqual(CORE.summarize(cases(selected),selected,invalid=True)[1]['classification'],'invalid')

    def test_duplicate_or_omitted_case_membership_is_refused(self):
        for rows in (cases([1])[:-1],cases([1])+cases([1])[:1]):
            with self.assertRaisesRegex(ValueError,'membership'):CORE.summarize(rows,[1])


if __name__=='__main__':unittest.main()
