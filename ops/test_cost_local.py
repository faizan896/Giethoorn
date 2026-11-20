import copy
import fcntl
import json
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from . import cost_local as RUN
    from . import test_study_local as SETUP
    from .test_study_core import fixture
except ImportError:
    import cost_local as RUN
    import test_study_local as SETUP
    from test_study_core import fixture


class CostAdmissionTests(unittest.TestCase):
    """Synthetic orchestration only; actual native acceptance is separate."""
    def setUp(self):
        self.setup = SETUP.LocalStudyTests('runTest')
        self.setup.setUp()
        self.addCleanup(self.setup.doCleanups)
        self.base = self.setup.base
        self.output = self.base/'cost'
        self.cost_template = self.base/'cost-template'
        self.cost_template.write_text('__GIETHOORN_THEME__<script type="application/json">__QUALITY_BOOT__</script>')

    def selected_feature(self, child, directory):
        analyzer = RUN.CORE.SIGNAL.Analyzer(child)
        for record, observation in fixture(times=(0, 5000, 5100, 6000)):
            for kind, value in analyzer.step(record, observation):
                if kind == 'feature' and value['monotonic_ns'] >= 5_000_000_000:
                    return value

    def fake_case(self, binary, source, value, profile, directory, expected, deadline):
        directory.mkdir()
        RUN.REVIEW.save(directory/'synthetic-only.json', dict(origin='synthetic_fixture'))
        return dict(status='verified', metrics=dict(outcome='no_entry_fill', entry_quantity='0',
            close_requested_quantity=None, closed_case_net_pnl=None, execution_path_sha256='synthetic-path'),
            prefix_verified=True, policy_sha256=expected['policy_sha256'])

    def generate(self, fresh=None, callback=None, feature_callback=None):
        with patch.object(RUN.QUALITY, 'generate', return_value=fresh or copy.deepcopy(self.setup.report)), \
             patch.object(RUN, 'feature', side_effect=feature_callback or self.selected_feature), \
             patch.object(RUN, 'run_case', side_effect=callback or self.fake_case):
            return RUN.generate(self.setup.binary, self.setup.source, self.setup.quality, self.output, 'synthetic_fixture',
                                self.setup.template, self.cost_template, self.setup.theme)

    def test_only_earliest_development_children_are_selected_without_replacement(self):
        calls = []
        def run(*args):
            calls.append((args[2]['child'], args[3]['id']))
            return self.fake_case(*args)
        report = self.generate(callback=run)
        self.assertEqual(report['selected_children'], [1,2,3])
        self.assertEqual(len(calls), 18)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['totals']['no_entry_fill'], 18)
        self.assertTrue(all(row['status'] == 'not_run' for row in report['rows'] if row['child'] >= 4))
        self.assertTrue(report['source_unchanged'] and report['quality_unchanged'] and report['code_unchanged'])
        self.assertFalse(report['portfolio_profit_evaluated'] or report['live_orders_enabled'] or report['full_window_verified'])
        self.assertTrue(all(row['closed_case_net_pnl_delta'] is None for row in report['comparisons']))

    def test_missing_signal_is_explicit_for_every_profile_and_not_replaced(self):
        report = self.generate(feature_callback=lambda child, directory: None)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['totals']['no_signal'], 18)
        self.assertTrue(all(row['metrics'] is None for row in report['cases']))

    def test_native_case_failure_is_retained_and_other_cases_still_run(self):
        def fail(*args):
            if args[2]['child'] == 1 and args[3]['id'] == 'baseline':
                raise ValueError('synthetic native refusal')
            return self.fake_case(*args)
        report = self.generate(callback=fail)
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['totals']['failed'], 1)
        self.assertEqual(report['totals']['verified'], 17)
        self.assertIsNone(report['cases'][0]['metrics'])
        self.assertTrue(all(pair['closed_case_net_pnl_delta'] is None for pair in report['comparisons']))

    def test_source_change_invalidates_previously_completed_case_metrics(self):
        def mutate(*args):
            result = self.fake_case(*args)
            (self.setup.root/'unexpected.txt').write_text('synthetic concurrent change')
            return result
        report = self.generate(callback=mutate)
        self.assertEqual(report['status'], 'source_changed')
        self.assertEqual(report['totals']['verified'], 0)
        self.assertTrue(all(row['metrics'] is None for row in report['cases']))

    def test_quality_change_invalidates_completed_results(self):
        def mutate(*args):
            result = self.fake_case(*args)
            (self.setup.quality/'research-protocol.md').write_text('changed')
            return result
        report = self.generate(callback=mutate)
        self.assertEqual(report['status'], 'source_changed')
        self.assertFalse(report['quality_unchanged'])
        self.assertTrue(all(row['metrics'] is None for row in report['cases']))

    def test_deadline_before_cases_keeps_results_not_run_not_zero(self):
        original = RUN.admit
        def admit(root, deadline, allowance):
            if allowance == RUN.LIMITS['case_allowance_bytes']:
                raise ValueError('suite time budget exhausted')
            return original(root, deadline, allowance)
        with patch.object(RUN, 'admit', side_effect=admit):
            report = self.generate()
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['totals']['not_run'], 18)
        self.assertTrue(all(row['metrics'] is None for row in report['cases']))

    def test_fresh_native_audit_failure_never_admits_cases(self):
        fresh = copy.deepcopy(self.setup.report)
        fresh['status'] = 'audit_unverified'
        report = self.generate(fresh=fresh)
        self.assertEqual(report['totals']['not_run'], 18)
        self.assertEqual(report['totals']['verified'], 0)
        self.assertEqual(report['status'], 'incomplete')

    def test_fresh_membership_changes_are_rejected(self):
        fresh = copy.deepcopy(self.setup.report)
        fresh['partitions']['development'] = [2,3]
        report = self.generate(fresh=fresh)
        self.assertEqual(report['totals']['verified'], 0)
        self.assertIn('membership', report['error'])

    def test_changed_binary_or_source_is_refused_before_output(self):
        (self.setup.root/'new.txt').write_text('synthetic change')
        with self.assertRaisesRegex(ValueError, 'source differs'):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_active_supervisor_is_refused_before_output(self):
        with (self.setup.root/'supervisor.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'supervisor is active'):
                self.generate()
        self.assertFalse(self.output.exists())

    def test_output_cannot_overwrite_frozen_inputs(self):
        self.output = self.setup.quality/'bad-output'
        with self.assertRaisesRegex(ValueError, 'outside original evidence'):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_comparison_cannot_call_open_mark_to_market_a_closed_return(self):
        cases = [dict(child=1,profile='baseline',status='verified',metrics=dict(entry_quantity='0.001',
            close_requested_quantity='0.001', outcome='closed', execution_path_sha256='a', closed_case_net_pnl='-0.02')),
            dict(child=1,profile='delay-stress',status='verified',metrics=dict(entry_quantity='0.0005',
            close_requested_quantity='0.0005', outcome='unresolved', execution_path_sha256='b', closed_case_net_pnl=None))]
        comparison = RUN.comparisons(cases)[1]
        self.assertTrue(comparison['entry_quantity_changed'] and comparison['outcome_changed'])
        self.assertIsNone(comparison['closed_case_net_pnl_delta'])

    def test_portable_report_escapes_hostile_text_and_preserves_raw_large_integers(self):
        report = self.generate()
        report['error'] = '</script><script>window.pwned=true</script>'
        report['large'] = 9007199254740993
        html = RUN.QUALITY.render(report, (Path(__file__).resolve().parent.parent/'web/cost.html').read_text(), '')
        self.assertNotIn('</script><script>window.pwned', html)
        self.assertIn('9007199254740993', html)
        self.assertNotIn('__QUALITY_BOOT__', html)
