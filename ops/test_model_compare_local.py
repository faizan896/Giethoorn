"""Synthetic snapshot admission; real native model behavior is tested separately."""
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from . import model_compare_local as RUN,test_cost_local as FIXTURE
except ImportError:
    import model_compare_local as RUN
    import test_cost_local as FIXTURE


class ModelComparisonAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.seed=FIXTURE.CostAdmissionTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        def case(*args):
            result=self.seed.fake_case(*args)
            RUN.REVIEW.save(args[4]/'compiled-scenario.json',dict(scenario_version=1,orders=[dict(id='entry')]))
            return result
        self.seed.generate(callback=case)
        self.source=self.seed.output;self.output=self.seed.base/'comparison'
        self.template=self.seed.base/'comparison-template'
        self.template.write_text('__GIETHOORN_THEME__<script type="application/json">__QUALITY_BOOT__</script>')

    def market(self,*args):
        args[2].mkdir();return dict(synthetic_native_market=True)

    def old(self,*args):
        args[4].mkdir()
        return dict(status='verified',orders=[],reason=None)

    def proxy(self,*args):
        args[3].mkdir()
        return dict(model=RUN.CORE.POLICY['proxy_model'],ledger_kind='manual_simulation',actual_execution='unknown',
            native_checkpoints=1,prefixes_verified=True,orders=[dict(order=dict(id='entry'),reference_eligible=False)],
            metrics=dict(outcome='no_fills',conditional_closed_pnl=None,fees='0',ending_position_quantity='0',pending_order_ids=[]))

    def generate(self,market=None,old=None,proxy=None):
        with patch.object(RUN.ORIGINAL,'fresh_market',side_effect=market or self.market), \
             patch.object(RUN.ORIGINAL,'case_review',side_effect=old or self.old), \
             patch.object(RUN,'proxy',side_effect=proxy or self.proxy):
            return RUN.generate(self.seed.setup.binary,self.source,self.output,self.seed.setup.template,
                self.seed.cost_template,self.template,self.seed.setup.theme)

    def test_full_frozen_cohort_is_preserved_with_one_native_source_check_per_child(self):
        calls=[]
        def market(*args):calls.append(args[3]);return self.market(*args)
        report=self.generate(market=market)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(report['totals']['verified'],18)
        self.assertEqual(report['status'],'completed');self.assertTrue(report['input_unchanged'] and report['code_unchanged'])
        self.assertFalse(report['actual_execution_known'] or report['alternative_strategy_evaluated'] or report['historical_outcomes_changed'])

    def test_modified_bundle_is_refused_before_comparison_output(self):
        (self.source/'cost-policy.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):self.generate()
        self.assertFalse(self.output.exists())

    def test_unexpected_member_or_symlink_is_refused(self):
        (self.source/'extra').write_text('synthetic extra')
        with self.assertRaises(ValueError):self.generate()
        (self.source/'extra').unlink();(self.source/'link').symlink_to(self.seed.setup.binary)
        with self.assertRaisesRegex(ValueError,'symlink'):self.generate()

    def test_original_ledger_failure_prevents_proxy_without_replacement(self):
        calls=[]
        def fail(*args):
            if args[2]['id']=='run-000001--baseline':raise ValueError('synthetic original ledger mismatch')
            return self.old(*args)
        def proxy(*args):calls.append(1);return self.proxy(*args)
        report=self.generate(old=fail,proxy=proxy)
        self.assertEqual(len(calls),17);self.assertEqual(report['totals']['unavailable'],1)
        self.assertIsNone(report['cases'][0]['proxy'])

    def test_failed_source_is_unavailable_for_all_profiles_without_retry(self):
        calls=[]
        def fail(*args):calls.append(args[3]);raise ValueError('synthetic failed source')
        report=self.generate(market=fail)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(report['totals']['unavailable'],18)

    def test_proxy_failure_retains_case_and_continues_original_cohort(self):
        def fail(*args):
            if 'run-000001--baseline' in str(args[3]):raise ValueError('synthetic proxy bound')
            return self.proxy(*args)
        report=self.generate(proxy=fail)
        self.assertEqual(report['totals']['unavailable'],1);self.assertEqual(report['totals']['verified'],17)

    def test_mutated_input_invalidates_all_comparisons(self):
        def change(*args):
            result=self.proxy(*args);(self.source/'changed').write_text('synthetic mutation');return result
        report=self.generate(proxy=change)
        self.assertEqual(report['status'],'source_changed');self.assertEqual(report['totals']['verified'],0)
        self.assertTrue(all(c['proxy'] is None and c['historical'] is None for c in report['cases']))

    def test_changed_view_asset_invalidates_metrics_without_altering_original_bundle(self):
        def change(*args):
            result=self.proxy(*args);self.template.write_text('synthetic changed template');return result
        report=self.generate(proxy=change)
        self.assertEqual(report['status'],'source_changed');self.assertFalse(report['code_unchanged'])
        self.assertTrue(report['input_unchanged']);self.assertEqual(report['totals']['verified'],0)

    def test_budget_refusal_is_not_run_and_never_becomes_zero_profit(self):
        with patch.object(RUN,'admit',side_effect=ValueError('synthetic output budget')):report=self.generate()
        self.assertEqual(report['totals']['not_run'],18)
        self.assertTrue(all(c['proxy'] is None for c in report['cases']))

    def test_new_output_is_outside_source_and_cannot_overwrite(self):
        self.output=self.source/'inside'
        with self.assertRaisesRegex(ValueError,'outside'):self.generate()
        self.output=self.seed.base/'comparison';self.generate()
        with self.assertRaisesRegex(ValueError,'new'):self.generate()

    def test_a_changed_final_ledger_cannot_reproduce_a_native_prefix(self):
        path=self.seed.base/'prefix.jsonl';path.write_bytes(b'one\ntwo\n')
        receipt=dict(records=1,input=dict(bytes=4,sha256=RUN.hashlib.sha256(b'one\n').hexdigest()))
        path.write_bytes(b'bad\ntwo\n')
        with self.assertRaisesRegex(ValueError,'prefix'):RUN.verify_prefixes(path,[receipt],'input')
