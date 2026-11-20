"""Native synthetic execution acceptance; never use exchange access or Mac data."""
import copy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from . import cost_local as RUN
except ImportError:
    import cost_local as RUN

PROJECT = Path(__file__).resolve().parent.parent
BINARY = Path(os.environ.get('GIETHOORN_TEST_BINARY', str(PROJECT/'target/debug/giethoorn'))).resolve()


def recording(root, times=None, book=None):
    source = root/'source/run/experiment'
    child = source/'supervision/run-000001'
    session = child/'session'
    session.mkdir(parents=True)
    events = [json.loads(s) for s in (PROJECT/'fixtures/hyperliquid-combined-v2.jsonl').read_text().splitlines()][:7]
    times = list(range(10, 6511, 100)) if times is None else list(times)
    for ms in times:
        bid, ask, bid_size, ask_size = book(ms) if book else ('99.99', '100.01', '0.02', '0.004')
        payload = dict(channel='bbo', data=dict(coin='BTC', time=100000+ms,
            bbo=[None if bid is None else dict(px=bid, sz=bid_size, n=1),
                 None if ask is None else dict(px=ask, sz=ask_size, n=1)]))
        events.append(dict(schema_version=2, sequence=len(events)+1, local_time_ns=1_000_000_000+ms*1_000_000,
            monotonic_ns=ms*1_000_000, connection_id=1, event=dict(type='text_received', text=json.dumps(payload))))
    last = times[-1]+1
    events.append(dict(schema_version=2, sequence=len(events)+1, local_time_ns=1_000_000_000+last*1_000_000,
        monotonic_ns=last*1_000_000, connection_id=1, event=dict(type='connection_closed', reason='synthetic end')))
    events.append(dict(schema_version=2, sequence=len(events)+1, local_time_ns=1_000_000_000+(last+1)*1_000_000,
        monotonic_ns=(last+1)*1_000_000, connection_id=0, event=dict(type='session_ended', reason='duration_elapsed')))
    raw = b''.join(RUN.CORE.encoded(e)+b'\n' for e in events)
    (session/'segment-00000001.jsonl').write_bytes(raw)
    entries = [dict(kind='header', container_version=1, event_schema_version=2,
                    max_segment_bytes=1048576, max_session_bytes=2097152),
        dict(kind='segment', number=1, file='segment-00000001.jsonl', bytes=len(raw), first_sequence=1,
             last_sequence=len(events), sha256=hashlib.sha256(raw).hexdigest()),
        dict(kind='end', segments=1, records=len(events), data_bytes=len(raw))]
    (session/'index.jsonl').write_bytes(b''.join(RUN.CORE.encoded(e)+b'\n' for e in entries))
    with (child/'live-quotes.jsonl').open('wb') as out:
        completed = subprocess.run([str(BINARY), 'replay', '--input', str(session)], stdout=out,
                                   stderr=subprocess.PIPE, timeout=10, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.decode())
    return source, child


