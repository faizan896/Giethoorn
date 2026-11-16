import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

OPS = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('render_service', OPS / 'render_service.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OperationsTests(unittest.TestCase):
    def test_unit_keeps_fail_stop_and_owns_the_whole_process_group(self):
        unit = MODULE.render(Path('/usr/bin/true'), OPS / 'run-collector-service', Path('/var/lib/giethoorn'), 'giethoorn')
        for policy in ('Restart=no', 'KillMode=control-group', 'KillSignal=SIGTERM', 'TimeoutStopSec=60', 'StateDirectory=giethoorn', 'NoNewPrivileges=yes'):
            self.assertIn(policy, unit)
        self.assertNotIn('@STATE@', unit)
        self.assertIn('WorkingDirectory=/var/lib/giethoorn\n', unit)
        self.assertNotIn('WorkingDirectory="', unit)

    def test_renderer_quotes_paths_and_rejects_directive_injection(self):
        self.assertEqual(MODULE.quote('/a path/100%/"quote"'), '"/a path/100%%/\\"quote\\""')
        with self.assertRaises(ValueError):
            MODULE.quote('/tmp/x\nRestart=always')
        with self.assertRaises(ValueError):
            MODULE.render(Path('/usr/bin/true'), OPS / 'run-collector-service', Path('/tmp/state'), 'root\nRestart=always')
        for path in ('/tmp/state ', '/tmp/state\\', '/tmp/${STATE}', '/tmp/$STATE'):
            with self.assertRaises(ValueError):
                MODULE.render(Path('/usr/bin/true'), OPS / 'run-collector-service', Path(path), 'giethoorn')
        for binary, runner in ((Path('/tmp/${BINARY}'), OPS / 'run-collector-service'),
                               (Path('/usr/bin/true'), Path('/tmp/$RUNNER'))):
            with self.assertRaises(ValueError):
                MODULE.render(binary, runner, Path('/tmp/state'), 'giethoorn')

    def test_template_tokens_in_a_binary_filename_are_preserved_literally(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / '@STATE@'
            binary.write_text('#!/bin/sh\nexit 0\n')
            binary.chmod(0o755)
            unit = MODULE.render(binary, OPS / 'run-collector-service', Path('/tmp/state'), 'giethoorn')
            self.assertIn(str(binary), unit)

    def test_runner_uses_new_paths_preserves_arguments_and_propagates_failure(self):
        with tempfile.TemporaryDirectory(prefix='giethoorn-operations-') as directory:
            root = Path(directory)
            binary = root / 'collector fixture'
            binary.write_text('#!/usr/bin/env python3\nimport json, os, sys\nopen(os.environ["GIETHOORN_TEST_ARGUMENTS"], "w").write(json.dumps(sys.argv[1:]))\nsys.exit(11)\n')
            binary.chmod(0o755)
            arguments = root / 'arguments.json'
            state = root / 'state with spaces'
            env = dict(os.environ, GIETHOORN_TEST_ARGUMENTS=str(arguments))
            output_dirs = []
            for _ in range(2):
                result = subprocess.run([str(OPS / 'run-collector-service'), '--binary', str(binary), '--state-dir', str(state), '--', '--coin', 'BTC', '--duration-secs', '5'], env=env, capture_output=True, check=False)
                self.assertEqual(result.returncode, 11)
                actual = json.loads(arguments.read_text())
                self.assertEqual(actual[0], 'supervise')
                self.assertEqual(actual[3:], ['--coin', 'BTC', '--duration-secs', '5'])
                self.assertTrue(Path(actual[2]).is_relative_to(state))
                output_dirs.append(actual[2])
            self.assertNotEqual(output_dirs[0], output_dirs[1])

    def test_runner_rejects_missing_binary_before_creating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state'
            result = subprocess.run([str(OPS / 'run-collector-service'), '--binary', str(Path(directory) / 'missing'), '--state-dir', str(state)], capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(state.exists())


if __name__ == '__main__':
    unittest.main()
