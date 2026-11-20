"""Synthetic admission checks; native integration is exercised separately."""
import copy
import fcntl
from pathlib import Path
import time
import unittest
from unittest.mock import patch

try:
    from . import evaluation_local as RUN, test_study_local as FIXTURE, test_cost_local as COST_FIXTURE
    from .test_evaluation_core import policy
except ImportError:
    import evaluation_local as RUN
    import test_study_local as FIXTURE
    import test_cost_local as COST_FIXTURE
    from test_evaluation_core import policy

PROJECT=Path(__file__).resolve().parent.parent


class DevelopmentEvaluationAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.seed=FIXTURE.LocalStudyTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        self.output=self.seed.base/'evaluation'
        self.template=self.seed.base/'evaluation-template'
        self.template.write_text('__GIETHOORN_THEME__<script type="application/json">__QUALITY_BOOT__</script>')
        self.protocol=PROJECT/'docs/development-evaluation-plan.md'

    def fresh(self,*args):
        return dict(integrity='verified',source_unchanged=True)

    def market(self,*args):
        args[2].mkdir()
        value=COST_FIXTURE.CostAdmissionTests.selected_feature(None,args[3],None)
        return dict(feature=value)

    def cycle(self,*args):
        args[4].mkdir()
        return policy()

    def generate(self,fresh=None,market=None,cycle=None):
        with patch.object(RUN,'fresh_quality',side_effect=fresh or self.fresh), \
             patch.object(RUN,'load_market',side_effect=market or self.market), \
             patch.object(RUN.CYCLE,'run_case',side_effect=cycle or self.cycle):
            return RUN.generate(self.seed.binary,self.seed.source,self.seed.quality,self.output,'synthetic_fixture',
                self.seed.template,self.seed.template,self.template,self.seed.theme,self.protocol)

    def test_all_frozen_development_children_and_profiles_are_retained_in_order(self):
        calls=[]
        def market(*args):calls.append(args[3]);return self.market(*args)
        r=self.generate(market=market)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(r['selected_children'],[1,2,3])
        self.assertEqual(r['totals']['verified'],18);self.assertEqual(r['status'],'completed')
        self.assertTrue(all(r[k] for k in ('source_unchanged','quality_unchanged','code_unchanged')))
        self.assertTrue(all(row['status']=='not_run' for row in r['rows'] if not row['selected']))

    def test_feature_is_persisted_before_profiles_and_existing_per_case_admission_stays_enabled(self):
        def cycle(*args):
            child=args[3]['child']
            self.assertTrue((self.output/'markets'/f'run-{child:06d}'/'selected-feature.json').is_file())
            self.assertEqual(args[6],args[4].parent)
            return self.cycle(*args)
        self.generate(cycle=cycle)

    def test_separate_audit_inventory_binds_every_retained_artifact_without_expanding_html(self):
        r=self.generate();receipt=r['provenance']['audit_inventory']
        path=self.output/receipt['file']
        self.assertEqual(receipt['sha256'],RUN.REVIEW.digest(path))
        inventory=RUN.REVIEW.read_json(path)
        self.assertEqual(inventory['audit_inventory_version'],1)
        self.assertEqual(len(inventory['files']),receipt['files'])
        for name,digest in inventory['files'].items():self.assertEqual(RUN.REVIEW.digest(self.output/name),digest)
        self.assertNotIn('audit_hashes',r['provenance'])

    def test_no_signal_stays_selected_across_six_profiles_without_replacement(self):
        calls=[]
        def market(*args):calls.append(args[3]);args[2].mkdir();return dict(feature=None)
        r=self.generate(market=market)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(r['totals']['no_signal'],18)
        self.assertTrue(all(p['closed_cycle_net'] is None for p in r['totals']['profiles']))

    def test_source_failure_marks_all_profiles_and_does_not_change_cohort(self):
        calls=[]
        def market(*args):
            calls.append(args[3])
            if args[3]==1:raise ValueError('synthetic corrupt source')
            return self.market(*args)
        r=self.generate(market=market)
        self.assertEqual(calls,[1,2,3]);self.assertEqual(r['totals']['unavailable'],6)
        self.assertEqual(r['totals']['verified'],12)
        self.assertTrue(all(p['closed_cycle_net'] is None for p in r['totals']['profiles']))

    def test_native_case_failure_retains_other_profiles_without_financial_total_for_failed_profile(self):
        def cycle(*args):
            if args[3]['child']==1 and args[2]['assumptions']['fee_rate']=='0':raise ValueError('synthetic native failure')
            return self.cycle(*args)
        r=self.generate(cycle=cycle)
        self.assertEqual(r['totals']['verified'],17);self.assertEqual(r['totals']['unavailable'],1)
        self.assertIsNone(next(p for p in r['totals']['profiles'] if p['profile']=='zero-fee')['closed_cycle_net'])
        self.assertIsNotNone(r['totals']['profiles'][0]['closed_cycle_net'])

    def test_case_budget_refusal_preserves_every_not_run_case(self):
        admit=RUN.admit
        def refuse(root,deadline,allowance):
            if allowance==RUN.LIMITS['case_allowance_bytes']:raise ValueError('synthetic budget exhausted')
            return admit(root,deadline,allowance)
        with patch.object(RUN,'admit',side_effect=refuse):r=self.generate()
        self.assertEqual(r['totals']['not_run'],18)
        self.assertTrue(all(p['closed_cycle_net'] is None for p in r['totals']['profiles']))

    def test_fresh_quality_failure_never_admits_cases(self):
        def fail(*args):raise ValueError('synthetic fresh archive mismatch')
        r=self.generate(fresh=fail)
        self.assertEqual(r['totals']['not_run'],18);self.assertEqual(r['status'],'incomplete')

    def test_fresh_quality_rejects_forged_candidate_membership_even_when_envelopes_match(self):
        manifest=copy.deepcopy(self.seed.manifest)
        expected=RUN.REVIEW.inventory(self.seed.source)
        native=dict(runs=[dict(run=n,directory=f'run-{n:06d}',finalized=True) for n in range(1,7)])
        for n in range(1,7):
            RUN.REVIEW.save(self.seed.root/f'run-{n:06d}'/'inspection.json',dict(session=dict(feeds=None)))
        def audit(binary,experiment,output,timeout_seconds):
            self.assertLessEqual(timeout_seconds,30)
            output.mkdir();RUN.REVIEW.save(output/'audit.stdout.json',native)
            RUN.REVIEW.save(output/'source-before.json',expected)
            manifest['audit_output_sha256']=RUN.REVIEW.digest(output/'audit.stdout.json')
            return dict(integrity='verified',source_unchanged=True)
        with patch.object(RUN.REVIEW,'review',side_effect=audit):
            with self.assertRaisesRegex(ValueError,'candidate membership differ'):
                RUN.fresh_quality(self.seed.binary,self.seed.source,self.seed.base/'fresh',
                    self.seed.report,manifest,expected,time.monotonic()+30)

    def test_fresh_native_audit_cannot_claim_integrity_when_it_failed(self):
        with patch.object(RUN.REVIEW,'review',return_value=dict(integrity='unverified',source_unchanged=True)):
            with self.assertRaisesRegex(ValueError,'unverified'):
                RUN.fresh_quality(self.seed.binary,self.seed.source,self.seed.base/'fresh',
                    self.seed.report,self.seed.manifest,{},time.monotonic()+30)

    def test_changed_source_is_refused_before_output(self):
        (self.seed.root/'extra').write_text('synthetic changed source')
        with self.assertRaisesRegex(ValueError,'source differs'):self.generate()
        self.assertFalse(self.output.exists())

    def test_source_or_quality_mutation_invalidates_all_completed_metrics(self):
        for name in ('source','quality'):
            with self.subTest(name=name):
                def mutate(*args):
                    result=self.cycle(*args)
                    if name=='source':(self.seed.root/'mutation').write_text('synthetic mutation')
                    else:(self.seed.quality/'research-protocol.md').write_text('synthetic mutation')
                    return result
                r=self.generate(cycle=mutate)
                self.assertEqual(r['status'],'source_changed');self.assertEqual(r['totals']['verified'],0)
                self.assertTrue(all(c['policy'] is None for c in r['cases']))
                if name=='source':(self.seed.root/'mutation').unlink()
                self.output=self.seed.base/'second-evaluation'

    def test_new_template_mutation_invalidates_metrics_without_changing_source(self):
        def mutate(*args):
            result=self.cycle(*args);self.template.write_text('synthetic changed template');return result
        r=self.generate(cycle=mutate)
        self.assertEqual(r['status'],'source_changed');self.assertTrue(r['source_unchanged'])
        self.assertFalse(r['code_unchanged']);self.assertEqual(r['totals']['verified'],0)

    def test_protocol_mutation_is_refused_before_output(self):
        self.protocol=self.seed.base/'wrong-protocol';self.protocol.write_text('synthetic replacement protocol')
        with self.assertRaisesRegex(ValueError,'protocol differs'):self.generate()
        self.assertFalse(self.output.exists())

    def test_active_supervisor_is_refused_before_output(self):
        with (self.seed.root/'supervisor.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'supervisor is active'):self.generate()
        self.assertFalse(self.output.exists())

    def test_wrong_installed_executable_is_refused_before_output(self):
        self.seed.binary=Path('/usr/bin/false')
        with self.assertRaisesRegex(ValueError,'verifier version'):self.generate()
        self.assertFalse(self.output.exists())

    def test_output_is_new_and_outside_source_and_quality(self):
        for output in (self.seed.source/'inside',self.seed.quality/'inside'):
            self.output=output
            with self.assertRaisesRegex(ValueError,'outside'):self.generate()
        self.output=self.seed.base/'evaluation';self.generate()
        with self.assertRaisesRegex(ValueError,'new'):self.generate()