@unittest.skipUnless(BINARY.is_file() and os.access(BINARY, os.X_OK), 'native binary required; set GIETHOORN_TEST_BINARY')
class NativeCostTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def case(self, name='case', times=None, book=None, profile=None):
        root = self.base/name
        source, child = recording(root, times, book)
        before = RUN.REVIEW.inventory(source)
        feature = RUN.feature(1, child)
        self.assertIsNotNone(feature)
        result = RUN.run_case(BINARY, child/'session', feature, profile or RUN.CORE.PROFILES[0], root/'result',
            dict(origin='synthetic_fixture', inventory=before, policy_sha256=RUN.CORE.fingerprint(RUN.CORE.POLICY)),
            time.monotonic()+30)
        self.assertEqual(RUN.REVIEW.inventory(source), before)
        self.assertTrue(result['prefix_verified'])
        self.assertEqual(result['cost_audit']['status'], 'verified')
        return result, root/'result'

    def test_full_round_trip_matches_hand_calculated_price_cost_and_ledger(self):
        result, path = self.case()
        m = result['metrics']
        self.assertEqual(m['outcome'], 'closed')
        self.assertEqual(m['entry_quantity'], m['close_quantity'])
        self.assertEqual(Decimal(m['entry_quantity']), Decimal('0.001'))
        self.assertEqual(Decimal(m['realized_pnl']), Decimal('-0.00004'))
        self.assertEqual(Decimal(m['fees']), Decimal('0.000100000001'))
        self.assertEqual(Decimal(m['closed_case_net_pnl']), Decimal('-0.000140000001'))
        self.assertEqual(Decimal(m['spread_cost']), Decimal('0.00002'))
        self.assertEqual(Decimal(m['slippage_cost']), Decimal('0.00002'))
        self.assertFalse(result['control_reused'])
        self.assertTrue((path/'control/replay/paper-input.jsonl').exists())

    def test_partial_entry_cannot_overclose_or_reverse(self):
        result, path = self.case(book=lambda t: ('99.99', '100.01', '0.02', '0.002'))
        m = result['metrics']
        self.assertEqual(m['outcome'], 'closed')
        self.assertEqual(m['entry_quantity'], '0.0005')
        self.assertEqual(m['close_requested_quantity'], '0.0005')
        self.assertEqual(m['position_quantity'], '0')
        self.assertEqual(Decimal(m['closed_case_net_pnl']), Decimal('-0.0000700000005'))
        plan = json.loads((path/'compiled-scenario.json').read_text())
        self.assertEqual(plan['orders'][1]['quantity'], '0.0005')

    def test_partial_close_preserves_open_exposure_and_historical_valuation(self):
        result, _ = self.case(book=lambda t: ('99.99', '100.01', '0.002' if t>=6010 else '0.02', '0.004'))
        m = result['metrics']
        self.assertEqual(m['outcome'], 'unresolved')
        self.assertEqual(m['position_quantity'], '0.0005')
        self.assertIsNone(m['closed_case_net_pnl'])
        self.assertIsNotNone(m['historical_mark_open_pnl'])
        self.assertEqual(m['close_status'], 'cancelled')

    def test_source_end_keeps_filled_entry_without_a_close_decision(self):
        result, path = self.case(times=range(10, 5511, 100))
        m = result['metrics']
        self.assertEqual(m['outcome'], 'unresolved')
        self.assertEqual(m['close_decision_status'], 'missing_decision')
        self.assertEqual(m['position_quantity'], '0.001')
        self.assertIsNone(m['closed_case_net_pnl'])
        self.assertEqual(len(json.loads((path/'compiled-scenario.json').read_text())['orders']), 1)

    def test_source_end_before_arrival_keeps_pending_entry_without_fabricated_expiry(self):
        result, _ = self.case(times=range(10, 5011, 100))
        m = result['metrics']
        self.assertEqual(m['outcome'], 'unresolved')
        self.assertEqual(m['entry_quantity'], '0')
        self.assertEqual(m['pending_order_ids'], ['entry'])
        self.assertIsNone(m['closed_case_net_pnl'])

    def test_pending_close_is_not_flattened_at_source_end(self):
        result, _ = self.case(times=range(10, 6011, 100))
        m = result['metrics']
        self.assertEqual(m['pending_order_ids'], ['close'])
        self.assertEqual(m['position_quantity'], '0.001')
        self.assertEqual(m['outcome'], 'unresolved')

    def test_expired_entry_has_no_phantom_close_or_replacement_attempt(self):
        times = list(range(10, 5011, 100))+list(range(5410, 6511, 100))
        result, path = self.case(times=times)
        self.assertEqual(result['metrics']['outcome'], 'entry_rejected')
        self.assertEqual(result['metrics']['entry_quantity'], '0')
        self.assertIsNone(result['metrics']['close_requested_quantity'])
        self.assertEqual(len(json.loads((path/'compiled-scenario.json').read_text())['orders']), 1)

    def test_nonmarketable_entry_cancels_without_exit(self):
        result, _ = self.case(book=lambda t: ('100.99', '101.01', '0.02', '0.004') if t>5010 else ('99.99','100.01','0.02','0.004'))
        self.assertEqual(result['metrics']['outcome'], 'no_entry_fill')
        self.assertIsNone(result['metrics']['close_requested_quantity'])
        self.assertIsNone(result['metrics']['closed_case_net_pnl'])

    def test_risk_rejection_is_retained_without_resizing_the_fixed_entry(self):
        result, _ = self.case(book=lambda t: ('100009.99', '100010.01', '0.02', '0.004'))
        self.assertEqual(result['metrics']['outcome'], 'entry_rejected')
        self.assertEqual(result['metrics']['entry_quantity'], '0')
        self.assertIsNotNone(result['metrics']['entry_rejection'])

    def test_loss_halt_can_reject_close_and_exposure_stays_open(self):
        original = RUN.CORE.entry_scenario
        def plan(*args):
            value = original(*args)
            value['max_loss'] = '0.000001'
            return value
        with patch.object(RUN.CORE, 'entry_scenario', side_effect=plan):
            result, _ = self.case()
        self.assertEqual(result['metrics']['outcome'], 'unresolved')
        self.assertTrue(result['metrics']['risk']['halted'])
        self.assertEqual(result['metrics']['close_status'], 'rejected')

    def test_late_close_reports_delay_without_inventing_events_in_gap(self):
        times = list(range(10, 5211, 100))+list(range(8010, 8411, 100))
        result, _ = self.case(times=times)
        self.assertEqual(result['metrics']['close_late_by_ns'], 2_000_000_000)
        self.assertEqual(result['metrics']['outcome'], 'closed')

    def test_future_prices_after_close_decision_do_not_change_compiled_requests(self):
        _, a = self.case('first')
        _, b = self.case('changed', book=lambda t: ('89.99','90.01','0.02','0.004') if t>6010 else ('99.99','100.01','0.02','0.004'))
        self.assertEqual((a/'compiled-scenario.json').read_bytes(), (b/'compiled-scenario.json').read_bytes())
        self.assertEqual(json.loads((a/'causal-prefix.json').read_text())['known_position'],
                         json.loads((b/'causal-prefix.json').read_text())['known_position'])
        self.assertEqual(json.loads((b/'case-result.json').read_text())['metrics']['outcome'], 'unresolved')

    def test_liquidity_profiles_change_close_size_under_the_same_policy(self):
        a, _ = self.case('baseline')
        b, _ = self.case('stress', profile=RUN.CORE.PROFILES[4])
        self.assertEqual(a['policy_sha256'], b['policy_sha256'])
        self.assertNotEqual(a['metrics']['close_requested_quantity'], b['metrics']['close_requested_quantity'])

    def test_partial_short_entry_closes_only_known_short_inventory(self):
        result, path = self.case(book=lambda t: ('99.99','100.01','0.002','0.02'))
        plan = json.loads((path/'compiled-scenario.json').read_text())
        self.assertEqual(plan['orders'][0]['side'], 'sell')
        self.assertEqual(plan['orders'][1]['side'], 'buy')
        self.assertEqual(plan['orders'][1]['quantity'], '0.0005')
        self.assertEqual(result['metrics']['position_quantity'], '0')
        self.assertEqual(Decimal(result['metrics']['closed_case_net_pnl']), Decimal('-0.0000700000005'))

    def test_zero_fee_control_keeps_spread_and_slippage_in_prices(self):
        baseline, _ = self.case('baseline')
        result, _ = self.case('zero', profile=RUN.CORE.PROFILES[2])
        self.assertEqual(result['metrics']['fees'], '0')
        self.assertEqual(Decimal(result['metrics']['closed_case_net_pnl']), Decimal('-0.00004'))
        self.assertEqual(baseline['metrics']['execution_path_sha256'], result['metrics']['execution_path_sha256'])

    def test_unusable_later_quote_does_not_replace_the_historical_mark_reference(self):
        result, _ = self.case(times=range(10, 5511, 100),
            book=lambda t: (None,'100.01','0.02','0.004') if t>=5410 else ('99.99','100.01','0.02','0.004'))
        metrics = result['metrics']
        self.assertEqual(metrics['outcome'], 'unresolved')
        self.assertEqual(metrics['historical_mark_price'], metrics['historical_mark_source']['mid'])
        self.assertEqual(metrics['historical_mark_source']['monotonic_ns'], 5310*1_000_000)

    def test_repeat_preserves_exact_requests_costs_and_metrics(self):
        a, first = self.case('first')
        b, second = self.case('second')
        self.assertEqual(a['metrics'], b['metrics'])
        self.assertEqual((first/'entry-scenario.json').read_bytes(), (second/'entry-scenario.json').read_bytes())
        self.assertEqual((first/'compiled-scenario.json').read_bytes(), (second/'compiled-scenario.json').read_bytes())

    def test_tampered_compiled_prefix_is_rejected(self):
        result, path = self.case()
        _, a = RUN.read_execution(path/'control')
        _, b = RUN.read_execution(path/'compiled')
        broken = copy.deepcopy(b)
        broken[0][0]['account']['collateral_balance'] = '9999'
        with self.assertRaisesRegex(ValueError, 'entry prefix'):
            RUN.CORE.verify_prefix(a, broken, result['causal_prefix']['decision'])
