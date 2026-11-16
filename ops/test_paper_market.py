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
SPEC = importlib.util.spec_from_file_location('paper_market', PROJECT/'ops/paper_market.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecordedPaperTests(unittest.TestCase):
    def prepare(self, root):
        source = root/'source'
        source.mkdir()
        raw = (PROJECT/'fixtures/hyperliquid-combined-v2.jsonl').read_bytes()
        (source/'segment-00000001.jsonl').write_bytes(raw)
        entries = [dict(kind='header', container_version=1, event_schema_version=2,
                        max_segment_bytes=1048576, max_session_bytes=2097152),
                   dict(kind='segment', number=1, file='segment-00000001.jsonl', bytes=len(raw),
                        first_sequence=1, last_sequence=29, sha256=hashlib.sha256(raw).hexdigest()),
                   dict(kind='end', segments=1, records=29, data_bytes=len(raw))]
        (source/'index.jsonl').write_text(''.join(json.dumps(e, sort_keys=True, separators=(',', ':'))+'\n' for e in entries))
        return source

    def replay_fixture(self, command, **kwargs):
        if command[1] == 'paper-market-replay':
            output = Path(command[command.index('--output-dir')+1])
            output.mkdir()
            shutil.copytree(Path(command[command.index('--input')+1]), output/'source')
            for target, suffix in [('paper-input.jsonl', 'input.jsonl'), ('paper-updates.jsonl', 'updates.jsonl'),
                                   ('paper-report.json', 'report.json'), ('market-replay.json', 'market.json'),
                                   ('market-links.jsonl', 'links.jsonl'), ('source-manifest.json', 'source.json')]:
                (output/target).write_bytes((PROJECT/'fixtures'/('paper-recorded-v2.'+suffix)).read_bytes())
            kwargs['stdout'].write((output/'market-replay.json').read_bytes())
        else:
            kwargs['stdout'].write((PROJECT/'fixtures/paper-recorded-v2.updates.jsonl').read_bytes())
            kwargs['stderr'].write((PROJECT/'fixtures/paper-recorded-v2.report.json').read_bytes())
        return SimpleNamespace(returncode=0)

    def test_portable_view_keeps_fixture_origin_replay_links_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.prepare(root)
            output = root/'view'
            with patch.object(MODULE.subprocess, 'run', side_effect=self.replay_fixture):
                path = MODULE.generate(Path('/usr/bin/true'), source, output, 'synthetic_fixture')
                html = path.read_text()
                self.assertIn('"origin":"synthetic_fixture"', html)
                self.assertIn('"market_sequence":29', html)
                self.assertNotIn('__PAPER_BOOT__', html)
                self.assertNotIn('__GIETHOORN_THEME__', html)
                self.assertNotIn('<script src=', html)
                self.assertFalse(json.loads((output/'run.json').read_text())['full_window_verified'])
                with self.assertRaises(FileExistsError):
                    MODULE.generate(Path('/usr/bin/true'), source, output, 'synthetic_fixture')

    def test_synthetic_market_fixture_cannot_be_exported_as_captured_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.prepare(root)
            output = root/'view'
            with patch.object(MODULE.subprocess, 'run', side_effect=self.replay_fixture):
                with self.assertRaisesRegex(ValueError, 'origin/feed'):
                    MODULE.generate(Path('/usr/bin/true'), source, output, 'captured_public_data')
            self.assertFalse((output/'paper-lab.html').exists())

    def test_changed_source_copy_fails_manifest_validation(self):
        def altered(command, **kwargs):
            result = self.replay_fixture(command, **kwargs)
            if command[1] == 'paper-market-replay':
                output = Path(command[command.index('--output-dir')+1])
                (output/'source/segment-00000001.jsonl').write_bytes(b'changed\n')
            return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.prepare(root)
            with patch.object(MODULE.subprocess, 'run', side_effect=altered):
                with self.assertRaisesRegex(ValueError, 'source copy'):
                    MODULE.generate(Path('/usr/bin/true'), source, root/'view', 'synthetic_fixture')
            self.assertFalse((root/'view/paper-lab.html').exists())

    def test_unmapped_market_sequence_is_rejected(self):
        def altered(command, **kwargs):
            result = self.replay_fixture(command, **kwargs)
            if command[1] == 'paper-market-replay':
                output = Path(command[command.index('--output-dir')+1])
                path = output/'market-links.jsonl'
                links = [json.loads(line) for line in path.read_text().splitlines()]
                links[5]['market_sequence'] = 999
                path.write_text(''.join(json.dumps(link)+'\n' for link in links))
            return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.prepare(root)
            with patch.object(MODULE.subprocess, 'run', side_effect=altered):
                with self.assertRaisesRegex(ValueError, 'links are inconsistent'):
                    MODULE.generate(Path('/usr/bin/true'), source, root/'view', 'synthetic_fixture')
            self.assertFalse((root/'view/paper-lab.html').exists())

    def test_independent_paper_replay_must_match_exact_derived_bytes(self):
        def altered(command, **kwargs):
            result = self.replay_fixture(command, **kwargs)
            if command[1] == 'paper-replay':
                kwargs['stdout'].write(b'divergent\n')
            return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.prepare(root)
            with patch.object(MODULE.subprocess, 'run', side_effect=altered):
                with self.assertRaisesRegex(ValueError, 'independent paper replay'):
                    MODULE.generate(Path('/usr/bin/true'), source, root/'view', 'synthetic_fixture')
            self.assertFalse((root/'view/paper-lab.html').exists())

    def test_failed_cli_keeps_diagnostics_without_a_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.prepare(root)
            with patch.object(MODULE.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
                with self.assertRaisesRegex(ValueError, 'replay failed'):
                    MODULE.generate(Path('/usr/bin/true'), source, root/'view', 'synthetic_fixture')
            self.assertTrue((root/'view/command.stderr').exists())
            self.assertFalse((root/'view/paper-lab.html').exists())
