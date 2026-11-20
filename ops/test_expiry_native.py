import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

try:
    from . import expiry_local as RUN, test_cost_native as FIXTURE
except ImportError:
    import expiry_local as RUN
    import test_cost_native as FIXTURE

BINARY=FIXTURE.BINARY
POLICY_SHA=RUN.COST.CORE.fingerprint(dict(policy=RUN.COST.CORE.POLICY,profiles=RUN.COST.CORE.PROFILES,limits=RUN.COST.LIMITS))


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY,os.X_OK),'native binary required; set GIETHOORN_TEST_BINARY')
class ExpiryNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def prepare(self,name='sample',times=None,book=None,profile=None):
        root=self.root/name
        source,child=FIXTURE.recording(root,times,book)
        feature=RUN.COST.feature(1,child)
        original=RUN.REVIEW.inventory(source)
        report=root/'cost';report.mkdir()
        folder=report/'run-000001';folder.mkdir();RUN.REVIEW.save(folder/'feature.json',feature)
        profile=profile or RUN.COST.CORE.PROFILES[0]
        case_id='run-000001--'+profile['id']
        expected=dict(origin='synthetic_fixture',inventory=original,policy_sha256=POLICY_SHA)
        result=RUN.COST.run_case(BINARY,child/'session',feature,profile,report/case_id,expected,time.monotonic()+30)
        case=dict(id=case_id,child=1,profile=profile['id'],reason=None,**result)
        market=RUN.fresh_market(BINARY,report/case_id,root/'market-audit',1,original,'synthetic_fixture',time.monotonic()+30)
        return root,report,case,market

    def review(self,root,report,case,market,folder='diagnostic'):
        return RUN.case_review(BINARY,report/case['id'],case,market,root/folder,'synthetic_fixture',
                               POLICY_SHA,time.monotonic()+30)

    def test_saved_full_and_partial_fills_have_fresh_native_source_and_ledger_checks(self):
        root,report,case,market=self.prepare(book=lambda t:('99.99','100.01','0.02','0.002'))
        before=RUN.inventory(report)
        reviewed=self.review(root,report,case,market)
        self.assertEqual([o['classification'] for o in reviewed['orders']],['partial_fill_cancelled','filled'])
        self.assertEqual(reviewed['orders'][1]['requested_quantity'],'0.0005')
        self.assertEqual(RUN.inventory(report),before)
        self.assertFalse(reviewed['profit_reestimated'])

    def test_shifted_window_explains_a_later_quote_without_claiming_a_latency_benefit(self):
        times=list(range(10,5011,100))+[5410,6010,6310,6410]
        a=self.prepare('baseline',times=times)
        b=self.prepare('delayed',times=times,profile=RUN.COST.CORE.PROFILES[3])
        baseline=self.review(*a);delayed=self.review(*b)
        entry_a,entry_b=baseline['orders'][0],delayed['orders'][0]
        self.assertEqual(entry_a['classification'],'expired_no_opportunity')
        self.assertEqual(entry_b['classification'],'filled')
        self.assertEqual(entry_a['expiry_offset_ns'],'350000000')
        self.assertEqual(entry_b['expiry_offset_ns'],'500000000')
        self.assertEqual(entry_a['first_native_quote_at_or_after_arrival']['offset_ns'],'400000000')
        self.assertEqual(entry_a['native_opportunities_in_window'],0)
        self.assertEqual(entry_b['native_opportunities_in_window'],1)
        self.assertEqual(entry_a['component_cause'],'unknown')

    def test_source_end_retains_pending_order_and_emits_no_fake_expiry(self):
        args=self.prepare(times=range(10,5011,100))
        reviewed=self.review(*args)
        self.assertEqual(len(reviewed['orders']),1)
        self.assertEqual(reviewed['orders'][0]['classification'],'pending_at_source_end')
        self.assertEqual(reviewed['ending_pending_order_ids'],['entry'])

    def test_request_risk_rejection_is_not_relabelled_as_quote_expiry(self):
        args=self.prepare(book=lambda t:('100009.99','100010.01','0.02','0.004'))
        reviewed=self.review(*args)
        self.assertEqual(reviewed['orders'][0]['classification'],'request_rejected')
        self.assertNotIn('expired',reviewed['orders'][0]['classification'])

    def test_modified_saved_ledger_is_rejected_by_fresh_exact_replay(self):
        root,report,case,market=self.prepare()
        file=report/case['id']/'compiled/replay/paper-input.jsonl'
        rows=[json.loads(s) for s in file.read_text().splitlines()]
        next(r for r in rows if r['event']['type']=='order_requested')['event']['limit_price']='1'
        file.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        with self.assertRaises(ValueError):self.review(root,report,case,market)

    def test_original_feature_or_causal_prefix_cannot_be_replaced(self):
        root,report,case,market=self.prepare()
        case=copy.deepcopy(case);case['causal_prefix']['known_position']='0.002'
        with self.assertRaisesRegex(ValueError,'compiler receipt'):
            self.review(root,report,case,market)

    def test_derived_market_inputs_cannot_diverge_from_the_fresh_native_source(self):
        root,report,case,market=self.prepare()
        file=report/case['id']/'control/replay/paper-input.jsonl'
        rows=[json.loads(s) for s in file.read_text().splitlines()]
        next(row for row in rows if row['event']['type']=='market_observed')['event']['bid']='1'
        file.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        with self.assertRaisesRegex(ValueError,'derived market input'):
            self.review(root,report,case,market)

    def test_repeated_diagnostics_keep_exact_timing_and_classification(self):
        args=self.prepare()
        first=self.review(*args,folder='first');second=self.review(*args,folder='second')
        self.assertEqual(first,second)
