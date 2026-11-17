import copy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import quality_local as MODULE
except ImportError:
    import quality_local as MODULE

MS = 1_000_000


class QualityTests(unittest.TestCase):
    """Explicit synthetic traces/receipts; native archives are checked separately."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.experiment = self.base/'run/experiment'
        self.root = self.experiment/'supervision'
        self.child = self.root/'run-000001'
        (self.child/'session').mkdir(parents=True)
        (self.root/'supervisor.lock').write_bytes(b'')
        self.output = self.base/'output'
        self.assets = {}
        for name, value in [('template', '__GIETHOORN_THEME__<script>const boot=__QUALITY_BOOT__;</script>'),
                            ('theme', '/* synthetic theme */'), ('protocol', 'Synthetic research protocol')]:
            self.assets[name] = self.base/name
            self.assets[name].write_text(value)
        self.trace()

    def trace(self, times=(100, 350, 600, 850, 1100, 1350, 1600), end=2000, mutations=None):
        self.records = [dict(schema_version=2, sequence=i+1, monotonic_ns=t*MS,
                             local_time_ns=1_700_000_000_000_000_000+t*MS, connection_id=1,
                             event=dict(type='feed_timer')) for i, t in enumerate((0, *times, end))]
        if mutations:
            mutations(self.records)
        self.observations = []
        for record in self.records[1:]:
            footer = record is self.records[-1]
            self.observations.append(dict(normalization_version=2, kind='freshness' if footer else 'bbo',
                **{key: record[key] for key in ('sequence', 'monotonic_ns', 'local_time_ns', 'connection_id')},
                quote=None if footer else dict(mid='100', exchange_time_ms=record['monotonic_ns']//MS),
                feeds=dict(bbo=dict(status='disconnected' if footer else 'fresh', acknowledged=not footer,
                                    stale_after_ms=500, age_ns=None if footer else 0), depth=None)))
        self.inspection = dict(status='completed', session=dict(records=len(self.records), end_reason='duration_elapsed',
                               feeds=dict(normalization_version=2, bbo={}, depth=None)),
                               recorded_duration_ns=end*MS, connection_errors=0, successful_connections=1,
                               feeds=dict(bbo=dict(snapshots=len(times))))
        self.persist()

    def persist(self):
        (self.child/'session/segment-00000001.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.records))
        (self.child/'live-quotes.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.observations))
        (self.child/'inspection.json').write_text(json.dumps(self.inspection))
        self.summary = dict(runs=[dict(run=1, elapsed_ns=2100*MS)])
        (self.root/'summary.json').write_text(json.dumps(self.summary))
        self.native = dict(runs=[dict(run=1, directory='run-000001', finalized=True,
                          snapshots=self.inspection['feeds']['bbo']['snapshots'], recording_bytes=999, comparison='exact')])

    def measure(self):
        stream = io.BytesIO()
        result = MODULE.measure(self.child/'session', self.child/'live-quotes.jsonl', self.inspection,
                                1, MODULE.SpanWriter(stream))
        return result, [json.loads(row) for row in stream.getvalue().splitlines()]

    def mock_audit(self, binary, experiment, output):
        output.mkdir()
        (output/'audit.stdout.json').write_text(json.dumps(self.native))
        return dict(integrity='verified', audit_diagnostic=None, source_unchanged=True,
                    audit_binary_sha256=MODULE.REVIEW.digest(binary.resolve()), verified_24_hour_window=False)

    def generate(self, native=None):
        with patch.object(MODULE.REVIEW, 'review', side_effect=native or self.mock_audit):
            return MODULE.generate(Path('/usr/bin/true'), self.experiment, self.output, 'synthetic_fixture',
                                   self.assets['template'], self.assets['theme'], self.assets['protocol'], (1,))

    def test_exact_gap_boundary_keeps_one_span_without_extending_its_tail(self):
        result, spans = self.measure()
        self.assertEqual(result['usable_bbo_observations'], 7)
        self.assertEqual(result['cadence']['candidate_span_count'], 1)
        self.assertEqual(result['cadence']['candidate_span_ns'], 1500*MS)
        self.assertEqual(spans[0]['start_ns'], 100*MS)
        self.assertEqual(spans[0]['end_ns'], 1600*MS)
        self.assertEqual(result['feed_state_duration_ns']['bbo']['fresh'], 1900*MS)

    def test_a_gap_one_nanosecond_beyond_threshold_breaks_the_span(self):
        self.records[4]['monotonic_ns'] += 1
        self.observations[3]['monotonic_ns'] += 1
        self.persist()
        result, spans = self.measure()
        self.assertEqual(result['cadence']['candidate_span_count'], 0)
        self.assertEqual(len(spans), 2)

    def test_missing_timer_transition_cannot_extend_freshness_past_deadline(self):
        self.trace(times=(100, 1000), end=1100)
        result, _ = self.measure()
        states = result['feed_state_duration_ns']['bbo']
        self.assertEqual(states['fresh'], 600*MS)
        self.assertEqual(states['unobserved_deadline'], 400*MS)
        self.assertEqual(sum(states.values()), 1100*MS)

    def test_depth_updates_do_not_refresh_bbo_or_supply_bbo_spans(self):
        self.trace(times=(100, 800), end=1000)
        self.inspection['session']['feeds']['depth'] = {}
        self.inspection['feeds']['bbo']['snapshots'] = 1
        self.inspection['feeds']['depth'] = dict(snapshots=1)
        for row in self.observations:
            row['feeds']['depth'] = copy.deepcopy(row['feeds']['bbo'])
        self.observations[1]['kind'] = 'depth'
        self.observations[1]['feeds']['bbo'].update(status='stale', age_ns=700*MS)
        self.persist()
        result, spans = self.measure()
        states = result['feed_state_duration_ns']['bbo']
        self.assertEqual(states['fresh'], 500*MS)
        self.assertEqual(states['stale'], 200*MS)
        self.assertEqual(result['usable_bbo_observations'], 1)
        self.assertEqual(spans, [])

    def test_connection_changes_and_repeated_exchange_times_break_chains(self):
        self.records[4]['connection_id'] = 2
        for row in self.records[5:]:row['connection_id'] = 2
        for record, row in zip(self.records[1:], self.observations):row['connection_id'] = record['connection_id']
        self.persist()
        result, _ = self.measure()
        self.assertEqual(result['cadence']['candidate_span_count'], 0)
        self.trace()
        self.observations[3]['quote']['exchange_time_ms'] = self.observations[2]['quote']['exchange_time_ms']
        self.persist()
        result, _ = self.measure()
        self.assertEqual(result['equal_exchange_time_bbo_observations'], 1)
        self.assertEqual(result['cadence']['candidate_span_count'], 0)

    def test_wall_clock_jump_does_not_create_a_false_continuous_span(self):
        def jump(records):
            for row in records[4:]:row['local_time_ns'] += 2_000*MS
        self.trace(mutations=jump)
        result, _ = self.measure()
        self.assertEqual(result['wall_clock_discontinuities'], 1)
        self.assertEqual(result['max_wall_minus_monotonic_step_ns'], 2000*MS)
        self.assertEqual(result['cadence']['candidate_span_count'], 0)

    def test_native_count_and_original_reference_mismatches_are_refused(self):
        self.inspection['feeds']['bbo']['snapshots'] += 1
        with self.assertRaisesRegex(ValueError, 'accounting'):self.measure()
        self.trace()
        self.observations[0]['local_time_ns'] += 1
        self.persist()
        with self.assertRaisesRegex(ValueError, 'no longer matches'):self.measure()

    def test_complete_quality_report_binds_source_protocol_and_exposure(self):
        before = MODULE.REVIEW.inventory(self.experiment)
        result = self.generate()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['totals']['candidate_recordings'], 1)
        self.assertTrue(result['source_unchanged'])
        self.assertTrue(result['runs'][0]['previously_inspected'])
        self.assertFalse(result['strategy_evaluated'])
        self.assertEqual(result['partitions']['status'], 'insufficient_children')
        self.assertFalse(result['manifest']['admitted'])
        self.assertEqual(result['manifest']['assets']['protocol'], hashlib.sha256(self.assets['protocol'].read_bytes()).hexdigest())
        self.assertEqual(before, MODULE.REVIEW.inventory(self.experiment))
        self.assertTrue((self.output/'quality.html').exists())

    def test_admission_keeps_whole_children_separate_and_freezes_chronological_partitions(self):
        for n in range(2,7):
            shutil.copytree(self.child,self.root/f'run-{n:06d}')
        self.native['runs']=[dict(self.native['runs'][0],run=n,directory=f'run-{n:06d}') for n in (6,2,5,1,4,3)]
        self.summary['runs']=[dict(run=n,elapsed_ns=2100*MS) for n in range(1,7)]
        (self.root/'summary.json').write_text(json.dumps(self.summary))
        result=self.generate()
        self.assertTrue(result['manifest']['admitted'])
        self.assertEqual(result['partitions']['development'],[1,2,3])
        self.assertEqual(result['partitions']['validation'],[4])
        self.assertEqual(result['partitions']['retrospective_test'],[5,6])
        spans=[json.loads(line) for line in (self.output/'fast-spans.jsonl').read_text().splitlines()]
        self.assertEqual([span['child'] for span in spans],[1,2,3,4,5,6])
        self.assertTrue(all(span['duration_ns']==1500*MS for span in spans))

    def test_recovered_prefix_is_retained_in_inventory_without_research_admission(self):
        self.native['runs'][0].update(finalized=False, comparison='live_prefix')
        result = self.generate()
        self.assertEqual(result['totals']['recovered_prefixes'], 1)
        self.assertEqual(result['totals']['retained_snapshots'], 7)
        self.assertIsNone(result['runs'][0]['measurements'])
        self.assertFalse(result['manifest']['admitted'])

    def test_refused_native_audit_never_invents_zero_quality_metrics(self):
        def refuse(*args):
            audit=self.mock_audit(*args);audit.update(integrity='unverified',audit_diagnostic='synthetic checksum failure');return audit
        result = self.generate(refuse)
        self.assertEqual(result['status'], 'audit_unverified')
        self.assertIsNone(result['totals'])
        self.assertEqual(result['runs'], [])
        self.assertFalse(result['manifest']['admitted'])
        self.assertIn('checksum failure', (self.output/'quality.html').read_text())

    def test_analysis_failure_or_changed_source_removes_candidate_results(self):
        self.inspection['session']['records'] += 1
        self.persist()
        result = self.generate()
        self.assertEqual(result['status'], 'analysis_failed')
        self.assertIsNone(result['totals'])
        self.output = self.base/'other-output'
        self.trace()
        original = MODULE.measure
        def mutate(*args):
            result = original(*args)
            (self.root/'summary.json').write_text('{"changed":"synthetic mutation"}')
            return result
        with patch.object(MODULE,'measure',side_effect=mutate):result=self.generate()
        self.assertEqual(result['status'], 'source_changed')
        self.assertIsNone(result['totals'])
        self.assertEqual(result['runs'], [])

    def test_active_writer_and_existing_output_are_refused(self):
        with (self.root/'supervisor.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'active'):self.generate()
        self.assertFalse(self.output.exists())
        self.output.mkdir();(self.output/'sentinel').write_text('unchanged')
        with self.assertRaises(FileExistsError):self.generate()
        self.assertEqual((self.output/'sentinel').read_text(),'unchanged')

    def test_partitions_stay_chronological_with_no_small_sample_admission(self):
        rows=[dict(run=n,candidate=n!=2) for n in (7,1,2,6,3,4)]
        result=MODULE.partitions(rows)
        self.assertEqual(result['development'],[1,3,4])
        self.assertEqual(result['validation'],[6])
        self.assertEqual(result['retrospective_test'],[7])
        self.assertIsNone(MODULE.partitions(rows[:2])['retrospective_test'])

    def test_render_escapes_source_text_and_requires_both_template_slots(self):
        report=dict(label='</script><script>globalThis.unsafe=true</script>')
        html=MODULE.render(report,self.assets['template'].read_text(),'/* synthetic */')
        self.assertNotIn('</script><script>',html)
        self.assertIn('\\u003c',html)
        with self.assertRaisesRegex(ValueError,'template'):MODULE.render(report,'missing slots','')


if __name__ == '__main__':
    unittest.main()
