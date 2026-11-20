"""Native recorder checks against a local TLS WebSocket peer, never an exchange."""
import base64
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

try:
    from . import feed_check as RUN
except ImportError:
    import feed_check as RUN

PROJECT=Path(__file__).resolve().parent.parent
BINARY=Path(os.environ.get('GIETHOORN_TEST_BINARY',str(PROJECT/'target/debug/giethoorn'))).resolve()
IMAGE='sha256:'+'a'*64
TEMPLATE=PROJECT/'web/feed-check.html'
THEME=PROJECT/'web/theme.css'


def receive(stream,n):
    out=b''
    while len(out)<n:
        part=stream.recv(n-len(out))
        if not part:raise EOFError()
        out+=part
    return out


def headers(stream):
    out=b''
    while not out.endswith(b'\r\n\r\n'):
        out+=receive(stream,1)
        if len(out)>16384:raise ValueError('oversized local handshake')
    return out.decode()


def frame(stream):
    first,second=receive(stream,2)
    size=second&127
    if size==126:size=struct.unpack('!H',receive(stream,2))[0]
    if size==127:size=struct.unpack('!Q',receive(stream,8))[0]
    if size>65536:raise ValueError('oversized local frame')
    mask=receive(stream,4) if second&128 else b''
    payload=receive(stream,size)
    return first&15,bytes(v^mask[i%4] for i,v in enumerate(payload)) if mask else payload


def send(stream,value,opcode=1):
    payload=json.dumps(value,separators=(',',':')).encode() if opcode==1 else value
    length=len(payload)
    stream.sendall(bytes([128|opcode,length]) + payload if length<126 else bytes([128|opcode,126])+struct.pack('!H',length)+payload)


