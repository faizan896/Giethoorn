import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import study_local as MODULE
    from .test_study_core import fixture
except ImportError:
    import study_local as MODULE
    from test_study_core import fixture


class LocalStudyTests(unittest.TestCase):
    """Synthetic orchestration receipts, separate from native archive acceptance."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.source=self.base/'run/experiment';self.root=self.source/'supervision'
        self.root.mkdir(parents=True);(self.root/'supervisor.lock').write_bytes(b'')
        self.quality=self.base/'quality';self.quality.mkdir();(self.quality/'audit').mkdir()
        self.output=self.base/'study';self.binary=Path('/usr/bin/true')
        self.template=self.base/'template';self.template.write_text('__GIETHOORN_THEME__<script>const report=__QUALITY_BOOT__;</script>')
        self.theme=self.base/'theme';self.theme.write_text('/* synthetic theme */')
        rows=[]
        for n in range(1,7):
            child=self.root/f'run-{n:06d}';(child/'session').mkdir(parents=True)
            events=fixture()
            (child/'session/segment-00000001.jsonl').write_text(''.join(json.dumps(r)+'\n' for r,o in events))
            (child/'live-quotes.jsonl').write_text(''.join(json.dumps(o)+'\n' for r,o in events if o is not None))
            rows.append(dict(run=n,directory=f'run-{n:06d}',candidate=True,finalized=True,snapshots=6,
                previously_inspected=n==6,reason='candidate',measurements=dict(source_records=len(events),
                    usable_bbo_observations=6,cadence=dict(candidate_span_count=1,candidate_span_ns=1250000000))))
        inventory=MODULE.REVIEW.inventory(self.source)
        self.save('source-before.json',inventory);self.save('source-after.json',inventory)
        self.save('quality-policy.json',MODULE.QUALITY.POLICY)
        self.save('audit/audit.stdout.json',dict(synthetic_native_audit=True))
        (self.quality/'research-protocol.md').write_text('Synthetic fixed protocol')
        (self.quality/'fast-spans.jsonl').write_text('synthetic unit span artifact\n')
        digest=MODULE.REVIEW.digest
        self.manifest=dict(quality_manifest_version=1,admitted=True,origin='synthetic_fixture',
            source_inventory_sha256=digest(self.quality/'source-before.json'),
            audit_output_sha256=digest(self.quality/'audit/audit.stdout.json'),
            policy_sha256=digest(self.quality/'quality-policy.json'),fast_spans_sha256=digest(self.quality/'fast-spans.jsonl'),
            audit_binary_sha256=digest(self.binary),quality_helper_sha256=digest(Path(MODULE.QUALITY.__file__)),
            review_helper_sha256=digest(Path(MODULE.REVIEW.__file__)),
            assets=dict(protocol=digest(self.quality/'research-protocol.md'),template=digest(self.template),theme=digest(self.theme)),
            candidate_partitions=MODULE.QUALITY.partitions(rows),inspected_children=[6])
        self.report=dict(quality_report_version=1,status='completed',source_unchanged=True,origin='synthetic_fixture',
            manifest=self.manifest,policy=MODULE.QUALITY.POLICY,partitions=self.manifest['candidate_partitions'],
            totals=MODULE.QUALITY.summarize(rows),runs=rows,
            audit=dict(verified_24_hour_window=False,reported_supervisor_status='failed',audit=dict(coin='BTC',network='mainnet')))
        self.save('dataset-manifest.json',self.manifest);self.save('quality-report.json',self.report)

    def save(self,name,value):
        (self.quality/name).write_text(json.dumps(value)+'\n')

    def generate(self,partition='development',fresh=None):
        with patch.object(MODULE.QUALITY,'generate',return_value=fresh or copy.deepcopy(self.report)):
            return MODULE.generate(self.binary,self.source,self.quality,self.output,partition,'synthetic_fixture',
                                   self.template,self.template,self.theme)

    def test_only_requested_partition_is_analysed_and_holdouts_remain_unrun(self):
        with patch.object(MODULE,'analyze',wraps=MODULE.analyze) as analyze:
            report=self.generate()
        self.assertEqual([call.args[0] for call in analyze.call_args_list],[1,2,3])
        self.assertEqual(report['status'],'completed')
        self.assertEqual(report['metrics']['signals'],3)
        self.assertEqual(report['metrics']['labelled_signals'],3)
        self.assertEqual(report['metrics']['signal_hits'],3)
        self.assertTrue(report['source_unchanged'] and report['quality_unchanged'])
        self.assertEqual(report['partitions']['validation']['status'],'not_run')
        self.assertIsNone(report['partitions']['retrospective_test']['metrics'])
        self.assertTrue(all(row['metrics'] is None for row in report['rows'] if row['child']>=4))
        self.assertFalse(report['orders_enabled'] or report['profit_evaluated'] or report['full_window_verified'])

    def test_wrong_market_domain_is_refused_before_any_study_output(self):
        self.report['audit']['audit']['coin']='ETH';self.save('quality-report.json',self.report)
        with self.assertRaisesRegex(ValueError,'BTC mainnet'):self.generate()
        self.assertFalse(self.output.exists())

    def test_feature_and_sample_bytes_repeat_on_unchanged_frozen_input(self):
        self.generate();features=(self.output/'features.jsonl').read_bytes();samples=(self.output/'samples.jsonl').read_bytes()
        self.output=self.base/'repeat';self.generate()
        self.assertEqual(features,(self.output/'features.jsonl').read_bytes())
        self.assertEqual(samples,(self.output/'samples.jsonl').read_bytes())

    def test_explicit_validation_uses_its_frozen_members_only(self):
        with patch.object(MODULE,'analyze',wraps=MODULE.analyze) as analyze:report=self.generate('validation')
        self.assertEqual([call.args[0] for call in analyze.call_args_list],[4])
        self.assertEqual(report['partitions']['development']['status'],'not_run')
        self.assertIsNone(report['partitions']['retrospective_test']['metrics'])

    def test_modified_quality_artifact_or_missing_admission_refuses_before_output(self):
        (self.quality/'fast-spans.jsonl').write_text('synthetic alteration')
        with self.assertRaisesRegex(ValueError,'fingerprint'):self.generate()
        self.assertFalse(self.output.exists())
        (self.quality/'fast-spans.jsonl').write_text('synthetic unit span artifact\n')
        self.manifest['admitted']=False;self.report['manifest']=self.manifest
        self.save('dataset-manifest.json',self.manifest);self.save('quality-report.json',self.report)
        with self.assertRaisesRegex(ValueError,'admitted'):self.generate()

    def test_fresh_verification_cannot_move_the_frozen_partitions(self):
        fresh=copy.deepcopy(self.report);fresh['partitions']['development']=[2,3,4]
        report=self.generate(fresh=fresh)
        self.assertEqual(report['status'],'analysis_failed')
        self.assertIsNone(report['metrics'])
        self.assertFalse((self.output/'features.jsonl').exists())

    def test_native_refusal_yields_unavailable_results_not_zero_scores(self):
        fresh=copy.deepcopy(self.report);fresh['status']='audit_unverified'
        report=self.generate(fresh=fresh)
        self.assertEqual(report['status'],'analysis_failed')
        self.assertIsNone(report['metrics'])
        self.assertTrue(all(row['metrics'] is None for row in report['rows']))

    def test_source_or_quality_change_invalidates_earlier_results(self):
        original=MODULE.analyze
        def mutate(*args):
            stats=original(*args);(self.root/'changed.txt').write_text('synthetic concurrent change');return stats
        with patch.object(MODULE,'analyze',side_effect=mutate):report=self.generate()
        self.assertEqual(report['status'],'source_changed');self.assertIsNone(report['metrics'])
        self.assertTrue((self.output/'features.jsonl').exists())
        self.assertTrue(all(row['metrics'] is None for row in report['rows']))

    def test_invalid_partition_output_location_and_existing_output_are_refused(self):
        with self.assertRaisesRegex(ValueError,'partition'):self.generate('all')
        self.output=self.quality/'nested'
        with self.assertRaisesRegex(ValueError,'outside'):self.generate()
        self.output=self.base/'exists';self.output.mkdir();(self.output/'sentinel').write_text('unchanged')
        with self.assertRaises(FileExistsError):self.generate()
        self.assertEqual((self.output/'sentinel').read_text(),'unchanged')


if __name__=='__main__':unittest.main()
