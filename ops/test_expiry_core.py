import copy
import json
from pathlib import Path
import unittest

try:
    from . import expiry_core as CORE
except ImportError:
    import expiry_core as CORE

PROJECT = Path(__file__).resolve().parent.parent


def fixture():
    def rows(name):
        return [json.loads(s) for s in (PROJECT/'fixtures'/name).read_text().splitlines()]
    original = rows('hyperliquid-combined-v2.jsonl')
    frames,links = rows('paper-recorded-v2.updates.jsonl'),rows('paper-recorded-v2.links.jsonl')
    execution = json.loads((PROJECT/'fixtures/paper-execution-v3.execution.json').read_text())
    timeline = list(zip(rows('paper-execution-v3.updates.jsonl'),rows('paper-execution-v3.links.jsonl'),rows('paper-execution-v3.trace.jsonl')))
    return original,frames,links,execution,timeline


class ExpiryCoreTests(unittest.TestCase):
    def setUp(self):
        self.original,self.frames,self.links,self.execution,self.rows = fixture()
        self.events = CORE.market_events(self.original,self.frames,self.links)

    def diagnose(self):
        return {row['order_id']:row for row in CORE.diagnose(self.execution,self.rows,self.events)}

    def test_golden_synthetic_lifecycles_keep_every_order(self):
        result = self.diagnose()
        self.assertEqual(len(result),9)
        self.assertEqual(result['missing-market']['classification'],'request_rejected')
        self.assertEqual(result['not-marketable']['classification'],'no_fill_cancelled')
        self.assertEqual(result['buy-partial']['classification'],'partial_fill_cancelled')
        self.assertEqual(result['sell-partial']['classification'],'partial_fill_cancelled')
        self.assertEqual(result['late-pending']['classification'],'pending_at_source_end')

    def test_quote_at_exclusive_expiry_is_not_a_fill_opportunity(self):
        row = self.diagnose()['expiry-boundary']
        self.assertEqual(row['classification'],'expired_at_quote_boundary')
        self.assertEqual(row['arrival_ns'],'170000000')
        self.assertEqual(row['expiry_ns'],'270000000')
        self.assertEqual(row['native_opportunities_in_window'],0)
        self.assertEqual(row['first_native_quote_at_or_after_arrival']['monotonic_ns'],row['expiry_ns'])
        self.assertEqual(row['observed_resolution']['monotonic_ns'],row['expiry_ns'])
        self.assertTrue(row['expiry_is_exclusive'])

    def test_pending_source_end_does_not_invent_an_expiry(self):
        row = self.diagnose()['late-pending']
        self.assertIsNone(row['observed_resolution'])
        self.assertIsNone(row['first_native_quote_at_or_after_arrival'])
        self.assertEqual(row['ending_pending_order_ids'],['late-pending'])
        self.assertEqual(row['expiry_ns'],'370000000')

    def test_equal_exchange_times_remain_visible_without_guaranteeing_liquidity(self):
        row = self.diagnose()['ambiguous-time']
        opportunity = row['first_native_quote_at_or_after_arrival']
        self.assertTrue(opportunity['repeated_exchange_time'])
        self.assertTrue(opportunity['usable_opportunity'])
        self.assertEqual(row['filled_quantity'],'0')
        self.assertEqual(row['classification'],'no_fill_cancelled')

    def test_stale_request_is_not_explained_as_expiry(self):
        row = self.diagnose()['stale-send']
        self.assertEqual(row['classification'],'request_rejected')
        self.assertEqual(row['observed_resolution']['sequence'],12)
        self.assertEqual(row['request_risk']['market_status'],'stale')

    def test_source_gaps_are_measured_without_interpolation(self):
        row = self.diagnose()['buy-partial']
        gap = row['source_gaps']['expiry']
        self.assertEqual(gap['recorded_gap_ns'],'70000000')
        self.assertEqual(gap['before']['sequence'],13)
        self.assertEqual(gap['at_or_after']['sequence'],14)
        self.assertEqual(row['component_cause'],'unknown')

    def test_timestamp_receipts_use_exact_strings_and_inputs_are_unchanged(self):
        before = copy.deepcopy((self.execution,self.rows,self.events))
        result = self.diagnose()
        row = result['buy-partial']
        self.assertIsInstance(row['request_ns'],str)
        self.assertIsInstance(row['timeline'][0]['local_time_ns'],str)
        self.assertEqual(before,(self.execution,self.rows,self.events))
        self.assertEqual(CORE.stamps(dict(monotonic_ns=2**63+123))['monotonic_ns'],str(2**63+123))

    def test_request_window_tamper_is_refused(self):
        next(step for _,_,step in self.rows if step['phase']=='scenario_request')['expiry_ns'] += 1
        with self.assertRaisesRegex(ValueError,'window differs'):
            self.diagnose()

    def test_earlier_opportunity_cannot_be_ignored_to_explain_an_expiry(self):
        # Move the existing boundary quote one nanosecond inside the window.
        self.events[24]['time'] -= 1
        with self.assertRaisesRegex(ValueError,'first native opportunity'):
            self.diagnose()

    def test_missing_or_duplicate_request_is_refused(self):
        self.rows.append(next(row for row in self.rows if row[2]['phase']=='scenario_request'))
        with self.assertRaisesRegex(ValueError,'duplicated'):
            self.diagnose()

    def test_source_sequence_or_clock_corruption_is_refused(self):
        self.original[2]['sequence']=200
        with self.assertRaisesRegex(ValueError,'source reference'):
            CORE.market_events(self.original,self.frames,self.links)

    def test_generated_end_is_not_a_native_opportunity(self):
        self.assertEqual(len(self.events),len(self.original))
        self.assertTrue(self.links[-1]['generated_end'])
        self.assertFalse(any(event['sequence']>len(self.original) for event in self.events))

    def test_source_connection_cannot_be_relabelled(self):
        self.links[8]['connection_id']=999
        with self.assertRaisesRegex(ValueError,'source reference'):
            CORE.market_events(self.original,self.frames,self.links)
