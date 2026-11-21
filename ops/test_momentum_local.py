"""R002 frozen source/spec admission; native arithmetic has separate fixtures."""
import copy
import fcntl
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from . import momentum_local as RUN, test_study_local as FIXTURE
    from .test_bounded_exit_local import bounded_value
    from .test_momentum_core import timeline
except ImportError:
    import momentum_local as RUN
    import test_study_local as FIXTURE
    from test_bounded_exit_local import bounded_value
    from test_momentum_core import timeline

PROJECT=Path(__file__).resolve().parent.parent


class MomentumAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.seed=FIXTURE.LocalStudyTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        self.output=self.seed.base/'momentum'
        self.template=self.seed.base/'momentum-template';self.template.write_text('__GIETHOORN_THEME____QUALITY_BOOT__')
        self.protocol=self.seed.base/'protocol';self.protocol.write_bytes((PROJECT/'docs/r002-cost-momentum-plan.md').read_bytes())
        self.spec=self.seed.base/'policy.json';self.spec.write_bytes((PROJECT/'docs/r002-cost-momentum-policy.json').read_bytes())

    def market(self,*args):
        output=args[2];output.mkdir();selection=RUN.CORE.select(timeline(),args[3])
        RUN.REVIEW.save(output/'selected-feature.json',RUN.ORIGINAL.CORE.stamps(selection['feature']))
        return dict(feature=selection['feature'],selection=selection,label=dict(status='unavailable',reason='synthetic'),
            selection_folder=output,selection_hashes={'selected-feature.json':RUN.REVIEW.digest(output/'selected-feature.json')})

    def case(self,*args):
        args[4].mkdir();value=bounded_value();value['policy_id']=RUN.CORE.POLICY['experiment_id'];return value

    def generate(self,fresh=None,market=None,case=None):
        with patch.object(RUN.EVAL,'fresh_quality',side_effect=fresh or (lambda *a:dict(integrity='verified',source_unchanged=True))),\
             patch.object(RUN,'load_market',side_effect=market or self.market),patch.object(RUN,'run_case',side_effect=case or self.case):
            return RUN.generate(self.seed.binary,self.seed.source,self.seed.quality,self.output,'synthetic_fixture',
                self.seed.template,self.seed.template,self.template,self.seed.theme,self.protocol,self.spec)

    def test_all_frozen_children_and_six_profiles_keep_complete_denominators(self):
        r=self.generate();self.assertEqual(r['status'],'completed');self.assertEqual(r['selected_children'],[1,2,3])
        self.assertEqual(r['totals']['verified'],18);self.assertEqual(r['screen']['classification'],'insufficient_data')
        self.assertTrue(all(c['policy']['policy_id']==RUN.CORE.POLICY['experiment_id'] for c in r['cases']))

    def test_feature_snapshot_exists_before_cases_and_is_never_overwritten(self):
        def case(*args):
            p=self.output/'markets'/f'run-{args[3]["child"]:06d}'/'selected-feature.json'
            self.assertEqual(RUN.ORIGINAL.obj(p),RUN.ORIGINAL.CORE.stamps(args[3]))
            self.assertEqual(args[6],args[4].parent)
            return self.case(*args)
        self.generate(case=case)

    def test_no_signal_retains_six_slots_with_unknown_net_and_no_orders(self):
        def market(*args):
            m=self.market(*args);m['feature']=None;return m
        r=self.generate(market=market);self.assertEqual(r['totals']['no_signal'],18)
        self.assertEqual(r['totals']['entry_requests'],0);self.assertEqual(r['status'],'completed')
        self.assertTrue(all(p['closed_cycle_net'] is None for p in r['totals']['profiles']))

    def test_native_verification_failure_invalidates_all_economics_without_replacement(self):
        def case(*args):
            if args[3]['child']==1:raise ValueError('synthetic native prefix mismatch')
            return self.case(*args)
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertEqual(r['totals']['unavailable'],18)
        self.assertEqual(r['screen']['classification'],'invalid');self.assertTrue(all(c['policy'] is None for c in r['cases']))

    def test_budget_refusal_keeps_planned_slots_not_run(self):
        admit=RUN.admit
        def refuse(root,deadline,allowance):
            if allowance==RUN.LIMITS['case_allowance_bytes']:raise RUN.AdmissionError('synthetic case budget exhausted')
            return admit(root,deadline,allowance)
        with patch.object(RUN,'admit',side_effect=refuse):r=self.generate()
        self.assertEqual(r['totals']['not_run'],18);self.assertEqual(r['screen']['classification'],'incomplete')

    def test_initial_suite_admission_refusal_is_incomplete_not_an_economic_result(self):
        with patch.object(RUN,'admit',side_effect=RUN.AdmissionError('synthetic budget exhausted')):r=self.generate()
        self.assertEqual(r['status'],'incomplete');self.assertEqual(r['screen']['classification'],'incomplete')

    def test_fresh_archive_failure_stops_economic_admission(self):
        def fresh(*args):raise ValueError('synthetic archive mismatch')
        r=self.generate(fresh=fresh);self.assertEqual(r['status'],'invalid');self.assertEqual(r['totals']['verified'],0)

    def test_changed_original_source_is_refused_before_output(self):
        (self.seed.root/'mutation').write_text('synthetic changed source')
        with self.assertRaisesRegex(ValueError,'source differs'):self.generate()
        self.assertFalse(self.output.exists())

    def test_source_mutation_during_execution_invalidates_metrics(self):
        def case(*args):
            v=self.case(*args);(self.seed.root/'mutation').write_text('synthetic mutation');return v
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertFalse(r['source_unchanged'])
        self.assertTrue(all(c['policy'] is None for c in r['cases']))

    def test_quality_mutation_invalidates_every_completed_metric(self):
        def case(*args):
            v=self.case(*args);(self.seed.quality/'research-protocol.md').write_text('synthetic changed quality');return v
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertFalse(r['quality_unchanged'])
        self.assertEqual(r['totals']['verified'],0)

    def test_producer_template_mutation_invalidates_native_results(self):
        def case(*args):
            v=self.case(*args);self.template.write_text('synthetic changed producer');return v
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertFalse(r['code_unchanged'])

    def test_changed_selected_feature_cannot_be_replaced_after_forward_outcome(self):
        def case(*args):
            v=self.case(*args)
            (self.output/'markets'/f'run-{args[3]["child"]:06d}'/'selected-feature.json').write_text('{}')
            return v
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertEqual(r['totals']['verified'],0)

    def test_policy_or_protocol_drift_is_refused_before_output(self):
        self.spec.write_text('{}')
        with self.assertRaisesRegex(ValueError,'specification differs'):self.generate()
        self.assertFalse(self.output.exists())

    def test_policy_mutation_during_execution_invalidates_new_metrics(self):
        def case(*args):
            v=self.case(*args);self.spec.write_text('{}');return v
        r=self.generate(case=case);self.assertEqual(r['status'],'invalid');self.assertFalse(r['code_unchanged'])

    def test_active_source_lock_is_refused_before_output(self):
        with (self.seed.root/'supervisor.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'supervisor is active'):self.generate()
        self.assertFalse(self.output.exists())

    def test_output_inside_original_inputs_is_refused(self):
        self.output=self.seed.source/'bad-output'
        with self.assertRaisesRegex(ValueError,'outside original evidence'):self.generate()

    def test_artifact_inventory_binds_selection_policy_and_native_receipts(self):
        r=self.generate();bound=r['provenance']['audit_inventory']
        self.assertEqual(RUN.REVIEW.digest(self.output/bound['file']),bound['sha256'])
        inventory=RUN.ORIGINAL.obj(self.output/bound['file'])['files']
        self.assertEqual(bound['files'],len(inventory))
        self.assertIn('momentum-policy.json',inventory);self.assertIn('markets/run-000001/selected-feature.json',inventory)
        for name,sha in inventory.items():self.assertEqual(RUN.REVIEW.digest(self.output/name),sha)

    def test_repeat_case_results_and_original_inputs_are_unchanged(self):
        before=RUN.REVIEW.inventory(self.seed.source);a=self.generate();self.output=self.seed.base/'repeat';b=self.generate()
        self.assertEqual(a['cases'],b['cases']);self.assertEqual(a['totals'],b['totals']);self.assertEqual(a['screen'],b['screen'])
        self.assertEqual(before,RUN.REVIEW.inventory(self.seed.source))


if __name__=='__main__':unittest.main()
