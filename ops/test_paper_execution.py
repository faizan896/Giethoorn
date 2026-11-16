import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('paper_execution', PROJECT/'ops/paper_execution.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExecutionLabTests(unittest.TestCase):
    def prepare(self, root):
        source = root/'source'
        source.mkdir()
        raw = (PROJECT/'fixtures/hyperliquid-combined-v2.jsonl').read_bytes()
        (source/'segment-00000001.jsonl').write_bytes(raw)
        entries = [dict(kind='header', container_version=1, event_schema_version=2, max_segment_bytes=1048576, max_session_bytes=2097152),
                   dict(kind='segment', number=1, file='segment-00000001.jsonl', bytes=len(raw), first_sequence=1, last_sequence=29, sha256=hashlib.sha256(raw).hexdigest()),
                   dict(kind='end', segments=1, records=29, data_bytes=len(raw))]
        (source/'index.jsonl').write_text(''.join(json.dumps(e, sort_keys=True, separators=(',', ':'))+'\n' for e in entries))
        return source

    def replay_fixture(self, command, **kwargs):
        if command[1] == 'paper-execution-replay':
            output = Path(command[command.index('--output-dir')+1])
            output.mkdir()
            (output/'market').mkdir()
            shutil.copytree(Path(command[command.index('--input')+1]), output/'market/source')
            (output/'scenario.json').write_bytes(Path(command[command.index('--scenario')+1]).read_bytes())
            for target, suffix in [('paper-input.jsonl','input.jsonl'), ('paper-updates.jsonl','updates.jsonl'),
                                   ('paper-report.json','report.json'), ('market-links.jsonl','links.jsonl'),
                                   ('execution-trace.jsonl','trace.jsonl'), ('execution-replay.json','execution.json')]:
                (output/target).write_bytes((PROJECT/'fixtures'/('paper-execution-v3.'+suffix)).read_bytes())
            kwargs['stdout'].write((output/'execution-replay.json').read_bytes())
        else:
            kwargs['stdout'].write((PROJECT/'fixtures/paper-execution-v3.updates.jsonl').read_bytes())
            kwargs['stderr'].write((PROJECT/'fixtures/paper-execution-v3.report.json').read_bytes())
        return SimpleNamespace(returncode=0)

    def generate(self, root, callback, origin='synthetic_fixture', **kwargs):
        source = self.prepare(root)
        with patch.object(MODULE.subprocess, 'run', side_effect=callback):
            return MODULE.generate(Path('/usr/bin/true'), source, PROJECT/'fixtures/paper-ioc-scenario-v1.json', root/'view', origin, **kwargs)

    def test_no_view_still_runs_both_audits_with_bounded_children(self):
        calls=[]
        def callback(command, **kwargs):
            calls.append((command[1], kwargs['timeout']))
            return self.replay_fixture(command, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=self.generate(root, callback, render_view=False, timeout_secs=7)
            self.assertEqual(result.name, 'execution-replay.json')
            self.assertEqual(calls, [('paper-execution-replay',7),('paper-replay',7)])
            self.assertFalse((root/'view/paper-lab.html').exists())
            self.assertEqual(json.loads((root/'view/cost-audit.json').read_text())['status'], 'verified')

    def test_invalid_native_timeouts_fail_before_creating_output(self):
        for timeout in (0, -1, True, float('nan'), 601):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                with self.assertRaisesRegex(ValueError, 'timeout'):
                    self.generate(root, self.replay_fixture, timeout_secs=timeout)
                self.assertFalse((root/'view').exists())

    def test_portable_execution_view_has_explicit_assumptions_and_independent_decimal_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.generate(root, self.replay_fixture)
            html = path.read_text()
            self.assertIn('"kind":"recorded_execution"', html)
            self.assertIn('"origin":"synthetic_fixture"', html)
            self.assertNotIn('__PAPER_BOOT__', html)
            self.assertNotIn('__GIETHOORN_THEME__', html)
            audit = json.loads((root/'view/cost-audit.json').read_text())
            self.assertEqual(audit['status'], 'verified')
            self.assertEqual(audit['assumed_fills'], 2)
            self.assertEqual(audit['fees'], '0.02511250125')
            with patch.object(MODULE.subprocess, 'run', side_effect=self.replay_fixture):
                with self.assertRaises(FileExistsError):
                    MODULE.generate(Path('/usr/bin/true'), root/'source', PROJECT/'fixtures/paper-ioc-scenario-v1.json', root/'view', 'synthetic_fixture')

    def test_fixture_origin_cannot_be_presented_as_captured_market_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'source/model'):
                self.generate(root, self.replay_fixture, 'captured_public_data')
            self.assertFalse((root/'view/paper-lab.html').exists())

    def mutate(self, filename, mutate):
        def callback(command, **kwargs):
            result = self.replay_fixture(command, **kwargs)
            if command[1] == 'paper-execution-replay':
                output = Path(command[command.index('--output-dir')+1])
                path = output/filename
                values = [json.loads(line) for line in path.read_text().splitlines()]
                mutate(values)
                path.write_text(''.join(json.dumps(value)+'\n' for value in values))
            return result
        return callback

    def test_wrong_assumed_fee_fails_independent_cost_verification(self):
        def wrong(frames):
            next(f for f in frames if f['assumed_fill'])['assumed_fill']['fee'] = '99'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'cost decomposition'):
                self.generate(root, self.mutate('paper-updates.jsonl', wrong))
            self.assertFalse((root/'view/paper-lab.html').exists())

    def test_fills_cannot_exceed_the_original_displayed_size_fraction(self):
        def wrong(frames):
            next(f for f in frames if f['assumed_fill'])['assumed_fill']['quantity'] = '100'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'top-size cap'):
                self.generate(root, self.mutate('paper-updates.jsonl', wrong))
            self.assertFalse((root/'view/paper-lab.html').exists())

    def test_a_forged_arrival_time_cannot_pass_the_replay_audit(self):
        def wrong(trace):
            next(t for t in trace if t['phase'] == 'assumed_fill')['arrival_ns'] = 999999999
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'timing window'):
                self.generate(root, self.mutate('execution-trace.jsonl', wrong))
            self.assertFalse((root/'view/paper-lab.html').exists())

    def test_changed_scenario_bytes_are_not_accepted(self):
        def callback(command, **kwargs):
            result = self.replay_fixture(command, **kwargs)
            if command[1] == 'paper-execution-replay':
                output = Path(command[command.index('--output-dir')+1])
                (output/'scenario.json').write_text('{}\n')
            return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'scenario provenance'):
                self.generate(root, callback)
            self.assertFalse((root/'view/paper-lab.html').exists())

    def test_divergent_independent_ledger_output_prevents_view_creation(self):
        def callback(command, **kwargs):
            result = self.replay_fixture(command, **kwargs)
            if command[1] == 'paper-replay':
                kwargs['stdout'].write(b'changed\n')
            return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'ledger replay'):
                self.generate(root, callback)
            self.assertFalse((root/'view/paper-lab.html').exists())
