import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

PROJECT = Path(__file__).resolve().parent.parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, PROJECT/'ops'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


LOCAL = module('run_local')
PACKAGE = module('package_mac')


class LocalRelayTests(unittest.TestCase):
    def test_direct_relay_forwards_only_opaque_payload_and_can_close_owned_streams(self):
        upstream=socket.socket();upstream.bind(('127.0.0.1',0));upstream.listen();upstream.settimeout(5)
        payloads=[]
        def echo():
            stream,_=upstream.accept()
            with stream:
                stream.settimeout(5)
                value=stream.recv(4096);payloads.append(value);stream.sendall(value)
                while stream.recv(4096):pass
        worker=threading.Thread(target=echo);worker.start()
        proxy=LOCAL.DirectProxy('api.hyperliquid.xyz:443')
        server=threading.Thread(target=proxy.serve_forever,kwargs={'poll_interval':.05});server.start()
        original=socket.create_connection
        def connect(address,**kwargs):
            self.assertEqual(address,('api.hyperliquid.xyz',443))
            return original(upstream.getsockname(),**kwargs)
        try:
            with original(proxy.server_address,timeout=5) as client, patch.object(LOCAL.socket,'create_connection',side_effect=connect):
                client.sendall(b'CONNECT api.hyperliquid.xyz:443 HTTP/1.1\r\n\r\n')
                self.assertIn(b'200',LOCAL.EXPERIMENT.headers(client))
                client.sendall(b'synthetic-opaque-TLS-payload')
                self.assertEqual(client.recv(4096),b'synthetic-opaque-TLS-payload')
                proxy.disconnect()
                self.assertEqual(client.recv(4096),b'')
        finally:
            proxy.disconnect();proxy.shutdown();proxy.server_close();server.join(5);worker.join(5);upstream.close()
        self.assertFalse(worker.is_alive())
        self.assertEqual(payloads,[b'synthetic-opaque-TLS-payload'])

    def test_relay_rejects_other_destinations_before_opening_an_outbound_socket(self):
        proxy=LOCAL.DirectProxy('api.hyperliquid.xyz:443')
        server=threading.Thread(target=proxy.serve_forever,kwargs={'poll_interval':.05});server.start()
        try:
            with socket.create_connection(proxy.server_address,timeout=2) as client:
                with patch.object(LOCAL.socket,'create_connection') as outbound:
                    client.sendall(b'CONNECT example.org:443 HTTP/1.1\r\n\r\n')
                    self.assertIn(b'403',LOCAL.EXPERIMENT.headers(client));outbound.assert_not_called()
        finally:
            proxy.disconnect();proxy.shutdown();proxy.server_close();server.join(5)
        with self.assertRaises(RuntimeError):LOCAL.DirectProxy('arbitrary.invalid:443')


