import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import cadence_local as RUN,test_expiry_local as SETUP,test_cadence_core as CORE_FIXTURE,test_paper_execution as RAW_FIXTURE
except ImportError:
    import cadence_local as RUN
    import test_expiry_local as SETUP
    import test_cadence_core as CORE_FIXTURE
    import test_paper_execution as RAW_FIXTURE


class CadenceAdmissionTests(unittest.TestCase):
    """Synthetic producer/admission tests; native acceptance is separate."""
    def setUp(self):
        self.seed=SETUP.ExpiryAdmissionTests('runTest');self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        self.seed.generate()
        self.source=self.seed.output
        self.output=self.seed.fixture.base/'cadence'
        self.template=self.seed.fixture.base/'cadence-template'
        self.template.write_text('__GIETHOORN_THEME__<script type="application/json">__QUALITY_BOOT__</script>')

    def groups(self,*args):
        return [dict(child=n,children=[n],recording_sha256=f'{n:064x}',status='not_run',metrics=None,
                     request_neighborhoods=[],reason='Not admitted.',_market={},_base='synthetic') for n in (1,2,3)]

    def fresh(self,*args):
        args[3].mkdir()
        return CORE_FIXTURE.synthetic([dict(connection=1,ns=0,kind='opened'),dict(connection=1,ns=10_000_000),dict(connection=1,ns=500_000_000)])

    def generate(self,groups=None,fresh=None):
        fixture=self.seed.fixture
        with patch.object(RUN,'source_groups',side_effect=groups or self.groups), \
             patch.object(RUN,'fresh_source',side_effect=fresh or self.fresh), \
             patch.object(RUN,'neighborhoods',return_value=[]):
            return RUN.generate(fixture.setup.binary,self.source,self.output,fixture.setup.template,
                fixture.cost_template,self.seed.template,self.template,fixture.setup.theme)

    def test_three_sources_are_counted_once_instead_of_eighteen_profile_copies(self):
        calls=[]
        def fresh(*args):calls.append(args[2]['child']);return self.fresh(*args)
        report=self.generate(fresh=fresh)
        self.assertEqual(calls,[1,2,3])
        self.assertEqual(report['totals']['bbo_messages'],6)
        self.assertEqual(report['totals']['verified'],3)
        self.assertEqual(report['status'],'completed')
        self.assertTrue(report['input_unchanged'] and report['code_unchanged'])
        self.assertFalse(report['profit_evaluated'] or report['orders_generated'] or report['measured_order_latency'] or report['fill_probability_estimated'])

    def test_alias_children_share_one_measurement_without_multiplying_messages(self):
        def groups(*args):
            row=self.groups()[0];row['children']=[1,2,3];return [row]
        report=self.generate(groups=groups)
        self.assertEqual(report['totals']['verified'],1)
        self.assertEqual(report['totals']['duplicate_child_copies'],2)
        self.assertEqual(report['totals']['bbo_messages'],2)

    def test_changed_producer_artifact_is_refused_before_output(self):
        (self.source/'input-cost-policy.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'artifact changed'):self.generate()
        self.assertFalse(self.output.exists())

    def test_unexpected_file_or_symlink_cannot_be_ignored(self):
        (self.source/'extra').write_text('unexpected')
        with self.assertRaisesRegex(ValueError,'unexpected'):self.generate()
        (self.source/'extra').unlink();(self.source/'link').symlink_to(self.seed.fixture.setup.binary)
        with self.assertRaisesRegex(ValueError,'symlink'):self.generate()

    def test_unsupported_or_unpreserved_producer_version_is_refused(self):
        path=self.source/'expiry-report.json';original=json.loads(path.read_text())
        for key,value in [('expiry_report_version',2),('expiry_report_version',True),('input_unchanged',False),('orders_generated',True)]:
            body=copy.deepcopy(original);body[key]=value;path.write_text(json.dumps(body))
            with self.assertRaises(ValueError):self.generate()
        self.assertFalse(self.output.exists())

    def test_original_producer_assets_must_match_exactly(self):
        self.seed.template.write_text('changed original template')
        with self.assertRaisesRegex(ValueError,'producer/assets'):self.generate()

    def test_source_change_during_measurement_invalidates_every_completed_group(self):
        def change(*args):
            result=self.fresh(*args);(self.source/'changed').write_text('synthetic mutation');return result
        report=self.generate(fresh=change)
        self.assertEqual(report['status'],'source_changed')
        self.assertEqual(report['totals']['verified'],0)
        self.assertTrue(all(g['metrics'] is None for g in report['recordings']))

    def test_new_asset_change_invalidates_measurements_without_changing_input(self):
        def change(*args):
            result=self.fresh(*args);self.template.write_text('changed new template');return result
        report=self.generate(fresh=change)
        self.assertTrue(report['input_unchanged']);self.assertFalse(report['code_unchanged'])
        self.assertEqual(report['status'],'source_changed')

    def test_native_source_failure_retains_unavailable_group_and_continues(self):
        def fail(*args):
            if args[2]['child']==2:raise ValueError('synthetic native source mismatch')
            return self.fresh(*args)
        report=self.generate(fresh=fail)
        self.assertEqual(report['totals']['verified'],2)
        self.assertEqual(report['totals']['unavailable'],1)
        self.assertEqual(report['status'],'incomplete')

    def test_budget_refusal_is_not_run_with_unavailable_metrics(self):
        with patch.object(RUN,'admit',side_effect=ValueError('synthetic budget exhausted')):
            report=self.generate()
        self.assertEqual(report['totals']['not_run'],3)
        self.assertEqual(report['totals']['bbo_messages'],0)
        self.assertTrue(all(g['metrics'] is None for g in report['recordings']))

    def test_interval_export_budget_failure_never_publishes_partial_statistics(self):
        with patch.dict(RUN.LIMITS,interval_file_bytes=1):report=self.generate()
        self.assertEqual(report['totals']['verified'],0)
        self.assertEqual(report['totals']['unavailable'],3)

    def test_output_cannot_overwrite_input_or_a_previous_measurement(self):
        self.output=self.source/'bad'
        with self.assertRaisesRegex(ValueError,'outside'):self.generate()
        self.output=self.seed.fixture.base/'cadence'
        self.generate()
        with self.assertRaises(FileExistsError):self.generate()


class CadenceIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        raw=RAW_FIXTURE.ExecutionLabTests('runTest').prepare(self.root)
        self.input=self.root/'input';self.input.mkdir()
        fixture=json.loads((RAW_FIXTURE.PROJECT/'fixtures/paper-execution-v3.execution.json').read_text())['market']
        for child in (1,2):
            folder=self.input/f'markets/run-{child:06d}/market';folder.mkdir(parents=True)
            shutil.copytree(raw,folder/'source')
            (folder/'market-replay.json').write_text(json.dumps(fixture))
        digest=fixture['source']['recording_sha256']
        rows=[dict(child=n,status='verified',recording_sha256=digest) for n in (1,2)]
        self.report=dict(selected_children=[1,2],origin='synthetic_fixture',cases=rows)
        self.cost=dict(cases=copy.deepcopy(rows))

    def groups(self):return RUN.source_groups(self.input,self.report,self.cost,RUN.EXPLAIN.inventory(self.input))

    def test_identical_source_bytes_are_deduplicated_by_native_recording_identity(self):
        groups=self.groups()
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['children'],[1,2])

    def test_different_case_identity_cannot_hide_behind_same_source_copy(self):
        self.cost['cases'][1]['recording_sha256']='0'*64
        groups=self.groups()
        self.assertEqual(len(groups),2)
        self.assertEqual(groups[1]['status'],'unavailable')

    def test_corrupt_raw_copy_is_refused_without_replacing_selected_child(self):
        path=self.input/'markets/run-000002/market/source/segment-00000001.jsonl'
        path.write_bytes(path.read_bytes()+b'{}\n')
        groups=self.groups()
        self.assertEqual(groups[0]['children'],[1])
        self.assertEqual(groups[1]['status'],'unavailable')
        self.assertEqual(groups[1]['child'],2)

    def test_missing_source_export_remains_unavailable(self):
        (self.input/'markets/run-000002/market/market-replay.json').unlink()
        groups=self.groups()
        self.assertEqual(groups[1]['status'],'unavailable')
