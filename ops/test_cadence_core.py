import copy
import json
from pathlib import Path
import unittest

try:
    from . import cadence_core as CORE,expiry_core as EXPLAIN
except ImportError:
    import cadence_core as CORE
    import expiry_core as EXPLAIN

PROJECT=Path(__file__).resolve().parent.parent
MS=1_000_000


def synthetic(points):
    result=[]
    for i,point in enumerate([dict(connection=0,ns=0,kind='header'),*points],1):
        connection,now=point['connection'],point['ns']
        kind=point.get('kind','bbo');usable=point.get('usable',kind=='bbo')
        channel='bbo' if kind=='bbo' else 'subscriptionResponse' if kind=='ack' else None
        event=dict(type={'header':'feed_session_started','timer':'feed_timer','opened':'connection_opened',
                         'closed':'connection_closed','ack':'text_received','bbo':'text_received'}[kind])
        if kind=='header':event['policy']=dict(profile='combined',bbo_stale_after_ms=1000,timer_interval_ms=50)
        exchange=point.get('exchange',1000+now//MS)
        if channel=='bbo':event['text']=json.dumps(dict(channel='bbo',data=dict(time=exchange)))
        if kind=='ack':event['text']=json.dumps(dict(channel=channel,data=dict(method='subscribe',subscription=dict(type='bbo'))))
        source=dict(sequence=i,connection_id=connection,monotonic_ns=now,local_time_ns=1_700_000_000_000_000_000+now+point.get('wall_offset',0),event=event)
        status='fresh' if usable else point.get('status','awaiting_data')
        result.append(dict(sequence=i,time=now,source=source,channel=channel,usable=usable,
            frame=dict(event_kind='market_observed' if usable else 'timer',risk=dict(market_status=status)),
            link=dict(quote=dict(exchange_time_ms=exchange) if usable else None,
                      feeds=dict(bbo=dict(status=status,acknowledged=point.get('ack',True))))))
    return result


def intervals(values):
    return [dict(delta_ns=str(n),clock_discontinuities_crossed=0,start=dict(sequence=i),end=dict(sequence=i+1)) for i,n in enumerate(values,1)]


class CadenceCoreTests(unittest.TestCase):
    def test_golden_native_source_keeps_raw_unusable_and_older_messages_separate(self):
        load=lambda n:[json.loads(s) for s in (PROJECT/'fixtures'/n).read_text().splitlines()]
        events=EXPLAIN.market_events(load('hyperliquid-combined-v2.jsonl'),load('paper-recorded-v2.updates.jsonl'),load('paper-recorded-v2.links.jsonl'))
        report,rows=CORE.analyze(1,events)
        self.assertEqual(report['series']['bbo_messages']['observations'],7)
        self.assertEqual(report['series']['native_opportunities']['observations'],5)
        self.assertEqual(report['series']['bbo_messages']['intervals'],5)
        self.assertEqual(report['series']['native_opportunities']['intervals'],3)
        self.assertEqual(report['series']['bbo_messages']['percentiles_ns']['50'],'20000000')
        self.assertEqual(report['series']['native_opportunities']['percentiles_ns']['50'],'60000000')
        self.assertEqual(report['connections'][1]['raw_regressed_exchange_times'],1)
        self.assertTrue(all(r['start']['connection_id']==r['end']['connection_id'] for r in rows))

    def test_nearest_rank_percentiles_match_hand_calculation_without_averaging(self):
        report=CORE.summary(intervals([1,2,3,4,5]),6)
        self.assertEqual(report['percentiles_ns'],{'50':'3','90':'5','95':'5','99':'5'})
        self.assertEqual(CORE.summary(intervals([1,2,3,4]),5)['percentiles_ns']['50'],'2')

    def test_bins_are_nonoverlapping_and_include_exact_upper_boundaries(self):
        values=[0,50*MS,50*MS+1,100*MS,100*MS+1,250*MS,250*MS+1,350*MS,350*MS+1,500*MS,500*MS+1,1000*MS,1000*MS+1]
        report=CORE.summary(intervals(values),len(values)+1)
        self.assertEqual([b['count'] for b in report['bins']],[2,2,2,2,2,2,1])
        self.assertEqual(report['zero_intervals'],1)

    def test_reconnections_never_create_a_cross_connection_gap(self):
        events=synthetic([dict(connection=1,ns=0),dict(connection=1,ns=10*MS),dict(connection=1,ns=20*MS,kind='closed'),
            dict(connection=2,ns=100*MS,kind='opened'),dict(connection=2,ns=110*MS),dict(connection=2,ns=120*MS),dict(connection=2,ns=130*MS,kind='closed')])
        report,rows=CORE.analyze(1,events)
        self.assertEqual(report['series']['bbo_messages']['observations'],4)
        self.assertEqual(report['series']['bbo_messages']['intervals'],2)
        self.assertEqual(report['series']['bbo_messages']['maximum_ns'],str(10*MS))
        self.assertEqual({r['delta_ns'] for r in rows},{str(10*MS)})

    def test_empty_series_has_unavailable_quantiles_and_an_observed_empty_span(self):
        report,_=CORE.analyze(1,synthetic([dict(connection=1,ns=0,kind='opened'),dict(connection=1,ns=100*MS,kind='timer')]))
        data=report['connections'][0]['series']['bbo_messages']
        self.assertEqual(data['observations'],0)
        self.assertIsNone(data['minimum_ns']);self.assertIsNone(data['percentiles_ns']['95'])
        self.assertEqual(data['empty_observed_span_ns'],str(100*MS))
        self.assertTrue(data['edge_silence_is_censored'])

    def test_one_message_keeps_censored_leading_and_trailing_silence(self):
        report,_=CORE.analyze(1,synthetic([dict(connection=1,ns=10*MS,kind='opened'),dict(connection=1,ns=50*MS),dict(connection=1,ns=200*MS,kind='closed')]))
        data=report['connections'][0]['series']['bbo_messages']
        self.assertEqual(data['intervals'],0)
        self.assertEqual(data['leading_observed_silence_ns'],str(40*MS))
        self.assertEqual(data['trailing_observed_silence_ns'],str(150*MS))
        self.assertIsNone(data['percentiles_ns']['50'])

    def test_same_monotonic_time_is_a_real_zero_interval_not_missing_data(self):
        report,_=CORE.analyze(1,synthetic([dict(connection=1,ns=10*MS,exchange=10),dict(connection=1,ns=10*MS,exchange=10)]))
        self.assertEqual(report['series']['bbo_messages']['minimum_ns'],'0')
        self.assertEqual(report['series']['bbo_messages']['zero_intervals'],1)
        self.assertEqual(report['connections'][0]['raw_repeated_exchange_times'],1)

    def test_older_or_unusable_message_is_not_deleted_from_raw_cadence(self):
        report,_=CORE.analyze(1,synthetic([dict(connection=1,ns=10*MS,exchange=100),
            dict(connection=1,ns=20*MS,exchange=99,usable=False,status='fresh')]))
        self.assertEqual(report['series']['bbo_messages']['observations'],2)
        self.assertEqual(report['series']['native_opportunities']['observations'],1)
        self.assertEqual(report['connections'][0]['raw_regressed_exchange_times'],1)
        self.assertEqual(report['connections'][0]['raw_bbo_without_native_opportunity'],1)

    def test_wall_clock_jump_is_flagged_without_deleting_the_monotonic_interval(self):
        report,rows=CORE.analyze(1,synthetic([dict(connection=1,ns=0),dict(connection=1,ns=20*MS,kind='timer',wall_offset=2_000_000_000),
            dict(connection=1,ns=30*MS,wall_offset=2_000_000_000)]))
        self.assertEqual(len(report['source_clock_discontinuities']),1)
        self.assertEqual(report['series']['bbo_messages']['maximum_ns'],str(30*MS))
        self.assertTrue(all(row['clock_discontinuities_crossed']==1 for row in rows))

    def test_backward_wall_clock_is_explicit_and_does_not_reset_cadence(self):
        report,_=CORE.analyze(1,synthetic([dict(connection=1,ns=0),dict(connection=1,ns=20*MS,wall_offset=-2_000_000_000)]))
        self.assertEqual(report['wall_clock_backward_events'],1)
        self.assertEqual(report['series']['bbo_messages']['intervals_crossing_clock_discontinuities'],1)

    def test_monotonic_regression_or_source_reordering_is_refused(self):
        with self.assertRaisesRegex(ValueError,'monotonic'):
            CORE.analyze(1,synthetic([dict(connection=1,ns=20*MS),dict(connection=1,ns=10*MS)]))
        events=synthetic([dict(connection=1,ns=0)]);events[-1]['sequence']=99
        with self.assertRaisesRegex(ValueError,'ordering'):CORE.analyze(1,events)

    def test_large_timestamps_and_one_nanosecond_intervals_remain_exact(self):
        large=2**63+123
        report,rows=CORE.analyze(1,synthetic([dict(connection=1,ns=large),dict(connection=1,ns=large+1)]))
        self.assertEqual(report['series']['bbo_messages']['maximum_ns'],'1')
        self.assertEqual(rows[0]['start']['monotonic_ns'],str(large))

    def test_connection_start_and_ack_are_context_not_bbo_intervals(self):
        report,_=CORE.analyze(1,synthetic([dict(connection=1,ns=0,kind='opened'),dict(connection=1,ns=20*MS,kind='ack'),
            dict(connection=1,ns=30*MS,usable=False,ack=False)]))
        connection=report['connections'][0]
        self.assertEqual(len(connection['bbo_acknowledgements']),1)
        self.assertEqual(connection['series']['bbo_messages']['observations'],1)
        self.assertEqual(connection['series']['native_opportunities']['observations'],0)
        self.assertEqual(connection['raw_ack_counts']['unacknowledged'],1)

    def test_inputs_are_not_mutated_and_no_economic_metric_is_created(self):
        events=synthetic([dict(connection=1,ns=0),dict(connection=1,ns=10*MS)])
        before=copy.deepcopy(events);report,_=CORE.analyze(1,events)
        self.assertEqual(events,before)
        self.assertFalse(report['profit_evaluated'] or report['measured_order_latency'] or report['fill_probability_estimated'])

    def test_negative_gap_or_impossible_count_is_refused(self):
        with self.assertRaises(ValueError):CORE.summary(intervals([-1]),2)
        with self.assertRaises(ValueError):CORE.summary(intervals([1]),0)
