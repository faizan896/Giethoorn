"""Synthetic admission/mutation orchestration; native checks have separate tests."""
import contextlib
import copy
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

try:
    from . import momentum_explain_local as DIAG, test_momentum_local as FIXTURE
    from .test_bounded_exit_local import bounded_value
    from .test_momentum_core import timeline
except ImportError:
    import momentum_explain_local as DIAG
    import test_momentum_local as FIXTURE
    from test_bounded_exit_local import bounded_value
    from test_momentum_core import timeline

PROJECT=Path(__file__).resolve().parent.parent


class DiagnosticAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.seed=FIXTURE.MomentumAdmissionTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        with contextlib.redirect_stdout(io.StringIO()): self.original=self.seed.generate()
        self.source=self.seed.output;self.output=self.source.parent/'diagnostic'
        self.assets=dict(quality_template=self.seed.seed.template,cost_template=self.seed.seed.template,
            momentum_template=self.seed.template,theme=self.seed.seed.theme,original_protocol=self.seed.protocol,
            policy_spec=self.seed.spec,protocol=PROJECT/'docs/momentum-explain-plan.md',template=PROJECT/'web/momentum-explain.html')
        self.binary=self.seed.seed.binary

    def fake_market(self,*args):
        child=args[3];selection=DIAG.RUN.CORE.select(timeline(),child)
        return dict(feature=selection['feature'],selection=selection,label=dict(status='unavailable',reason='synthetic')),dict(status='synthetic_orchestration')

    def fake_case(self,*args):
        v=bounded_value();v['policy_id']=DIAG.RUN.CORE.POLICY['experiment_id']
        return v,dict(synthetic_orchestration=True,closed_decomposition=None),dict(ledgers={},cost_identity_verified=False)

    def generate(self,market=None,case=None):
        with patch.object(DIAG,'verify_market',side_effect=market or self.fake_market),\
             patch.object(DIAG,'verify_case',side_effect=case or self.fake_case),contextlib.redirect_stdout(io.StringIO()):
            return DIAG.generate(self.binary,self.source,self.output,self.assets)

    def write_report(self,value):
        (self.source/'momentum-report.json').write_text(json.dumps(value))

    def test_frozen_membership_and_original_classification_are_preserved(self):
        before=DIAG.inventory(self.source,time.monotonic()+10);r=self.generate()
        self.assertEqual(r['status'],'completed');self.assertEqual(len(r['cases']),18)
        self.assertEqual(r['selected_children'],[1,2,3]);self.assertEqual(r['original_screen'],self.original['screen'])
        self.assertEqual(before,DIAG.inventory(self.source,time.monotonic()+10));self.assertTrue(r['input_unchanged'])

    def test_changed_artifact_or_unbound_extra_is_refused_before_output(self):
        (self.source/'momentum-policy.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'artifact fingerprint'):self.generate()
        self.assertFalse(self.output.exists())

    def test_extra_unbound_file_cannot_join_completed_bundle(self):
        (self.source/'extra').write_text('synthetic')
        with self.assertRaisesRegex(ValueError,'unbound'):self.generate()
        self.assertFalse(self.output.exists())

    def test_inventory_traversal_and_symlinks_are_refused(self):
        for name in ('../outside','/outside','x/../outside','x//outside','x\\outside'):
            with self.assertRaises(ValueError):DIAG.path_in(self.source,name)
        (self.source/'link').symlink_to(self.source/'momentum-policy.json')
        with self.assertRaisesRegex(ValueError,'symlink'):self.generate()

    def test_duplicate_json_and_nonfinite_metadata_are_refused(self):
        for raw in ('{"status":"completed","status":"invalid"}','{"value":NaN}'):
            (self.source/'momentum-report.json').write_text(raw)
            with self.assertRaises(ValueError):self.generate()

    def test_incomplete_or_changed_original_scope_is_refused(self):
        for field,value in [('status','incomplete'),('verification_failed',True),('source_unchanged',False),('live_orders_enabled',True)]:
            r=copy.deepcopy(self.original);r[field]=value;self.write_report(r)
            with self.assertRaises(ValueError):self.generate()

    def test_changed_totals_or_case_membership_are_refused(self):
        for field,value in [('totals',{}),('cases',self.original['cases'][:-1]),('selected_children',[1])]:
            r=copy.deepcopy(self.original);r[field]=value;self.write_report(r)
            with self.assertRaises(ValueError):self.generate()

    def test_copied_binary_is_never_used_as_installed_executable(self):
        replacement=self.source.parent/'different-executable';replacement.write_text('#!/bin/sh\nexit 0\n');replacement.chmod(0o700)
        self.binary=replacement
        with self.assertRaisesRegex(ValueError,'installed original executable'):self.generate()

    def test_matching_copied_bundle_binary_is_also_refused_as_executable(self):
        self.binary=self.source/'replay.bin'
        with self.assertRaisesRegex(ValueError,'never execute an evidence-bundle binary'):self.generate()
        self.assertFalse(self.output.exists())

    def test_mutating_original_report_during_checks_invalidates_all_analysis(self):
        def case(*args):
            result=self.fake_case(*args)
            (self.source/'momentum-report.json').write_text(json.dumps(self.original)+' ')
            return result
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertFalse(r['input_unchanged'])
        self.assertTrue(all(c['explanation'] is None and c['status']=='unavailable' for c in r['cases']))

    def test_mutating_original_producer_asset_invalidates_all_analysis(self):
        def case(*args):
            result=self.fake_case(*args);self.seed.template.write_text('synthetic mutation');return result
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertFalse(r['code_unchanged'])
        self.assertTrue(all(c['explanation'] is None for c in r['cases']))

    def test_failed_native_check_keeps_failure_receipt_and_no_partial_economics(self):
        def fail(*args):raise ValueError('synthetic replay mismatch')
        r=self.generate(case=fail);self.assertEqual(r['status'],'invalid');self.assertIn('replay mismatch',r['error'])
        self.assertTrue((self.output/'momentum-explain-report.json').is_file())
        self.assertTrue(all(c['explanation'] is None for c in r['cases']))

    def test_budget_and_timeout_failures_keep_original_case_denominators(self):
        with patch.object(DIAG,'admit',side_effect=ValueError('synthetic budget exhausted')):r=self.generate()
        self.assertEqual(r['status'],'invalid');self.assertEqual(len(r['cases']),18);self.assertTrue(r['input_unchanged'])

    def test_output_inside_source_and_existing_output_are_refused(self):
        self.output=self.source/'nested'
        with self.assertRaisesRegex(ValueError,'outside original'):self.generate()
        self.output=self.source.parent/'already';self.output.mkdir()
        with self.assertRaises(ValueError):self.generate()

    def test_input_size_bound_is_enforced_without_truncation(self):
        with patch.dict(DIAG.LIMITS,max_files=2):
            with self.assertRaisesRegex(ValueError,'bounds'):self.generate()

    def test_new_contract_hash_is_pinned_independently_of_frozen_r002(self):
        self.assertEqual(DIAG.REVIEW.digest(self.assets['protocol']),DIAG.PROTOCOL_SHA256)
        self.assertEqual(DIAG.REVIEW.digest(PROJECT/'docs/r002-cost-momentum-plan.md'),DIAG.RUN.CORE.PROTOCOL_SHA256)
        self.assertEqual(DIAG.REVIEW.digest(PROJECT/'docs/r002-cost-momentum-policy.json'),DIAG.RUN.CORE.POLICY_SHA256)


if __name__=='__main__':unittest.main()