class LocalLauncherTests(unittest.TestCase):
    def args(self,root,**changes):
        return argparse.Namespace(**dict(dict(binary=Path('/usr/bin/true'),output_dir=root/'run',network='mainnet',route='direct',
                    duration_secs=90,run_duration_secs=45,disconnect_at_secs=10,kill_at_secs=25),**changes))

    def test_direct_route_restores_environment_and_does_not_relabel_a_short_run_as_24_hours(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'HTTPS_PROXY':'http://synthetic-private-route.invalid:8080'}):
            root=Path(directory);original={k:os.environ.get(k) for k in LOCAL.PROXY_KEYS}
            def experiment(args):
                self.assertTrue(os.environ['HTTPS_PROXY'].startswith('http://127.0.0.1:'))
                self.assertEqual(args.output_dir,root/'run/experiment')
                return 0
            with patch.object(LOCAL.EXPERIMENT,'run',side_effect=experiment):self.assertEqual(LOCAL.run(self.args(root)),0)
            self.assertEqual({k:os.environ.get(k) for k in LOCAL.PROXY_KEYS},original)
            result=json.loads((root/'run/local-result.json').read_text())
            self.assertTrue(result['full_window_verified']);self.assertFalse(result['verified_24_hour_window'])
            receipt=(root/'run/local-run.json').read_text()
            self.assertNotIn('synthetic-private-route',receipt)
            self.assertIn('direct venue TCP',receipt)

    def test_failure_retains_diagnostics_and_restores_the_original_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original={k:os.environ.get(k) for k in LOCAL.PROXY_KEYS}
            with patch.object(LOCAL.EXPERIMENT,'run',side_effect=RuntimeError('synthetic injected failure')):
                self.assertEqual(LOCAL.run(self.args(root)),1)
            self.assertEqual({k:os.environ.get(k) for k in LOCAL.PROXY_KEYS},original)
            report=json.loads((root/'run/local-result.json').read_text())
            self.assertEqual(report['status'],'failed');self.assertFalse(report['full_window_verified'])
            with self.assertRaises(FileExistsError):LOCAL.run(self.args(root))

    def test_inherited_route_and_invalid_schedule_fail_before_making_output(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True):
            root=Path(directory)
            with self.assertRaises(RuntimeError):LOCAL.run(self.args(root,route='inherit'))
            self.assertFalse((root/'run').exists())
            with self.assertRaises(RuntimeError):LOCAL.run(self.args(root,duration_secs=40))
            self.assertFalse((root/'run').exists())