class TlsFeed:
    """Ephemeral, loopback-only CONNECT/TLS/WebSocket peer with an explicit test CA."""
    def __init__(self,root,mode='quotes'):
        self.mode=mode;self.connections=0;self.errors=[];self.stopped=threading.Event();self.active=None
        self.cert=root/'test-ca.pem';key=root/'test-peer.key'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-subj','/CN=api.hyperliquid.xyz','-addext','subjectAltName=DNS:api.hyperliquid.xyz',
            '-keyout',str(key),'-out',str(self.cert)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,key)
        self.context=context
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0));self.socket.listen();self.socket.settimeout(.1)
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def environment(self):
        env=RUN.child_environment()
        env.update(https_proxy='http://127.0.0.1:'+str(self.socket.getsockname()[1]),HTTPS_PROXY='',
                   no_proxy='',NO_PROXY='',SSL_CERT_FILE=str(self.cert))
        return env

    def run(self):
        while not self.stopped.is_set():
            try:
                stream,_=self.socket.accept();stream.settimeout(3);self.active=stream;self.connections+=1
                assert headers(stream).startswith('CONNECT api.hyperliquid.xyz:443 HTTP/1.1\r\n')
                if self.mode=='denied':
                    stream.sendall(b'HTTP/1.1 403 Local synthetic denial\r\n\r\n');stream.close();continue
                stream.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                stream=self.context.wrap_socket(stream,server_side=True);self.active=stream
                request=headers(stream)
                key=next(line.split(':',1)[1].strip() for line in request.splitlines() if line.lower().startswith('sec-websocket-key:'))
                accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                stream.sendall(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n').encode())
                for _ in range(2):
                    opcode,payload=frame(stream);assert opcode==1
                    sub=json.loads(payload);assert sub['method']=='subscribe' and sub['subscription']['coin']=='BTC'
                    send(stream,dict(channel='subscriptionResponse',data=sub))
                stream.settimeout(.01)
                tick=0
                while not self.stopped.is_set():
                    if self.mode=='quotes':
                        tick+=1
                        book=[dict(px='100.1',sz='2',n=1),dict(px='100.3',sz='1',n=1)]
                        send(stream,dict(channel='l2Book',data=dict(coin='BTC',time=100000+tick,levels=[[book[0]],[book[1]]])))
                        send(stream,dict(channel='bbo',data=dict(coin='BTC',time=100000+tick,bbo=book)))
                    try:
                        opcode,payload=frame(stream)
                        if opcode==8:send(stream,payload,8);break
                        if opcode==9:send(stream,payload,10)
                    except socket.timeout:
                        pass
                    self.stopped.wait(.04)
                stream.close()
            except socket.timeout:
                continue
            except (EOFError,OSError):
                if self.stopped.is_set():break
            except Exception as error:
                self.errors.append(repr(error));break

    def close(self):
        self.stopped.set()
        if self.active is not None:
            try:self.active.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.active.close()
        self.socket.close();self.thread.join(4)
        if self.thread.is_alive():raise RuntimeError('local TLS peer failed to stop')


@unittest.skipUnless(BINARY.is_file() and shutil.which('openssl'),'native binary and openssl required')
class FeedCheckNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.template=self.root/'template.html';self.template.write_bytes(TEMPLATE.read_bytes())
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(RUN,'BINARY_SHA256',RUN.REVIEW.digest(BINARY)))
        self.stack.enter_context(patch.dict(RUN.POLICY,duration_secs=1,max_reconnects=0))

    def capture(self,mode='quotes',name='capture'):
        peer=TlsFeed(self.root,mode);self.addCleanup(peer.close)
        env=peer.environment()
        with patch.object(RUN,'child_environment',return_value=env):
            result=RUN.capture(BINARY,self.root/name,self.template,THEME,IMAGE,'synthetic_fixture')
        peer.close()
        self.assertFalse(peer.errors)
        return result,peer

    def audit(self,name='report'):
        return RUN.audit(BINARY,self.root/'capture',self.root/name,self.template,THEME,IMAGE)

    def test_real_tls_capture_has_exact_live_replay_and_fresh_native_cadence(self):
        result,peer=self.capture();self.assertEqual(result['status'],'completed',result)
        before=RUN.inventory(self.root/'capture',RUN.LIMITS['capture_bytes'])
        report=self.audit()
        self.assertEqual(report['status'],'completed',report['error'])
        self.assertEqual(report['replay']['comparison'],'exact')
        self.assertEqual(peer.connections,1)
        self.assertEqual(report['cadence']['metrics']['series']['bbo_messages']['observations'],report['cadence']['metrics']['series']['native_opportunities']['observations'])
        self.assertEqual(RUN.inventory(self.root/'capture',RUN.LIMITS['capture_bytes']),before)
        self.assertFalse(report['orders_generated'] or report['profit_evaluated'] or report['measured_order_latency'] or report['full_window_verified'])

    def test_failed_capture_keeps_integrity_diagnosis_without_cadence_or_replacement(self):
        result,peer=self.capture('denied');self.assertEqual(result['status'],'failed')
        report=self.audit()
        self.assertEqual(report['status'],'incomplete')
        self.assertEqual(report['integrity']['status'],'verified')
        self.assertIsNone(report['cadence']['metrics']);self.assertEqual(peer.connections,1)

    def test_empty_capture_is_not_a_completed_check(self):
        result,_=self.capture('empty');self.assertEqual(result['status'],'failed')
        report=self.audit();self.assertEqual(report['status'],'incomplete')
        self.assertIsNone(report['cadence']['metrics'])

    def test_native_timeout_stops_one_child_and_retains_original_result(self):
        with patch.dict(RUN.LIMITS,capture_seconds=.25):
            result,peer=self.capture()
            self.assertTrue(result['timed_out']);self.assertEqual(result['status'],'failed')
            report=self.audit();self.assertEqual(report['status'],'incomplete')
            self.assertIsNone(report['cadence']['metrics']);self.assertEqual(peer.connections,1)

    def test_modified_source_or_live_stream_is_refused_before_audit_output(self):
        self.capture()
        source=self.root/'capture/live.jsonl';source.write_bytes(source.read_bytes()+b'{}\n')
        with self.assertRaisesRegex(ValueError,'changed'):self.audit()
        self.assertFalse((self.root/'report').exists())

    def test_invalid_native_checksum_is_not_treated_as_source_integrity(self):
        self.capture()
        path=self.root/'capture/session/segment-00000001.jsonl';path.write_bytes(path.read_bytes().replace(b'100.1',b'100.2',1))
        receipt=self.root/'capture/capture-result.json';result=json.loads(receipt.read_text())
        result['artifacts']['session/segment-00000001.jsonl']=RUN.inventory(self.root/'capture',RUN.LIMITS['capture_bytes'])['session/segment-00000001.jsonl']
        receipt.write_text(json.dumps(result))
        report=self.audit();self.assertEqual(report['status'],'incomplete')
        self.assertNotEqual(report['integrity']['status'],'verified')
        self.assertIsNone(report['cadence']['metrics'])

    def test_changed_image_or_producer_is_refused(self):
        self.capture()
        with self.assertRaisesRegex(ValueError,'image differs'):
            RUN.audit(BINARY,self.root/'capture',self.root/'report',self.template,THEME,'sha256:'+'b'*64)
        self.template.write_text('changed template')
        with self.assertRaisesRegex(ValueError,'producer'):self.audit()

    def test_input_change_during_audit_invalidates_every_stage_and_measurement(self):
        self.capture();original=RUN.CADENCE.analyze
        def mutate(*args):
            result=original(*args);(self.root/'capture/changed').write_text('synthetic mutation');return result
        with patch.object(RUN.CADENCE,'analyze',side_effect=mutate):report=self.audit()
        self.assertEqual(report['status'],'source_changed')
        self.assertIsNone(report['cadence']['metrics'])
        self.assertEqual(report['replay']['status'],'unavailable')

    def test_report_asset_change_invalidates_all_previously_verified_metrics(self):
        self.capture();original=RUN.CADENCE.analyze
        def mutate(*args):
            result=original(*args);self.template.write_text('synthetic changed asset');return result
        with patch.object(RUN.CADENCE,'analyze',side_effect=mutate):report=self.audit()
        self.assertEqual(report['status'],'source_changed');self.assertTrue(report['input_unchanged'])
        self.assertFalse(report['code_unchanged']);self.assertIsNone(report['cadence']['metrics'])

    def test_runtime_output_budget_stops_capture_without_replacement(self):
        with patch.dict(RUN.LIMITS,capture_bytes=RUN.LIMITS['report_reserve_bytes']+6000):
            result,peer=self.capture()
            self.assertTrue(result['budget_exceeded'],result)
            self.assertEqual(result['status'],'failed');self.assertEqual(peer.connections,1)

    def test_native_tls_still_rejects_an_untrusted_local_certificate(self):
        peer=TlsFeed(self.root);self.addCleanup(peer.close)
        env=peer.environment();env.pop('SSL_CERT_FILE')
        with patch.object(RUN,'child_environment',return_value=env):
            result=RUN.capture(BINARY,self.root/'capture',self.template,THEME,IMAGE,'synthetic_fixture')
        self.assertEqual(result['status'],'failed')
        self.assertIn('verified TLS handshake failed',result['diagnostic'])

    def test_limited_audit_retains_explicit_not_run_metrics(self):
        self.capture()
        with patch.object(RUN,'run_native',side_effect=ValueError('synthetic budget refusal')):
            report=self.audit()
        self.assertEqual(report['status'],'incomplete')
        self.assertEqual(report['integrity']['reason'],'synthetic budget refusal')
        self.assertIsNone(report['cadence']['metrics'])

    def test_symlink_in_capture_is_not_followed(self):
        self.capture();(self.root/'capture/link').symlink_to(BINARY)
        with self.assertRaisesRegex(ValueError,'symlink'):self.audit()

    def test_low_free_space_prevents_connection_and_new_capture(self):
        with patch.object(RUN.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)),patch.object(RUN,'run_native') as run:
            with self.assertRaisesRegex(ValueError,'free-space'):
                RUN.capture(BINARY,self.root/'capture',self.template,THEME,IMAGE,'synthetic_fixture')
        run.assert_not_called();self.assertFalse((self.root/'capture').exists())

    def test_original_output_paths_are_never_reused(self):
        self.capture();self.audit()
        with self.assertRaisesRegex(ValueError,'new path'):
            RUN.capture(BINARY,self.root/'capture',self.template,THEME,IMAGE,'synthetic_fixture')
        with self.assertRaisesRegex(ValueError,'new and outside'):self.audit()


class FeedCheckContractTests(unittest.TestCase):
    def test_production_environment_is_direct_and_never_uses_inherited_tls_overrides(self):
        with patch.dict(os.environ,dict(https_proxy='http://synthetic.invalid',SSL_CERT_FILE='synthetic-ca',OPENSSL_CONF='synthetic-conf')):
            env=RUN.child_environment()
        self.assertEqual(env['NO_PROXY'],'*')
        self.assertFalse(any(env.get(k) for k in ('http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','OPENSSL_CONF')))

    def test_request_has_frozen_duration_storage_timing_and_no_fault_injection(self):
        args=RUN.capture_arguments(Path('/new-output'))
        for name,value in (('--duration-secs','120'),('--feed-profile','combined'),('--max-segment-bytes','1048576'),
                           ('--max-session-bytes','16777216'),('--bbo-stale-after-ms','2000'),('--feed-timer-ms','250')):
            self.assertEqual(args[args.index(name)+1],value)
        self.assertFalse(RUN.POLICY['automatic_reruns'] or RUN.POLICY['injected_faults'] or RUN.POLICY['orders_generated'])
