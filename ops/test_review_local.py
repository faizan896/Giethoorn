import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('review_local', Path(__file__).with_name('review_local.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReviewTests(unittest.TestCase):
    """Synthetic orchestration receipts, never presented as actual capture evidence."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.experiment = self.base/'run/experiment'
        self.root = self.experiment/'supervision'
        self.root.mkdir(parents=True)
        (self.root/'supervisor.lock').write_bytes(b'')
        (self.root/'synthetic-recording').write_bytes(b'synthetic source bytes')
        self.summary = dict(schema_version=1, status='failed', reason='synthetic watchdog failure',
                            requested_duration_secs=86400, elapsed_ns=41404564431499,
                            runs=[dict(run=134, elapsed_ns=707000000000, exit_code=0, signal=None,
                                       finalized=True, comparison='exact', snapshots=12)])
        self.experiment_report = dict(status='failed', network_recovery_observed=True, crash_recovery_observed=True)
        self.local = dict(status='failed', experiment_exit_code=1, verified_24_hour_window=False)
        self.audit = dict(schema_version=1, integrity='verified', supervisor_status='failed',
                          full_window_completed=False, coin='BTC', network='mainnet',
                          validated_runs=134, started_runs=134, restarts=2, snapshots=334794,
                          recording_bytes=139614246, peak_sampled_rss_bytes=11624448, max_sampled_open_fds=6,
                          runs=[dict(run=n+1, finalized=n!=0) for n in range(134)])
        self.output = self.base/'review'
        self.metadata()

    def metadata(self):
        for path, value in [(self.root/'summary.json', self.summary),
                            (self.experiment/'experiment.json', self.experiment_report),
                            (self.experiment.parent/'local-result.json', self.local)]:
            path.write_text(json.dumps(value)+'\n')

    def native(self, command, **kwargs):
        self.assertEqual(command[1:], ['audit-supervision', '--input', str(self.root)])
        self.assertGreater(kwargs['timeout'], 0)
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertIs(kwargs['preexec_fn'], MODULE.cap_child_output)
        kwargs['stdout'].write(json.dumps(self.audit).encode())
        return SimpleNamespace(returncode=0)

    def review(self, callback=None, **kwargs):
        with patch.object(MODULE.subprocess, 'run', side_effect=callback or self.native):
            return MODULE.review(Path('/usr/bin/true'), self.experiment, self.output, **kwargs)

    def test_valid_failed_archive_keeps_integrity_separate_from_operating_success(self):
        before = MODULE.inventory(self.experiment)
        result = self.review()
        self.assertEqual(result['status'], 'reviewed')
        self.assertEqual(result['integrity'], 'verified')
        self.assertEqual(result['reported_supervisor_status'], 'failed')
        self.assertEqual(result['reported_reason'], 'synthetic watchdog failure')
        self.assertEqual(result['reported_elapsed_seconds'], 41404)
        self.assertEqual(result['audit']['snapshots'], 334794)
        self.assertEqual(result['audit']['finalized_recordings'], 133)
        self.assertEqual(result['audit']['recovered_prefixes'], 1)
        self.assertEqual(result['last_reported_run']['elapsed_seconds'], 707)
        self.assertFalse(result['verified_24_hour_window'])
        self.assertTrue(result['source_unchanged'])
        self.assertEqual(before, MODULE.inventory(self.experiment))
        self.assertEqual(json.loads((self.output/'source-before.json').read_text()),
                         json.loads((self.output/'source-after.json').read_text()))
        self.assertTrue((self.output/'review.json').is_file())

    def test_short_completed_window_cannot_become_a_verified_day(self):
        self.summary.update(status='completed', requested_duration_secs=90, elapsed_ns=90000000000)
        self.experiment_report['status'] = 'completed'
        self.audit.update(supervisor_status='completed', full_window_completed=True)
        self.metadata()
        self.assertFalse(self.review()['verified_24_hour_window'])

    def test_day_requires_native_window_and_both_recoveries_and_local_completion(self):
        self.summary.update(status='completed', elapsed_ns=86400000000000)
        self.experiment_report['status'] = 'completed'
        self.local.update(status='completed', experiment_exit_code=0, verified_24_hour_window=True)
        self.audit.update(supervisor_status='completed', full_window_completed=True)
        self.metadata()
        self.assertTrue(self.review()['verified_24_hour_window'])

    def test_failed_experiment_cannot_become_a_pass_from_native_integrity(self):
        self.summary.update(status='completed', elapsed_ns=86400000000000)
        self.local.update(status='completed', experiment_exit_code=0, verified_24_hour_window=True)
        self.audit.update(supervisor_status='completed', full_window_completed=True)
        self.metadata()
        self.assertFalse(self.review()['verified_24_hour_window'])

    def test_inconsistent_local_completion_or_invalid_native_envelope_stays_unverified(self):
        self.summary.update(status='completed', elapsed_ns=86400000000000)
        self.experiment_report['status'] = 'completed'
        self.audit.update(supervisor_status='completed', full_window_completed=True)
        self.local.update(status='failed', experiment_exit_code=1, verified_24_hour_window=True)
        self.metadata()
        self.assertFalse(self.review()['verified_24_hour_window'])
        self.output=self.base/'other-review'
        self.audit.pop('snapshots')
        result=self.review()
        self.assertEqual(result['integrity'],'unverified')
        self.assertIsNone(result['audit'])

    def test_refused_audit_retains_diagnostics_without_inventing_verified_counts(self):
        def refuse(command, **kwargs):
            kwargs['stderr'].write(b'synthetic checksum mismatch')
            return SimpleNamespace(returncode=1)
        result = self.review(refuse)
        self.assertEqual(result['status'], 'audit_unverified')
        self.assertEqual(result['integrity'], 'unverified')
        self.assertIsNone(result['audit'])
        self.assertFalse(result['verified_24_hour_window'])
        self.assertIn('checksum mismatch', (self.output/'audit.stderr').read_text())
        self.assertEqual(result['audit_diagnostic'], 'synthetic checksum mismatch')

    def test_missing_final_summary_is_not_created_or_repaired(self):
        (self.root/'summary.json').unlink()
        result = self.review(lambda *a, **k: SimpleNamespace(returncode=1))
        self.assertEqual(result['status'], 'audit_unverified')
        self.assertFalse((self.root/'summary.json').exists())
        self.assertTrue(any(e['artifact']=='supervisor' for e in result['metadata_issues']))

    def test_local_completion_receipt_mutation_invalidates_the_review(self):
        def mutate(command, **kwargs):
            result = self.native(command, **kwargs)
            (self.experiment.parent/'local-result.json').write_text('{"status":"changed"}')
            return result
        result = self.review(mutate)
        self.assertFalse(result['source_unchanged'])
        self.assertEqual(result['integrity'], 'unverified')

    def test_timed_out_native_process_is_an_unverified_review(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired('synthetic audit', kwargs['timeout'])
        result = self.review(timeout, timeout_seconds=3)
        self.assertTrue(result['audit_timed_out'])
        self.assertIsNone(result['audit_exit_code'])
        self.assertEqual(result['integrity'], 'unverified')

    def test_input_mutation_cannot_be_reported_as_verified(self):
        def mutate(command, **kwargs):
            result = self.native(command, **kwargs)
            path = self.root/'synthetic-recording'
            original = path.stat()
            path.write_bytes(b'SYNTHETIC source bytes')
            os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
            return result
        result = self.review(mutate)
        self.assertFalse(result['source_unchanged'])
        self.assertEqual(result['integrity'], 'unverified')
        self.assertIsNone(result['audit'])

    def test_active_supervisor_is_refused_before_output_or_native_execution(self):
        with (self.root/'supervisor.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(MODULE.subprocess, 'run') as native:
                with self.assertRaisesRegex(ValueError, 'still active'):
                    MODULE.review(Path('/usr/bin/true'), self.experiment, self.output)
                native.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_output_inside_source_or_an_existing_review_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'outside original'):
            MODULE.review(Path('/usr/bin/true'), self.experiment, self.experiment/'review')
        self.output.mkdir()
        (self.output/'sentinel').write_text('unchanged')
        with self.assertRaises(FileExistsError):self.review()
        self.assertEqual((self.output/'sentinel').read_text(), 'unchanged')

    def test_source_symlinks_and_nonfinite_timeouts_are_rejected(self):
        link = self.root/'link'
        link.symlink_to(self.root/'synthetic-recording')
        with self.assertRaisesRegex(ValueError, 'symlink'):self.review()
        link.unlink()
        for timeout in (0, -1, True, float('nan'), 601):
            with self.assertRaisesRegex(ValueError, 'timeout'):
                MODULE.review(Path('/usr/bin/true'), self.experiment, self.base/'other', timeout)


if __name__ == '__main__':
    unittest.main()