class MacScriptTests(unittest.TestCase):
    def prepare(self,root):
        project=root/'project with spaces';(project/'scripts').mkdir(parents=True)
        (project/'scripts/mac').write_bytes((PROJECT/'scripts/mac').read_bytes())
        fake=root/'bin';fake.mkdir()
        backend=root/'fake.py'
        backend.write_text('''import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['GIETHOORN_TEST_LOG'],'a') as f:f.write(json.dumps(args)+'\\n')
if args[0]=='info':
 if args[-1]=='{{.NCPU}} {{.MemTotal}}':print('2 '+os.environ.get('GIETHOORN_TEST_MEMORY','4294967296'))
 elif args[-1]=='{{json .SecurityOptions}}':print('[]')
 else:print('linux')
 sys.exit(int(os.environ.get('GIETHOORN_TEST_ENGINE','0')))
if args[:2]==['image','inspect']:sys.exit(0)
if args[0]=='run' and '/app/ops/paper_market.py' in args:
 if os.environ.get('GIETHOORN_TEST_CASE')=='replay-failure':sys.exit(7)
 target=next(args[i+1] for i,v in enumerate(args) if v=='--mount' and 'dst=/data' in args[i+1])
 source=target.split('src=',1)[1].split(',dst=',1)[0]
 view=Path(source)/'lab/paper-lab.html';view.parent.mkdir();view.write_text('synthetic orchestration view')
 sys.exit(0)
if args[0]=='inspect':
 if os.environ.get('GIETHOORN_TEST_CASE')=='active-review':
  if '--format' in args:print('true')
  sys.exit(0)
 if 'foreign' in os.environ.get('GIETHOORN_TEST_CASE',''):
  if '--format' in args:print('false')
  sys.exit(0)
 sys.exit(1)
if args[0]=='run' and '--name' in args:
 name=args[args.index('--name')+1]
 if 'monitor' in name and os.environ.get('GIETHOORN_TEST_CASE')=='monitor-failure':sys.exit(1)
 print('synthetic-container-id')
''')
        (fake/'docker').write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(backend))+' "$@"\n')
        (fake/'docker').chmod(0o755)
        return project,dict(os.environ,PATH=str(fake)+os.pathsep+os.environ['PATH'],
            GIETHOORN_DATA_DIR=str(root/'saved data'),GIETHOORN_TEST_LOG=str(root/'calls.jsonl'))

    def test_setup_quotes_paths_and_builds_without_starting_any_live_container(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root)
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'setup'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            build=next(c for c in calls if c[0]=='build')
            self.assertEqual(build[-1],str(project));self.assertIn('linux/amd64',build)
            self.assertFalse(any(c[0]=='run' for c in calls))
            self.assertTrue((root/'saved data').is_dir())

    def test_missing_engine_stops_before_build_or_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);env['GIETHOORN_TEST_ENGINE']='1'
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'setup'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('Docker Desktop',result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            self.assertFalse(any(c[0] in ('build','run') for c in calls))

    def test_insufficient_vm_memory_stops_before_a_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);env['GIETHOORN_TEST_MEMORY']='1073741824'
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'setup'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('4 GB RAM',result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            self.assertFalse(any(c[0] in ('build','run') for c in calls))

    def test_stop_refuses_to_touch_a_container_with_another_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);env['GIETHOORN_TEST_CASE']='foreign'
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'stop'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            self.assertFalse(any(c[0] in ('stop','rm') for c in calls))

    def test_monitor_launch_failure_stops_the_new_collector_and_keeps_its_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);env['GIETHOORN_TEST_CASE']='monitor-failure'
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'rehearsal'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('Collector stopped',result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            self.assertTrue(any(c[0]=='stop' and any('collector' in a for a in c) for c in calls))
            run=(root/'saved data/last-run').read_text().strip()
            self.assertTrue((root/'saved data'/run).is_dir())

    def test_review_mounts_originals_read_only_without_starting_or_stopping_a_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root)
            (project/'ops').mkdir()
            (project/'ops/review_local.py').write_bytes((PROJECT/'ops/review_local.py').read_bytes())
            source=root/'saved data/start-fixture';source.mkdir(parents=True)
            (source.parent/'last-run').write_text('start-fixture\n')
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'review'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            runs=[c for c in calls if c[0]=='run']
            self.assertEqual(len(runs),1)
            self.assertEqual(runs[0][runs[0].index('--network')+1],'none')
            self.assertIn('--read-only',runs[0])
            mounts=[runs[0][i+1] for i,v in enumerate(runs[0]) if v=='--mount']
            self.assertTrue(any('dst=/source,readonly' in m for m in mounts))
            self.assertTrue(any('dst=/review_local.py,readonly' in m for m in mounts))
            self.assertFalse(any(c[0] in ('build','stop','rm') for c in calls))
            self.assertNotIn('--detach',runs[0])

    def test_review_refuses_an_active_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root)
            source=root/'saved data/start-fixture';source.mkdir(parents=True)
            (source.parent/'last-run').write_text('start-fixture\n')
            env['GIETHOORN_TEST_CASE']='active-review'
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'review'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('still running',result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            self.assertFalse(any(c[0] in ('run','build','stop','rm') for c in calls))

    def replay_source(self, root):
        source=root/'saved data/start-fixture'
        session=source/'run/experiment/supervision/run-000134/session'
        session.mkdir(parents=True)
        (session/'index.jsonl').write_text('synthetic orchestration index\n')
        (source.parent/'last-run').write_text('start-fixture\n')
        return source

    def test_replay_opens_only_the_explicit_recording_offline_with_bounded_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);source=self.replay_source(root)
            original=(source/'run/experiment/supervision/run-000134/session/index.jsonl').read_bytes()
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'replay','000134'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            run=next(c for c in calls if c[0]=='run')
            self.assertEqual(run[run.index('--input')+1],'/source/run/experiment/supervision/run-000134/session')
            self.assertEqual(run[run.index('--origin')+1],'captured-public-data')
            self.assertEqual(run[run.index('--feed')+1],'bbo')
            self.assertEqual(run[run.index('--network')+1],'none')
            self.assertIn('--read-only',run);self.assertIn('180s',run)
            self.assertIn('--kill-after=10s',run)
            self.assertTrue(any('dst=/source,readonly' in c for c in run))
            self.assertFalse(any(c[0] in ('build','stop','rm') or '--detach' in c for c in calls))
            view=next((root/'saved data').glob('replay-*/lab/paper-lab.html'))
            self.assertIn(str(view),result.stdout)
            self.assertIn('Child: run-000134',(view.parent.parent/'source-selection.txt').read_text())
            self.assertEqual(original,(source/'run/experiment/supervision/run-000134/session/index.jsonl').read_bytes())

    def test_replay_refuses_invalid_or_missing_children_before_running_a_container(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);self.replay_source(root)
            for value in ('0','000000','-1','1.2','../134','1000000','135'):
                with self.subTest(child=value):
                    result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'replay',value],env=env,capture_output=True,text=True)
                    self.assertNotEqual(result.returncode,0)
            log=root/'calls.jsonl'
            calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            self.assertFalse(any(c[0] in ('run','build','stop','rm') for c in calls))
            self.assertFalse(list((root/'saved data').glob('replay-*')))

    def test_replay_keeps_failed_evidence_and_propagates_native_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);source=self.replay_source(root)
            env['GIETHOORN_TEST_CASE']='replay-failure'
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'replay','134'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,7,result.stderr)
            self.assertIn('Replay saved:',result.stdout)
            self.assertTrue(source.exists())
            self.assertTrue(next((root/'saved data').glob('replay-*/source-selection.txt')).exists())
            self.assertFalse(list((root/'saved data').glob('replay-*/lab/paper-lab.html')))

    def test_replay_refuses_an_active_collector_without_creating_replay_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,env=self.prepare(root);self.replay_source(root)
            env['GIETHOORN_TEST_CASE']='active-review'
            result=subprocess.run(['/bin/bash',str(project/'scripts/mac'),'replay','134'],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('still running',result.stderr)
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            self.assertFalse(any(c[0] in ('run','build','stop','rm') for c in calls))
            self.assertFalse(list((root/'saved data').glob('replay-*')))


class MacPackageTests(unittest.TestCase):
    def prepare(self,root):
        for name in PACKAGE.SINGLES:(root/name).write_text('synthetic package test\n')
        for name in PACKAGE.DIRECTORIES:(root/name).mkdir()
        (root/'docs/local-mac.md').write_text('Synthetic setup instructions\n')
        (root/'scripts/mac').write_text('#!/bin/bash\n');(root/'scripts/mac').chmod(0o755)
        (root/'src/main.rs').write_text('// synthetic fixture\n')

    def test_export_preserves_executable_modes_and_checksums_and_excludes_local_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.prepare(root)
            for name in ['data','target','.ssh','.git']:
                (root/name).mkdir();(root/name/'private').write_text('synthetic excluded marker')
            (root/'.env').write_text('synthetic excluded marker')
            (root/'ops/.env.local').write_text('synthetic excluded marker')
            (root/'ops/private.key').write_text('synthetic excluded marker')
            output=root/'export.zip'
            with patch.object(PACKAGE,'PROJECT',root):PACKAGE.package(output)
            with zipfile.ZipFile(output) as archive:
                names=archive.namelist();manifest=json.loads(archive.read(PACKAGE.ROOT+'TRANSFER-MANIFEST.json'))
                self.assertTrue(all(n.startswith(PACKAGE.ROOT) and '..' not in Path(n).parts for n in names))
                self.assertFalse(any('private' in n or '.env' in n for n in names))
                self.assertEqual((archive.getinfo(PACKAGE.ROOT+'scripts/mac').external_attr>>16)&0o777,0o755)
                for item in manifest['files']:
                    raw=archive.read(PACKAGE.ROOT+item['file'])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
            before=output.read_bytes()
            with patch.object(PACKAGE,'PROJECT',root),self.assertRaises(FileExistsError):PACKAGE.package(output)
            self.assertEqual(output.read_bytes(),before)

    def test_source_symlinks_fail_before_creating_an_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.prepare(root)
            (root/'src/link.rs').symlink_to(root/'Cargo.toml')
            with patch.object(PACKAGE,'PROJECT',root),self.assertRaisesRegex(ValueError,'symlink'):
                PACKAGE.package(root/'export.zip')
            self.assertFalse((root/'export.zip').exists())


if __name__=='__main__':unittest.main()
