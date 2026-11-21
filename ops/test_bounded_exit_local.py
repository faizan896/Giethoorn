"""Synthetic bounded-exit admission; real ledger checks have native fixtures."""
import copy
import fcntl
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from . import bounded_exit_local as RUN, test_study_local as FIXTURE, test_cost_local as COST_FIXTURE
    from .test_evaluation_core import policy
except ImportError:
    import bounded_exit_local as RUN
    import test_study_local as FIXTURE
    import test_cost_local as COST_FIXTURE
    from test_evaluation_core import policy

PROJECT=Path(__file__).resolve().parent.parent


def bounded_value():
    old=policy();value=copy.deepcopy(old)
    value.update(policy_id=RUN.CORE.POLICY['policy_id'],single_close_control=old,retry_prefix_verified=True,
        retry_prefix_audit=dict(status='verified',decision_available=True,prefix_records=12,prefix_sha256='synthetic'),
        retry_compilation=dict(status='already_flat',decision=dict(sequence=10,monotonic_ns='1200000000',quote_age_ns='0'),
            known_position='0',entry_filled_quantity='0.001',working_orders=0,risk_at_decision=dict(halted=False),
            prefix_records=12,prefix_sha256='synthetic',delay_from_first_request_ns='200000000',
            first_close_state=dict(id='close',status='filled',filled_quantity='0.001',cancel_pending=False)))
    value['metrics'].update(retry_requested_quantity=None,retry_quantity=None,retry_outcome=None,
        retry_decision_status='already_flat',retry_known_position='0',total_close_quantity='0.001')
    return value


class BoundedExitAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.seed=FIXTURE.LocalStudyTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        self.output=self.seed.base/'bounded-exit'
        self.template=self.seed.base/'bounded-template'
        self.template.write_text('__GIETHOORN_THEME__<script type="application/json">__QUALITY_BOOT__</script>')
        self.protocol=PROJECT/'docs/bounded-exit-plan.md'

    def fresh(self,*args):return dict(integrity='verified',source_unchanged=True)

    def market(self,*args):
        args[2].mkdir();return dict(feature=COST_FIXTURE.CostAdmissionTests.selected_feature(None,args[3],None))

    def case(self,*args):
        args[4].mkdir();return bounded_value()

    def generate(self,fresh=None,market=None,case=None):
        with patch.object(RUN.EVAL,'fresh_quality',side_effect=fresh or self.fresh), \
             patch.object(RUN.EVAL,'load_market',side_effect=market or self.market), \
             patch.object(RUN,'run_case',side_effect=case or self.case):
            return RUN.generate(self.seed.binary,self.seed.source,self.seed.quality,self.output,'synthetic_fixture',
                self.seed.template,self.seed.template,self.template,self.seed.theme,self.protocol)

    def test_fixed_whole_cohort_and_profiles_have_matching_separate_controls(self):
        calls=[]
        def market(*args):calls.append(args[3]);return self.market(*args)
        r=self.generate(market=market)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(r['selected_children'],[1,2,3])
        self.assertEqual(r['totals']['verified'],18);self.assertEqual(r['control_totals']['verified'],18)
        self.assertEqual(r['totals']['retry_requests'],0);self.assertEqual(r['status'],'completed')
        self.assertTrue(all(c['control']['policy_id']==RUN.CORE.CYCLE.POLICY['policy_id'] for c in r['cases']))
        self.assertTrue(all(p['conditional_closed_net_delta']=='0.0' for p in r['comparisons']))

    def test_feature_is_saved_before_case_and_existing_local_budget_is_preserved(self):
        def case(*args):
            self.assertTrue((self.output/'markets'/f'run-{args[3]["child"]:06d}'/'selected-feature.json').is_file())
            self.assertEqual(args[6],args[4].parent)
            return self.case(*args)
        self.generate(case=case)

    def test_no_signal_retains_all_six_cases_and_both_totals_are_unavailable(self):
        def market(*args):args[2].mkdir();return dict(feature=None)
        r=self.generate(market=market)
        self.assertEqual(r['totals']['no_signal'],18);self.assertEqual(r['control_totals']['no_signal'],18)
        self.assertEqual(r['status'],'completed')
        self.assertTrue(all(p['closed_cycle_net'] is None for p in r['totals']['profiles']))

    def test_source_failure_keeps_all_profiles_without_replacement(self):
        calls=[]
        def market(*args):
            calls.append(args[3])
            if args[3]==1:raise ValueError('synthetic source corruption')
            return self.market(*args)
        r=self.generate(market=market)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(r['totals']['unavailable'],6)
        self.assertEqual(r['control_totals']['unavailable'],6)
        self.assertTrue(all(p['closed_cycle_net'] is None for p in r['totals']['profiles']))

    def test_failed_case_does_not_leave_a_complete_total_or_replacement(self):
        def fail(*args):
            if args[3]['child']==1 and args[2]['assumptions']['fee_rate']=='0':raise ValueError('synthetic retry prefix mismatch')
            return self.case(*args)
        r=self.generate(case=fail)
        self.assertEqual(r['totals']['verified'],17);self.assertEqual(r['totals']['unavailable'],1)
        row=next(c for c in r['cases'] if c['status']=='unavailable')
        self.assertIsNone(row['control']);self.assertIsNone(row['policy'])
        self.assertIsNone(next(p for p in r['totals']['profiles'] if p['profile']=='zero-fee')['closed_cycle_net'])

    def test_case_budget_failure_leaves_every_planned_case_not_run(self):
        admit=RUN.admit
        def refuse(root,deadline,allowance):
            if allowance==RUN.LIMITS['case_allowance_bytes']:raise ValueError('synthetic global budget exhausted')
            return admit(root,deadline,allowance)
        with patch.object(RUN,'admit',side_effect=refuse):r=self.generate()
        self.assertEqual(r['totals']['not_run'],18);self.assertEqual(r['totals']['retry_requests'],0)
        self.assertTrue(all(c['control'] is None and c['policy'] is None for c in r['cases']))

    def test_fresh_archive_failure_prevents_case_execution(self):
        def fresh(*args):raise ValueError('synthetic native audit failed')
        r=self.generate(fresh=fresh)
        self.assertEqual(r['totals']['not_run'],18);self.assertEqual(r['totals']['verified'],0)

    def test_modified_source_is_refused_before_output(self):
        (self.seed.root/'extra').write_text('synthetic changed source')
        with self.assertRaisesRegex(ValueError,'source differs'):self.generate()
        self.assertFalse(self.output.exists())

    def test_source_mutation_invalidates_control_and_retry_metrics(self):
        def mutate(*args):
            value=self.case(*args);(self.seed.root/'mutation').write_text('synthetic mutation');return value
        r=self.generate(case=mutate)
        self.assertEqual(r['status'],'source_changed');self.assertEqual(r['totals']['verified'],0)
        self.assertTrue(all(c['control'] is None and c['policy'] is None for c in r['cases']))

    def test_quality_mutation_invalidates_all_completed_comparisons(self):
        def mutate(*args):
            value=self.case(*args);(self.seed.quality/'research-protocol.md').write_text('synthetic mutation');return value
        r=self.generate(case=mutate)
        self.assertFalse(r['quality_unchanged']);self.assertEqual(r['status'],'source_changed')
        self.assertTrue(all(p['conditional_closed_net_delta'] is None for p in r['comparisons']))

    def test_new_template_mutation_hides_both_sides(self):
        def mutate(*args):
            value=self.case(*args);self.template.write_text('synthetic changed asset');return value
        r=self.generate(case=mutate)
        self.assertTrue(r['source_unchanged']);self.assertFalse(r['code_unchanged'])
        self.assertEqual(r['totals']['verified'],0)

    def test_protocol_change_before_or_during_run_is_detected(self):
        self.protocol=self.seed.base/'protocol';self.protocol.write_bytes((PROJECT/'docs/bounded-exit-plan.md').read_bytes())
        def mutate(*args):
            value=self.case(*args);self.protocol.write_text('synthetic changed protocol');return value
        r=self.generate(case=mutate)
        self.assertFalse(r['code_unchanged']);self.assertEqual(r['totals']['verified'],0)
        self.output=self.seed.base/'second'
        with self.assertRaisesRegex(ValueError,'protocol differs'):self.generate()
        self.assertFalse(self.output.exists())

    def test_changed_installed_binary_is_refused_before_output(self):
        self.seed.binary=Path('/usr/bin/false')
        with self.assertRaisesRegex(ValueError,'verifier version'):self.generate()
        self.assertFalse(self.output.exists())

    def test_binary_mutation_after_pin_invalidates_both_sides(self):
        binary=self.seed.base/'installed.bin';binary.write_bytes(self.seed.binary.read_bytes());binary.chmod(0o700)
        self.seed.binary=binary
        def mutate(*args):
            value=self.case(*args);binary.write_bytes(b'synthetic changed binary');return value
        r=self.generate(case=mutate)
        self.assertFalse(r['code_unchanged']);self.assertEqual(r['totals']['verified'],0)

    def test_active_supervisor_is_refused_before_output(self):
        with (self.seed.root/'supervisor.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'supervisor is active'):self.generate()
        self.assertFalse(self.output.exists())

    def test_output_cannot_overwrite_or_nest_in_any_original_input(self):
        for output in (self.seed.source/'inside',self.seed.quality/'inside'):
            self.output=output
            with self.assertRaisesRegex(ValueError,'outside'):self.generate()
        self.output=self.seed.base/'bounded-exit';self.generate()
        with self.assertRaisesRegex(ValueError,'new'):self.generate()

    def test_separate_audit_inventory_binds_all_retained_files(self):
        r=self.generate();receipt=r['provenance']['audit_inventory'];path=self.output/receipt['file']
        self.assertEqual(RUN.REVIEW.digest(path),receipt['sha256'])
        inventory=RUN.REVIEW.read_json(path)['files'];self.assertEqual(len(inventory),receipt['files'])
        for name,digest in inventory.items():self.assertEqual(RUN.REVIEW.digest(self.output/name),digest)


class BoundedExitEconomicsTests(unittest.TestCase):
    def row(self,child=1,status='verified'):
        value=bounded_value()
        return dict(case_id=f'synthetic-{child}',child=child,profile='baseline',status=status,
            policy=RUN.compact(value) if status=='verified' else None,
            control=RUN.EVAL.compact(value['single_close_control']) if status=='verified' else None)

    def test_closed_to_closed_uses_exact_conditional_delta(self):
        c=self.row();c['policy']['metrics'].update(conditional_closed_pnl='-0.100000000000000001',fees='0.010000000000000001')
        new,old,pairs=RUN.CORE.summarize([c])
        self.assertEqual(pairs[0]['conditional_closed_net_delta'],'-1E-18')
        self.assertEqual(pairs[0]['fee_delta'],'1E-18')
        self.assertEqual(new['profiles'][0]['closed_cycle_net'],'-0.100000000000000001')

    def test_unresolved_case_keeps_new_total_unavailable_after_one_retry(self):
        a=self.row();b=self.row(2)
        b['policy']['metrics'].update(conditional_closed_pnl=None,ending_position_quantity='0.0005',
            outcome='open_exposure',retry_requested_quantity='0.00075',retry_quantity='0.00025')
        b['control']['metrics'].update(conditional_closed_pnl=None,ending_position_quantity='0.00075',outcome='open_exposure')
        new,old,pairs=RUN.CORE.summarize([a,b])
        self.assertIsNone(new['profiles'][0]['closed_cycle_net']);self.assertIsNone(old['profiles'][0]['closed_cycle_net'])
        self.assertEqual(new['retry_requests'],1);self.assertEqual(new['profiles'][0]['unresolved_to_unresolved'],1)
        self.assertIsNone(pairs[1]['conditional_closed_net_delta'])

    def test_unverified_case_cannot_retain_control_metrics(self):
        c=self.row();c.update(status='unavailable',policy=None)
        with self.assertRaisesRegex(ValueError,'control metrics'):RUN.CORE.summarize([c])

    def test_failed_case_prevents_profile_totals_on_both_sides(self):
        new,old,pairs=RUN.CORE.summarize([self.row(),self.row(2,status='not_run')])
        self.assertIsNone(new['profiles'][0]['closed_cycle_net']);self.assertIsNone(old['profiles'][0]['closed_cycle_net'])
        self.assertIsNone(pairs[1]['fee_delta']);self.assertEqual(new['not_run'],1)
