import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parent.parent
SPEC=importlib.util.spec_from_file_location('paper_demo',PROJECT/'ops/paper_demo.py')
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PaperDemoTests(unittest.TestCase):
    def replay_fixture(self,*args,**kwargs):
        # Boundary fixture only; actual Rust accounting has its own golden/CLI tests.
        kwargs['stdout'].write((PROJECT/'fixtures/paper-synthetic-v1.updates.jsonl').read_bytes())
        kwargs['stderr'].write((PROJECT/'fixtures/paper-synthetic-v1.report.json').read_bytes())
        return SimpleNamespace(returncode=0)

    def test_export_is_self_contained_explicitly_synthetic_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'view'
            with patch.object(MODULE.subprocess,'run',side_effect=self.replay_fixture):
                result=MODULE.generate(Path('/usr/bin/true'),PROJECT/'fixtures/paper-synthetic-v1.jsonl',output)
                html=result.read_text()
                self.assertIn('Synthetic scenario.',html)
                self.assertIn('"mode":"paper"',html)
                self.assertNotIn('__PAPER_BOOT__',html)
                self.assertNotIn('<script src=',html)
                self.assertEqual(json.loads((output/'run.json').read_text())['source_kind'],'synthetic')
                with self.assertRaises(FileExistsError):
                    MODULE.generate(Path('/usr/bin/true'),PROJECT/'fixtures/paper-synthetic-v1.jsonl',output)

    def test_non_synthetic_inputs_are_refused_before_artifact_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'scenario.jsonl';output=root/'view'
            value=json.loads((PROJECT/'fixtures/paper-synthetic-v1.jsonl').read_text().splitlines()[0])
            value['event']['config']['source']['kind']='manual_simulation'
            source.write_text(json.dumps(value)+'\n')
            with self.assertRaises(ValueError):MODULE.generate(Path('/usr/bin/true'),source,output)
            self.assertFalse(output.exists())

    def test_failed_replay_keeps_diagnostics_without_publishing_a_view(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'view'
            with patch.object(MODULE.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
                with self.assertRaises(RuntimeError):MODULE.generate(Path('/usr/bin/true'),PROJECT/'fixtures/paper-synthetic-v1.jsonl',output)
            self.assertFalse((output/'paper-lab.html').exists())
            self.assertTrue((output/'paper-report.json').exists())

    def test_inconsistent_account_summary_is_not_rendered_as_a_valid_demo(self):
        def inconsistent(*args,**kwargs):
            result=self.replay_fixture(*args,**kwargs)
            path=Path(kwargs['stderr'].name)
            kwargs['stderr'].flush()
            report=json.loads(path.read_text());report['account']['fees']='0'
            path.write_text(json.dumps(report)+'\n')
            return result
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'view'
            with patch.object(MODULE.subprocess,'run',side_effect=inconsistent):
                with self.assertRaises(ValueError):MODULE.generate(Path('/usr/bin/true'),PROJECT/'fixtures/paper-synthetic-v1.jsonl',output)
            self.assertFalse((output/'paper-lab.html').exists())
