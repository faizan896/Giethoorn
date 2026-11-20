"""Native integration of archive source, causal feature and unchanged cycle."""
import os
from pathlib import Path
import tempfile
import time
import unittest

try:
    from . import evaluation_local as RUN, test_model_compare_native as FIXTURE
except ImportError:
    import evaluation_local as RUN
    import test_model_compare_native as FIXTURE

BINARY=FIXTURE.BINARY


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native executable required')
class DevelopmentEvaluationNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def source(self,imbalance=True,finish=7000):
        bid='0.016' if imbalance else '0.004'
        _,source=FIXTURE.market(self.root,quotes=[(10,'99.99','100.01',bid,'0.004',100010),
            (5010,'99.99','100.01',bid,'0.004',105010),(6010,'99.99','100.01',bid,'0.004',106010)],finish=finish)
        inventory={f'supervision/run-000001/session/{p.name}':dict(bytes=p.stat().st_size,sha256=RUN.REVIEW.digest(p))
            for p in source.iterdir()}
        return source,inventory

    def test_feature_is_selected_without_future_label_availability_and_exact_cycle_closes(self):
        source,inventory=self.source()
        market=RUN.load_market(BINARY,source,self.root/'fresh',1,inventory,'synthetic_fixture',time.monotonic()+30)
        self.assertEqual(market['feature']['monotonic_ns'],5010000000)
        self.assertEqual(market['feature']['prediction'],'up')
        # The one-second gap violates prediction-label cadence; entry eligibility
        # deliberately does not read that later label or require it to exist.
        plan=RUN.CORE.CYCLE.FROZEN.entry_scenario(market['feature'],RUN.CORE.PROFILES[0]['assumptions'])
        folder=self.root/'case';folder.mkdir()
        value=RUN.CYCLE.run_case(BINARY,market,plan,market['feature'],folder/'policy',time.monotonic()+30,folder)
        compact=RUN.compact(value)
        total=RUN.CORE.summarize([dict(child=1,profile='baseline',status='verified',policy=compact)])
        self.assertEqual(total['profiles'][0]['closed_cycle_net'],'-0.000140000001')
        self.assertEqual(compact['metrics']['ending_position_quantity'],'0')
        self.assertTrue(compact['causal_prefix_verified'])

    def test_no_directional_feature_is_retained_without_replacement(self):
        source,inventory=self.source(imbalance=False)
        market=RUN.load_market(BINARY,source,self.root/'fresh',1,inventory,'synthetic_fixture',time.monotonic()+30)
        self.assertIsNone(market['feature'])

    def test_source_inventory_mismatch_prevents_feature_admission(self):
        source,inventory=self.source();inventory[next(iter(inventory))]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source differs'):
            RUN.load_market(BINARY,source,self.root/'fresh',1,inventory,'synthetic_fixture',time.monotonic()+30)
