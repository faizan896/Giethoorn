from decimal import Decimal
from fractions import Fraction
import json
import unittest

try:
    from . import study_core as CORE
except ImportError:
    import study_core as CORE

MS = 1_000_000


def fixture(times=(0,250,500,750,1000,1250), price=None, sizes=None, end=None):
    """Synthetic original/native pairs for deterministic hand calculations."""
    events=[(dict(schema_version=2, sequence=1, monotonic_ns=0, local_time_ns=1_700_000_000_000_000_000,
                  connection_id=1, event=dict(type='feed_session_started')),None)]
    for i,t in enumerate(times):
        mid=Decimal(str(price(t) if price else (101 if t>=1000 else 100)))
        bid,ask=format(mid-1,'f'),format(mid+1,'f')
        bid_size,ask_size=sizes(t) if sizes else ('3','1')
        payload=dict(channel='bbo',data=dict(coin='BTC',time=100000+t,
            bbo=[dict(px=bid,sz=bid_size,n=1),dict(px=ask,sz=ask_size,n=1)]))
        record=dict(schema_version=2,sequence=i+2,monotonic_ns=t*MS,
                    local_time_ns=1_700_000_000_000_000_000+t*MS,connection_id=1,
                    event=dict(type='text_received',text=json.dumps(payload)))
        observation=dict(normalization_version=2,kind='bbo',coin='BTC',
            **{key:record[key] for key in ('sequence','connection_id','monotonic_ns','local_time_ns')},
            quote=dict(bid=bid,ask=ask,mid=format(mid,'f'),exchange_time_ms=100000+t),
            feeds=dict(bbo=dict(status='fresh',acknowledged=True,age_ns=0,stale_after_ms=2000),depth=None))
        events.append((record,observation))
    if end is not None:
        events.append((dict(schema_version=2,sequence=len(events)+1,monotonic_ns=end*MS,
            local_time_ns=1_700_000_000_000_000_000+end*MS,connection_id=1,event=dict(type='feed_timer')),None))
    return events


def run(events):
    analyzer=CORE.Analyzer(1);features=[];samples=[]
    for record,observation in events:
        for kind,value in analyzer.step(record,observation):
            (features if kind=='feature' else samples).append(value)
    for _,value in analyzer.finish():samples.append(value)
    return features,samples,analyzer.stats.report()


