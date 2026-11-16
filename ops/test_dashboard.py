import fcntl
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('dashboard', Path(__file__).parent / 'dashboard.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DashboardTests(unittest.TestCase):
    """Synthetic monitor inputs; these are never labeled real exchange evidence."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.experiment = Path(self.temp.name) / 'experiment'
        self.root = self.experiment / 'supervision'
        self.root.mkdir(parents=True)
        self.now = 10_000_000_000_000
        self.origin = self.now - 30_000_000_000
        self.policy = dict(profile='combined', depth_stale_after_ms=15000,
                           bbo_stale_after_ms=2000, timer_interval_ms=250)
        self.save('configuration.json', dict(event_schema_version=2, feed_policy=self.policy,
                 duration_secs=86400, coin='BTC', network='mainnet', max_total_recording_bytes=4294967296))
        self.controls = [self.control('started', 0, {}), self.control('child_started', 1000,
                         dict(run=1, directory='run-000001', pid=123))]
        self.save_lines('events.jsonl', self.controls)
        self.save_lines('resources.jsonl', [dict(elapsed_ns=29_000_000_000, rss_bytes=10485760,
                                               open_fds=6, run=1, pid=123)])
        self.lock = (self.root / 'supervisor.lock').open('wb')
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        run = self.root / 'run-000001'
        run.mkdir()
        self.quote = dict(sequence=12, connection_id=1, local_time_ns=self.now-100_000_000,
                          monotonic_ns=28_900_000_000, exchange_time_ms=9890000,
                          coin='BTC', bid='100.1234567890123456789', ask='101',
                          mid='100.56172839450617283945', spread='0.8765432109876543211')
        self.output = dict(normalization_version=2, kind='bbo', sequence=12, connection_id=1,
                           local_time_ns=self.quote['local_time_ns'], monotonic_ns=self.quote['monotonic_ns'],
                           coin='BTC', quote=self.quote,
                           feeds={source:dict(status='fresh', acknowledged=True, stale_after_ms=limit,
                              latest_sequence=12, exchange_time_ms=9890000, age_ns=age)
                              for source, limit, age in [('depth',15000,300_000_000),('bbo',2000,0)]})
        self.output['feeds']['all_required_fresh'] = True
        (run / 'live-quotes.jsonl').write_text(json.dumps(self.output)+'\n')

    def tearDown(self):
        self.lock.close()
        self.temp.cleanup()

    def control(self, kind, ms, data):
        return dict(kind=kind, elapsed_ns=ms*1_000_000,
                    local_time_ns=self.origin+ms*1_000_000, data=data)

    def save(self, name, value):
        (self.root/name).write_text(json.dumps(value)+'\n')

    def save_lines(self, name, values):
        (self.root/name).write_text(''.join(json.dumps(value)+'\n' for value in values))

    def test_prices_keep_exact_strings_and_monitor_does_not_write_evidence(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        state=MODULE.snapshot(self.experiment,self.now)
        self.assertEqual(state['gate_status'],'running')
        self.assertEqual(state['feeds']['bbo']['status'],'fresh')
        self.assertEqual(state['feeds']['bbo']['age_ms'],100)
        self.assertEqual(state['feeds']['depth']['age_ms'],400)
        self.assertEqual(state['feeds']['bbo']['quote']['bid'],self.quote['bid'])
        self.assertEqual(state['verified_observations'],0)
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_monitor_ages_an_idle_feed_without_new_messages(self):
        state=MODULE.snapshot(self.experiment,self.now+3_000_000_000)
        self.assertEqual(state['feeds']['bbo']['status'],'stale')
        self.assertEqual(state['feeds']['depth']['status'],'fresh')
        self.assertFalse(state['final_audit_verified'])

    def test_observer_time_is_captured_after_concurrent_output_reads(self):
        with patch.object(MODULE.time,'time_ns',side_effect=[self.now-1_000_000_000,self.now]):
            state=MODULE.snapshot(self.experiment)
        self.assertFalse(state['clock_uncertain'])
        self.assertEqual(state['feeds']['bbo']['status'],'fresh')

    def test_backwards_clock_is_uncertain_and_stopped_producer_is_not_fresh(self):
        state=MODULE.snapshot(self.experiment,self.now-1_000_000_000)
        self.assertEqual(state['feeds']['bbo']['status'],'clock_uncertain')
        self.lock.close()
        state=MODULE.snapshot(self.experiment,self.now)
        self.assertEqual(state['gate_status'],'incomplete')
        self.assertEqual(state['feeds']['bbo']['status'],'disconnected')

    def test_new_child_cannot_inherit_the_previous_childs_freshness(self):
        self.controls.extend([self.control('child_exited',29900,dict(run=1,exit_code=0,signal=None)),
                              self.control('child_validated',29901,dict(run=1,comparison='exact',snapshots=42,recording_bytes=9000)),
                              self.control('child_started',29902,dict(run=2,directory='run-000002',pid=124))])
        self.save_lines('events.jsonl',self.controls)
        (self.root/'run-000002').mkdir()
        state=MODULE.snapshot(self.experiment,self.now)
        self.assertEqual(state['current_run'],2)
        self.assertEqual(state['validated_runs'],1)
        self.assertEqual(state['verified_observations'],42)
        self.assertEqual(state['feeds']['bbo']['status'],'awaiting_data')
        self.assertEqual(state['feeds']['bbo']['quote']['run'],1)

    def test_full_window_needs_consistent_completed_summary_experiment_and_audit(self):
        self.lock.close()
        summary=dict(status='completed_with_restarts',elapsed_ns=86400*1_000_000_000)
        self.save('summary.json',summary)
        self.assertEqual(MODULE.snapshot(self.experiment,self.now)['gate_status'],'audit_pending')
        (self.experiment/'experiment.json').write_text(json.dumps(dict(status='completed'))+'\n')
        audit=dict(integrity='verified',full_window_completed=False)
        (self.experiment/'audit.json').write_text(json.dumps(audit)+'\n')
        self.assertFalse(MODULE.snapshot(self.experiment,self.now)['final_audit_verified'])
        audit['full_window_completed']=True
        (self.experiment/'audit.json').write_text(json.dumps(audit)+'\n')
        self.assertEqual(MODULE.snapshot(self.experiment,self.now)['gate_status'],'passed')
        summary['status']='failed'
        self.save('summary.json',summary)
        self.assertEqual(MODULE.snapshot(self.experiment,self.now)['gate_status'],'failed')

    def test_partial_last_lines_are_provisional_but_complete_corruption_is_an_error(self):
        path=self.root/'run-000001/live-quotes.jsonl'
        with path.open('ab') as output:output.write(b'{"partial":')
        self.assertEqual(MODULE.snapshot(self.experiment,self.now)['feeds']['bbo']['status'],'fresh')
        with path.open('ab') as output:output.write(b'bad}\n')
        with self.assertRaises(ValueError):MODULE.snapshot(self.experiment,self.now)

    def test_bounded_tail_drops_only_the_leading_fragment(self):
        path=self.root/'tail.jsonl'
        path.write_bytes(b'{"value":1}\n{"value":2}\n{"value":3}\n')
        self.assertEqual(MODULE.json_lines(path,26,tail=True),[{'value':2},{'value':3}])

    def test_snapshot_embeds_data_safely_and_contains_all_assets(self):
        state=MODULE.snapshot(self.experiment,self.now)
        state['experiment']='</script><script>unexpected()</script>'
        html=MODULE.render_html(state,'snapshot').decode()
        self.assertNotIn(state['experiment'],html)
        self.assertIn('\\u003c/script\\u003e',html)
        self.assertIn('"mode":"snapshot"',html)
        self.assertNotIn('src="http',html)

    def test_http_surface_is_read_only_and_does_not_serve_arbitrary_files(self):
        server=MODULE.server_for(self.experiment,port=0)
        worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05})
        worker.start()
        try:
            for method,path,expected in [('GET','/api/state',200),('GET','/../Cargo.toml',404),
                                          ('GET','/api/read?path=/etc/passwd',404),('POST','/api/state',405)]:
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                conn.request(method,path)
                response=conn.getresponse();body=response.read()
                self.assertEqual(response.status,expected)
                if path=='/api/state' and method=='GET':
                    value=json.loads(body)
                    self.assertEqual(value['schema_version'],1)
                    self.assertNotIn('pid',value['runs'][0])
                conn.close()
        finally:
            server.shutdown();server.server_close();worker.join(timeout=5)

    def test_batch_route_is_explicit_fixed_and_read_only(self):
        batch=Path(self.temp.name)/'batch.html';batch.write_text('<!doctype html><title>Synthetic batch fixture</title>')
        for configured in (None,batch):
            server=MODULE.server_for(self.experiment,port=0,batch_view=configured)
            worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05});worker.start()
            try:
                for method,path,expected in [('GET','/batch',200 if configured else 404),
                                              ('GET','/batch/source',404),('POST','/batch',405)]:
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request(method,path);response=conn.getresponse();body=response.read();conn.close()
                    self.assertEqual(response.status,expected)
                    if method=='GET' and path=='/batch' and configured:self.assertEqual(body,batch.read_bytes())
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                conn.request('GET','/api/state');response=conn.getresponse();state=json.loads(response.read());conn.close()
                self.assertEqual(state['batch_available'],configured is not None)
                self.assertFalse(state['paper_lab_available'])
                if configured:
                    batch.unlink()
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request('GET','/batch');response=conn.getresponse();response.read();conn.close()
                    self.assertEqual(response.status,503)
            finally:
                server.shutdown();server.server_close();worker.join(timeout=5)

    def test_research_routes_refuse_symlink_views(self):
        view=Path(self.temp.name)/'view.html';view.write_text('Synthetic fixture')
        link=Path(self.temp.name)/'link.html';link.symlink_to(view)
        for option in ['paper_view','batch_view']:
            with self.assertRaises((ValueError,OSError)):
                MODULE.server_for(self.experiment,port=0,**{option:link})

    def test_paper_route_is_explicit_opt_in_and_does_not_execute_a_binary(self):
        paper=Path(self.temp.name)/'paper.html';paper.write_text('<!doctype html><title>Synthetic paper view</title>')
        for configured in (None,paper):
            server=MODULE.server_for(self.experiment,port=0,paper_view=configured)
            worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05});worker.start()
            try:
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                conn.request('GET','/paper');response=conn.getresponse();body=response.read();conn.close()
                self.assertEqual(response.status,200 if configured else 404)
                if configured:self.assertEqual(body,paper.read_bytes())
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                conn.request('GET','/api/state');response=conn.getresponse();state=json.loads(response.read());conn.close()
                self.assertEqual(state['paper_lab_available'],configured is not None)
            finally:
                server.shutdown();server.server_close();worker.join(timeout=5)


if __name__=='__main__':
    unittest.main()
