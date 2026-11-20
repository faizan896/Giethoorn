import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from . import expiry_local as RUN, test_cost_local as SETUP
except ImportError:
    import expiry_local as RUN
    import test_cost_local as SETUP


class ExpiryAdmissionTests(unittest.TestCase):
    """Synthetic admission/orchestration; native saved-case checks are separate."""
    def setUp(self):
        self.fixture = SETUP.CostAdmissionTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.generate()
        self.source = self.fixture.output
        self.output = self.fixture.base/'expiry'
        self.template = self.fixture.base/'expiry-template'
        self.template.write_text('__GIETHOORN_THEME__<script type="application/json">__QUALITY_BOOT__</script>')

    def fake_market(self,*args):
        args[2].mkdir()
        return dict(synthetic_native_market=True)

    def fake_case(self,*args):
        args[4].mkdir()
        value = dict(status='verified',orders=[dict(order_id='entry',classification='request_rejected')],reason=None)
        RUN.REVIEW.save(args[4]/'synthetic-only.json',value)
        return value

    def generate(self,market=None,case=None):
        with patch.object(RUN,'fresh_market',side_effect=market or self.fake_market), \
             patch.object(RUN,'case_review',side_effect=case or self.fake_case):
            return RUN.generate(self.fixture.setup.binary,self.source,self.output,self.fixture.setup.template,
                self.fixture.cost_template,self.template,self.fixture.setup.theme)

    def test_preserved_bundle_reuses_one_source_audit_per_child_and_keeps_all_cases(self):
        calls=[]
        def market(*args):
            calls.append(args[3]);return self.fake_market(*args)
        report=self.generate(market=market)
        self.assertEqual(calls,[1,2,3])
        self.assertEqual(report['status'],'completed')
        self.assertEqual(report['totals']['verified'],18)
        self.assertEqual(report['totals']['orders'],18)
        self.assertTrue(report['input_unchanged'] and report['code_unchanged'])
        self.assertFalse(report['orders_generated'] or report['profit_reestimated'] or report['full_window_verified'])

    def test_changed_bundle_member_is_refused_before_any_output(self):
        (self.source/'cost-policy.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'bundle member changed'):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_unexpected_file_or_symlink_cannot_be_silently_ignored(self):
        (self.source/'unexpected.txt').write_text('unexpected')
        with self.assertRaisesRegex(ValueError,'unexpected'):
            self.generate()
        (self.source/'unexpected.txt').unlink()
        (self.source/'unsafe').symlink_to(self.fixture.setup.binary)
        with self.assertRaisesRegex(ValueError,'symlink'):
            self.generate()

    def test_wrong_bundle_fingerprint_is_refused(self):
        path=self.source/'cost-report.json'
        value=json.loads(path.read_text());value['provenance']['bundle_inventory_sha256']='0'*64
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'bundle fingerprint'):
            self.generate()

    def test_changed_cost_scope_or_version_cannot_be_admitted(self):
        path=self.source/'cost-report.json'
        original=json.loads(path.read_text())
        for key,value in [('cost_report_version',2),('source_unchanged',False),('live_orders_enabled',True)]:
            modified=copy.deepcopy(original);modified[key]=value;path.write_text(json.dumps(modified))
            with self.assertRaises(ValueError):self.generate()
        self.assertFalse(self.output.exists())

    def test_native_source_failure_is_unavailable_for_every_profile_without_retrying(self):
        calls=[]
        def fail(*args):
            calls.append(args[3]);raise ValueError('synthetic source validation failed')
        report=self.generate(market=fail)
        self.assertEqual(calls,[1,2,3])
        self.assertEqual(report['totals']['unavailable'],18)
        self.assertEqual(report['totals']['verified'],0)
        self.assertEqual(report['status'],'incomplete')
        self.assertTrue(all(not c['orders'] for c in report['cases']))

    def test_case_failure_is_retained_and_other_cases_continue(self):
        def fail(*args):
            if args[2]['id']=='run-000001--baseline':raise ValueError('synthetic ledger mismatch')
            return self.fake_case(*args)
        report=self.generate(case=fail)
        self.assertEqual(report['totals']['unavailable'],1)
        self.assertEqual(report['totals']['verified'],17)
        self.assertEqual(report['status'],'incomplete')

    def test_source_mutation_invalidates_previously_completed_rows(self):
        def change(*args):
            result=self.fake_case(*args)
            (self.source/'changed.txt').write_text('synthetic mutation')
            return result
        report=self.generate(case=change)
        self.assertEqual(report['status'],'source_changed')
        self.assertFalse(report['input_unchanged'])
        self.assertEqual(report['totals']['verified'],0)
        self.assertTrue(all(not c['orders'] for c in report['cases']))

    def test_asset_mutation_invalidates_rows_without_changing_original_cost_results(self):
        def change(*args):
            result=self.fake_case(*args);self.template.write_text('changed asset');return result
        report=self.generate(case=change)
        self.assertFalse(report['code_unchanged'])
        self.assertTrue(report['input_unchanged'])
        self.assertEqual(report['status'],'source_changed')

    def test_budget_refusal_stays_not_run_with_no_order_diagnosis(self):
        original=RUN.admit;calls=[]
        def admit(*args):
            calls.append(1)
            if len(calls)>1:raise ValueError('synthetic budget exhausted')
            return original(*args)
        with patch.object(RUN,'admit',side_effect=admit):report=self.generate()
        self.assertEqual(report['totals']['not_run'],18)
        self.assertEqual(report['totals']['orders'],0)

    def test_output_cannot_be_inside_original_bundle_or_overwrite_a_previous_review(self):
        self.output=self.source/'bad'
        with self.assertRaisesRegex(ValueError,'outside original'):
            self.generate()
        self.output=self.fixture.base/'expiry'
        self.generate()
        with self.assertRaises(FileExistsError):self.generate()

    def test_json_duplicate_keys_and_nonfinite_numbers_are_refused(self):
        for raw in ('{"x":1,"x":2}','{"x":NaN}'):
            with self.assertRaises(ValueError):RUN.parse(raw)

    def test_time_display_is_exact_and_never_uses_float_precision(self):
        self.assertEqual(RUN.milliseconds('143830603'),'143.830603')
        self.assertEqual(RUN.milliseconds('-1'),'-0.000001')
        self.assertEqual(RUN.milliseconds(str(2**63+123)),'9223372036854.775931')
        self.assertIsNone(RUN.milliseconds(None))
