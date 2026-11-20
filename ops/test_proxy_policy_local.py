"""Synthetic admission tests; causal ledger behavior has independent native cases."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from . import proxy_policy_local as RUN,test_cost_local as FIXTURE
except ImportError:
    import proxy_policy_local as RUN
    import test_cost_local as FIXTURE


class CausalProxyAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.seed=FIXTURE.CostAdmissionTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        self.features={}
        def case(*args):
            result=self.seed.fake_case(*args)
            self.features[args[2]['child']]=copy.deepcopy(args[2])
            entry=RUN.CORE.FROZEN.entry_scenario(args[2],args[3]['assumptions'])
            RUN.REVIEW.save(args[4]/'entry-scenario.json',entry)
            return result
        self.seed.generate(callback=case)
        self.source=self.seed.output;self.output=self.seed.base/'policy'
        self.template=self.seed.base/'policy-template'
        self.template.write_text('__GIETHOORN_THEME__<script type="application/json">__QUALITY_BOOT__</script>')

    def market(self,*args):
        args[2].mkdir();return dict(feature=self.features[args[3]])

    def original(self,*args):
        args[4].mkdir();return dict(status='verified')

    def policy(self,*args):
        args[4].mkdir()
        return dict(causal_proxy_policy_version=1,policy_id=RUN.CORE.POLICY['policy_id'],status='verified',
            actual_execution='unknown',causal_prefix_verified=True,control_reused=False,orders=[],
            metrics=dict(outcome='closed_under_assumptions',entry_quantity='0.001',close_decision_status='close_compiled',
                known_position_at_decision='0.001',close_requested_quantity='0.001',close_quantity='0.001',
                close_outcome='filled',conditional_closed_pnl='-0.1',fees='0.01',ending_position_quantity='0',pending_order_ids=[]))

    def generate(self,market=None,original=None,policy=None):
        with patch.object(RUN.ORIGINAL,'fresh_market',side_effect=market or self.market), \
             patch.object(RUN.ORIGINAL,'case_review',side_effect=original or self.original), \
             patch.object(RUN,'run_case',side_effect=policy or self.policy):
            return RUN.generate(self.seed.setup.binary,self.source,self.output,self.seed.setup.template,
                self.seed.cost_template,self.template,self.seed.setup.theme)

    def test_original_cohort_and_profiles_remain_fixed_without_source_replacements(self):
        calls=[]
        def market(*args):calls.append(args[3]);return self.market(*args)
        report=self.generate(market=market)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(report['totals']['verified'],18)
        self.assertEqual(report['totals']['entry_requests'],18);self.assertEqual(report['totals']['close_requests'],18)
        self.assertTrue(report['input_unchanged'] and report['code_unchanged'])
        self.assertFalse(report['actual_execution_known'] or report['live_orders_enabled'] or report['portfolio_profit_evaluated'])

    def test_modified_original_bundle_is_refused_before_new_policy_output(self):
        (self.source/'cost-policy.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):self.generate()
        self.assertFalse(self.output.exists())

    def test_extra_members_and_symlinks_cannot_be_silently_ignored(self):
        (self.source/'extra').write_text('synthetic unexpected member')
        with self.assertRaises(ValueError):self.generate()
        (self.source/'extra').unlink();(self.source/'link').symlink_to(self.seed.setup.binary)
        with self.assertRaisesRegex(ValueError,'symlink'):self.generate()

    def test_original_ledger_failure_prevents_policy_run(self):
        calls=[]
        def fail(*args):
            if args[2]['id']=='run-000001--baseline':raise ValueError('synthetic original ledger mismatch')
            return self.original(*args)
        def policy(*args):calls.append(1);return self.policy(*args)
        report=self.generate(original=fail,policy=policy)
        self.assertEqual(len(calls),17);self.assertEqual(report['totals']['unavailable'],1)
        self.assertIsNone(report['cases'][0]['policy'])

    def test_source_failure_marks_every_profile_without_retry(self):
        calls=[]
        def fail(*args):calls.append(args[3]);raise ValueError('synthetic source corruption')
        report=self.generate(market=fail)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(report['totals']['unavailable'],18)

    def test_control_or_compiled_failure_is_retained_and_other_cases_continue(self):
        def fail(*args):
            if 'run-000001--baseline' in str(args[4]):raise ValueError('synthetic causal prefix failure')
            return self.policy(*args)
        report=self.generate(policy=fail)
        self.assertEqual(report['totals']['unavailable'],1);self.assertEqual(report['totals']['verified'],17)

    def test_source_mutation_invalidates_previously_completed_policy_cases(self):
        def mutate(*args):
            result=self.policy(*args);(self.source/'changed').write_text('synthetic mutation');return result
        report=self.generate(policy=mutate)
        self.assertEqual(report['status'],'source_changed');self.assertEqual(report['totals']['verified'],0)
        self.assertTrue(all(c['policy'] is None for c in report['cases']))

    def test_new_template_change_invalidates_all_metrics_and_preserves_original_input(self):
        def mutate(*args):
            result=self.policy(*args);self.template.write_text('synthetic changed asset');return result
        report=self.generate(policy=mutate)
        self.assertEqual(report['status'],'source_changed');self.assertFalse(report['code_unchanged'])
        self.assertTrue(report['input_unchanged']);self.assertEqual(report['totals']['verified'],0)

    def test_budget_refusal_stays_not_run_with_unavailable_policy_metrics(self):
        with patch.object(RUN,'admit',side_effect=ValueError('synthetic output budget')):report=self.generate()
        self.assertEqual(report['totals']['not_run'],18)
        self.assertTrue(all(c['policy'] is None for c in report['cases']))

    def test_output_is_new_and_outside_original_bundle(self):
        self.output=self.source/'inside'
        with self.assertRaisesRegex(ValueError,'outside'):self.generate()
        self.output=self.seed.base/'policy';self.generate()
        with self.assertRaisesRegex(ValueError,'new'):self.generate()