class CoreTests(unittest.TestCase):
    def test_exact_threshold_and_one_second_label_match_hand_calculation(self):
        features,samples,stats=run(fixture(sizes=lambda t:('0.3','0.1')))
        self.assertEqual(len(features),1)
        self.assertEqual(features[0]['prediction'],'up')
        self.assertNotIn('outcome',features[0])
        self.assertEqual(samples[0]['outcome']['future']['monotonic_ns'],1000*MS)
        self.assertEqual(samples[0]['outcome']['signed_mid_change_bps'],dict(numerator='100',denominator='1'))
        self.assertEqual(stats['hit_rate_percent'],'100.0000')
        self.assertEqual(stats['mean_signed_mid_change_bps_12dp'],'100.000000000000')

    def test_down_and_unchanged_labels_do_not_become_directional_wins(self):
        _,samples,stats=run(fixture(price=lambda t:99 if t>=1000 else 100,sizes=lambda t:('1','3')))
        self.assertEqual(samples[0]['outcome']['direction'],'down')
        self.assertEqual(stats['always_down_percent'],'100.0000')
        self.assertEqual(stats['always_up_percent'],'0.0000')
        _,_,stats=run(fixture(price=lambda t:100))
        self.assertEqual(stats['unchanged_signal_labels'],1)
        self.assertEqual(stats['signal_hits'],0)
        self.assertEqual(stats['hit_rate_percent'],'0.0000')

    def test_first_eligible_quote_consumes_bin_even_when_it_abstains(self):
        features,_,stats=run(fixture(times=(0,100,250,500,750,1000,5000),
                                   sizes=lambda t:('2','1') if t==0 else ('4','1')))
        self.assertEqual([f['bin'] for f in features],[0,1])
        self.assertEqual(features[0]['prediction'],'abstain')
        self.assertEqual(features[1]['prediction'],'up')
        self.assertEqual(stats['abstentions'],1)
        self.assertEqual(stats['missing_signal_labels'],1)
        self.assertIsNone(stats['hit_rate_percent'])

    def test_gap_marks_label_unavailable_without_replacing_earlier_feature(self):
        features,samples,stats=run(fixture(times=(0,250,500,1100)))
        self.assertEqual(len(features),1)
        self.assertEqual(samples[0]['outcome']['reason'],'bbo_gap_over_250ms')
        self.assertIsNone(samples[0]['outcome']['mid_change_bps'])
        self.assertEqual(stats['missing_labels'],1)
        self.assertIsNone(stats['mean_signed_mid_change_bps_12dp'])

    def test_label_uses_first_quote_at_or_after_horizon_and_requires_cadence(self):
        _,samples,_=run(fixture(times=(0,250,500,750,999,1249)))
        self.assertEqual(samples[0]['outcome']['future']['monotonic_ns'],1249*MS)
        _,samples,_=run(fixture(times=(0,250,500,750,999,1250)))
        self.assertEqual(samples[0]['outcome']['reason'],'bbo_gap_over_250ms')

    def test_depth_cannot_supply_a_bbo_label_or_refresh_its_gap(self):
        events=fixture(times=(0,250,500,750,1000,1100))
        events[-2][1]['kind']='depth'
        _,samples,_=run(events)
        self.assertEqual(samples[0]['outcome']['reason'],'bbo_gap_over_250ms')

    def test_unacknowledged_or_stale_quote_cannot_create_a_feature(self):
        for status,ack in [('fresh',False),('stale',True)]:
            with self.subTest(status=status,ack=ack):
                events=fixture(times=(0,250))
                for _,observation in events[1:]:observation['feeds']['bbo'].update(status=status,acknowledged=ack)
                features,_,stats=run(events)
                self.assertEqual(features,[])
                self.assertIsNone(stats['hit_rate_percent'])

    def test_connection_duplicate_and_clock_step_invalidate_pending_labels(self):
        for kind in ('connection','duplicate','clock'):
            with self.subTest(kind=kind):
                events=fixture()
                if kind=='connection':
                    for record,obs in events[3:]:record['connection_id']=obs['connection_id']=2
                    reason='connection_changed'
                elif kind=='duplicate':
                    events[3][1]['quote']['exchange_time_ms']=events[2][1]['quote']['exchange_time_ms']
                    reason='repeated_exchange_timestamp'
                else:
                    for record,obs in events[3:]:
                        record['local_time_ns']+=2_000*MS;obs['local_time_ns']=record['local_time_ns']
                    reason='clock_discontinuity'
                _,samples,_=run(events)
                self.assertEqual(samples[0]['outcome']['reason'],reason)

    def test_future_price_changes_cannot_change_an_emitted_prefix_feature(self):
        left=run(fixture(price=lambda t:100 if t<750 else 101))
        right=run(fixture(price=lambda t:100 if t<750 else 999))
        self.assertEqual(left[0],right[0])
        self.assertNotEqual(left[1][0]['outcome']['mid_change_bps'],right[1][0]['outcome']['mid_change_bps'])
        self.assertEqual(run(fixture())[0],run(fixture())[0])

    def test_missing_bins_and_unfinished_source_are_not_filled(self):
        features,samples,stats=run(fixture(times=(0,250,500,750,1000,20000,20250)))
        self.assertEqual([f['bin'] for f in features],[0,4])
        self.assertEqual(stats['sampling_bins_without_eligible_bbo'],3)
        self.assertEqual(samples[-1]['outcome']['reason'],'source_ended')
        self.assertIsNone(samples[-1]['outcome']['future'])

    def test_exact_fraction_and_declared_half_even_aggregation(self):
        _,samples,_=run(fixture(price=lambda t:4 if t>=1000 else 3))
        self.assertEqual(samples[0]['outcome']['signed_mid_change_bps'],dict(numerator='10000',denominator='3'))
        self.assertEqual(CORE.rounded_ticks(Fraction(25,10**13)),2)
        self.assertEqual(CORE.rounded_ticks(Fraction(35,10**13)),4)
        self.assertEqual(CORE.rounded_ticks(Fraction(-25,10**13)),-2)

    def test_raw_price_identity_or_invalid_size_is_refused(self):
        events=fixture(times=(0,))
        events[1][1]['quote']['mid']='999'
        with self.assertRaisesRegex(ValueError,'original prices'):run(events)
        for size in ('NaN','Infinity','-1','0'):
            with self.subTest(size=size),self.assertRaises(ValueError):run(fixture(sizes=lambda t:(size,'1')))


if __name__=='__main__':unittest.main()
