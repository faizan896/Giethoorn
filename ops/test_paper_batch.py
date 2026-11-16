import copy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('paper_batch', PROJECT/'ops/paper_batch.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BatchTests(unittest.TestCase):
    """Orchestration fixtures are synthetic, separate from native model tests."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source'
        self.source.mkdir()
        (self.source/'index.jsonl').write_text('synthetic orchestration source\n')
        self.plan = json.loads((PROJECT/'fixtures/paper-ioc-scenario-v1.json').read_text())
        MODULE.write_json(self.root/'plan.json', self.plan)
        self.manifest = dict(batch_version=1, label='Synthetic batch fixture', baseline_profile='base',
            datasets=[dict(id='fixture', label='Synthetic recording', recording='source', scenario='plan.json',
                           origin='synthetic_fixture', feed='bbo')],
            profiles=[dict(id='base', label='Baseline', assumptions=self.plan['assumptions']),
                      dict(id='fee', label='Fee stress', assumptions=dict(self.plan['assumptions'], fee_rate='0.001'))],
            limits=dict(max_output_bytes=1024*MODULE.MIB, min_free_bytes=1024*MODULE.MIB,
                        native_timeout_seconds=30, suite_timeout_seconds=120))
        self.path = self.root/'manifest.json'
        self.plans = []

    def save(self):
        self.path.write_text(json.dumps(self.manifest))

    def snapshot(self, command, **kwargs):
        output = Path(command[command.index('--output-dir')+1])
        output.mkdir()
        (output/'source').mkdir()
        raw = (self.source/'index.jsonl').read_bytes()
        (output/'source/index.jsonl').write_bytes(raw)
        manifest = dict(manifest_version=1, origin='synthetic_fixture', recording_sha256='f'*64,
                        files=[dict(file='index.jsonl', bytes=len(raw), sha256=MODULE.digest(raw))])
        MODULE.write_json(output/'source-manifest.json', manifest)
        MODULE.write_json(output/'market-replay.json', dict(source=manifest,
            source_report=dict(complete=True, records=29, end_reason='fixture_end'), source_storage=dict(finalized=True)))
        self.assertGreater(kwargs['timeout'], 0)
        self.assertLessEqual(kwargs['timeout'], 30)
        return SimpleNamespace(returncode=0)

    def case(self, binary, recording, scenario, output, origin, feed, **kwargs):
        self.assertFalse(kwargs['render_view'])
        self.assertLessEqual(kwargs['timeout_secs'], 30)
        self.assertEqual(origin, 'synthetic_fixture')
        self.assertEqual(recording, self.root/'out/datasets/fixture/market/source')
        self.plans.append(json.loads(scenario.read_text()))
        output.mkdir()
        (output/'replay').mkdir()
        report = json.loads((PROJECT/'fixtures/paper-execution-v3.execution.json').read_text())
        report['scenario_sha256'] = MODULE.digest(scenario.read_bytes())
        report['paper']['config']['source']['recording_sha256'] = 'f'*64
        MODULE.write_json(output/'replay/execution-replay.json', report)
        MODULE.write_json(output/'cost-audit.json', dict(status='verified'))
        MODULE.write_json(output/'run.json', dict(recording_sha256='f'*64))
        for dest, fixture in [('paper-updates.jsonl','updates'), ('execution-trace.jsonl','trace')]:
            (output/'replay'/dest).write_bytes((PROJECT/f'fixtures/paper-execution-v3.{fixture}.jsonl').read_bytes())

    def run_batch(self, case=None, native=None):
        self.save()
        with patch.object(MODULE.subprocess, 'run', side_effect=native or self.snapshot), \
             patch.object(MODULE.EXECUTION, 'generate', side_effect=case or self.case):
            return MODULE.generate(Path('/usr/bin/true'), self.path, self.root/'out')

    def test_profiles_change_only_assumptions_and_cases_use_a_frozen_source(self):
        original = (self.source/'index.jsonl').read_bytes()
        path, report = self.run_batch()
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(report['counts'], dict(verified=2, failed=0, not_run=0))
        self.assertEqual(len(self.plans), 2)
        for plan in self.plans:
            self.assertEqual(MODULE.fixed_plan(plan), MODULE.fixed_plan(self.plan))
        self.assertNotEqual(self.plans[0]['assumptions'], self.plans[1]['assumptions'])
        self.assertEqual((self.source/'index.jsonl').read_bytes(), original)
        self.assertEqual(len({c['fixed_plan_sha256'] for c in report['cases']}), 1)
        self.assertEqual(report['cases'][0]['metrics']['coin'], 'BTC')
        self.assertEqual(report['cases'][0]['metrics']['quote_currency'], 'USDC')
        self.assertIn('"origin":"synthetic_fixture"', path.read_text())
        with self.assertRaises(FileExistsError):
            MODULE.generate(Path('/usr/bin/true'), self.path, self.root/'out')

    def test_failed_baseline_stays_visible_with_null_result_and_no_paired_delta(self):
        def fail_first(*args, **kwargs):
            if 'base' in str(args[3]):
                raise ValueError('synthetic deliberate failure')
            return self.case(*args, **kwargs)
        _, report = self.run_batch(case=fail_first)
        self.assertEqual(report['status'], 'completed_with_failures')
        self.assertEqual(report['cases'][0]['status'], 'failed')
        self.assertIsNone(report['cases'][0]['metrics'])
        self.assertEqual(report['cases'][1]['status'], 'verified')
        self.assertTrue(all(p['deltas'] is None for p in report['comparisons']))
        self.assertIn('deliberate failure', report['cases'][0]['reason'])

    def test_source_timeout_fails_all_its_cases_and_preserves_a_report(self):
        _, report = self.run_batch(native=lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired('fixture', 1)))
        self.assertEqual(report['counts']['failed'], 2)
        self.assertTrue(all(c['metrics'] is None for c in report['cases']))
        self.assertIn('TimeoutExpired', report['snapshots'][0]['reason'])
        self.assertTrue((self.root/'out/batch-report.json').exists())

    def test_budget_blocks_remaining_cases_instead_of_silently_dropping_them(self):
        with patch.object(MODULE, 'admission', side_effect=[None, None, 'Output budget exhausted.']):
            _, report = self.run_batch()
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['counts'], dict(verified=1, failed=0, not_run=1))
        self.assertIsNone(report['cases'][1]['metrics'])
        self.assertIsNone(report['comparisons'][1]['deltas'])

    def test_exact_decimal_deltas_and_changed_execution_paths(self):
        a=dict(net_pnl='-0.05513500125', fees='0.02511250125', spread_cost='0.05',
               slippage_cost='0.0050225', position_quantity='0', pending_order_ids=['late'], execution_path_sha256='a')
        b=dict(a, net_pnl='-0.0802475025', fees='0.0502250025', execution_path_sha256='b', position_quantity='0.1')
        cases=[dict(id='a', dataset_id='fixture', profile_id='base', status='verified', metrics=a),
               dict(id='b', dataset_id='fixture', profile_id='fee', status='verified', metrics=b)]
        pair=MODULE.comparisons(cases, 'base')[1]
        self.assertEqual(pair['deltas']['net_pnl'], '-0.02511250125')
        self.assertEqual(pair['deltas']['fees'], '0.02511250125')
        self.assertTrue(pair['execution_path_changed'])
        self.assertTrue(pair['ending_inventory_changed'])
        self.assertFalse(pair['pending_changed'])

    def test_missing_valuation_remains_null_in_paired_comparison(self):
        a=dict(net_pnl=None, fees='0', spread_cost='0', slippage_cost='0', position_quantity='0.1',
               pending_order_ids=[], execution_path_sha256='a')
        cases=[dict(id='a', dataset_id='fixture', profile_id='base', status='verified', metrics=a)]
        self.assertIsNone(MODULE.comparisons(cases, 'base')[0]['deltas']['net_pnl'])

    def test_strict_manifest_rejects_unknown_fields_boolean_time_and_ambiguous_ids(self):
        original=copy.deepcopy(self.manifest)
        for mutate in [lambda m:m.update(strategy=True),
                       lambda m:m['profiles'][0]['assumptions'].update(latency_ms=True),
                       lambda m:m['profiles'][0].update(id='../bad'),
                       lambda m:m['datasets'][0].update(id='a--b'),
                       lambda m:m.update(baseline_profile='missing'),
                       lambda m:m['profiles'][0]['assumptions'].update(top_size_fraction='0'),
                       lambda m:m['profiles'][0]['assumptions'].update(fee_rate='1e-3')]:
            self.manifest=copy.deepcopy(original);mutate(self.manifest);self.save()
            with self.assertRaises(ValueError):
                MODULE.generate(Path('/usr/bin/true'), self.path, self.root/'out')
            self.assertFalse((self.root/'out').exists())

    def test_duplicate_json_keys_and_source_output_overlap_are_rejected(self):
        self.save()
        self.path.write_text(self.path.read_text().replace('"batch_version": 1', '"batch_version":1,"batch_version":1'))
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            MODULE.load_manifest(self.path)
        self.save()
        with self.assertRaisesRegex(ValueError, 'outside every source'):
            MODULE.generate(Path('/usr/bin/true'), self.path, self.source/'out')

    def test_admission_enforces_time_space_and_output_reserves(self):
        root=self.root
        limits=self.manifest['limits']
        with patch.object(MODULE.time, 'monotonic', return_value=100):
            self.assertIn('time budget', MODULE.admission(root, limits, 99, 0))
            with patch.object(MODULE.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)):
                self.assertIn('Free-space', MODULE.admission(root, limits, 101, 0))
            with patch.object(MODULE, 'used_bytes', return_value=limits['max_output_bytes']):
                self.assertIn('Output budget', MODULE.admission(root, limits, 101, 1))

    def test_embedded_report_escapes_script_closing_text(self):
        self.manifest['label']='Synthetic </script><script>alert(1)</script>'
        path, _=self.run_batch()
        self.assertNotIn('</script><script>alert', path.read_text())
        self.assertIn('\\u003c/script\\u003e', path.read_text())


if __name__ == '__main__':
    unittest.main()
