import json
import os
from pathlib import Path
import tempfile
import time
import unittest

try:
    from . import cadence_local as RUN,test_expiry_native as FIXTURE
except ImportError:
    import cadence_local as RUN
    import test_expiry_native as FIXTURE

BINARY=FIXTURE.BINARY


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native binary required; set GIETHOORN_TEST_BINARY')
class CadenceNativeTests(unittest.TestCase):
    def setUp(self):
        self.seed=FIXTURE.ExpiryNativeTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)

    def prepared(self,**kwargs):
        root,_,_,market=self.seed.prepare(**kwargs)
        group=dict(child=1,children=[1],_base='market-audit/market',_market=market['report'])
        return root,group

    def fresh(self,root,group,name='cadence'):
        return RUN.fresh_source(BINARY,root,group,root/name,'synthetic_fixture',time.monotonic()+30)

    def test_native_replay_cadence_matches_hand_calculated_fixed_updates(self):
        root,group=self.prepared()
        events=self.fresh(root,group)
        metric,_=RUN.CORE.analyze(1,events)
        self.assertEqual(metric['series']['bbo_messages']['observations'],66)
        self.assertEqual(metric['series']['bbo_messages']['intervals'],65)
        self.assertEqual(metric['series']['native_opportunities']['observations'],66)
        self.assertEqual(metric['series']['native_opportunities']['percentiles_ns']['95'],'100000000')

    def test_one_sided_tail_is_raw_data_and_censored_native_silence(self):
        root,group=self.prepared(book=lambda t:(None,'100.01','0.02','0.004') if t>=5410 else ('99.99','100.01','0.02','0.004'))
        events=self.fresh(root,group)
        metric,_=RUN.CORE.analyze(1,events)
        self.assertEqual(metric['series']['bbo_messages']['observations'],66)
        self.assertEqual(metric['series']['native_opportunities']['observations'],54)
        connection=metric['connections'][0]
        self.assertEqual(connection['raw_bbo_without_native_opportunity'],12)
        self.assertEqual(connection['series']['native_opportunities']['trailing_observed_silence_ns'],'1201000000')
        self.assertEqual(metric['series']['native_opportunities']['maximum_ns'],'100000000')

    def test_fresh_native_source_checksum_refuses_corruption(self):
        root,group=self.prepared()
        path=root/group['_base']/'source/segment-00000001.jsonl'
        path.write_bytes(path.read_bytes()+b'{}\n')
        with self.assertRaises(ValueError):self.fresh(root,group)

    def test_repeat_preserves_exact_intervals_and_original_source(self):
        root,group=self.prepared()
        before=RUN.EXPLAIN.inventory(root/group['_base'])
        a,ai=RUN.CORE.analyze(1,self.fresh(root,group,'first'))
        b,bi=RUN.CORE.analyze(1,self.fresh(root,group,'second'))
        self.assertEqual(a,b);self.assertEqual(ai,bi)
        self.assertEqual(RUN.EXPLAIN.inventory(root/group['_base']),before)
