"""Golden coverage and exact arithmetic checks for the broader evaluation."""
import copy
import unittest

try:
    from . import evaluation_core as CORE
except ImportError:
    import evaluation_core as CORE


def policy(net='-0.1', position='0', pending=None, fills=2):
    return dict(policy_id=CORE.CYCLE.POLICY['policy_id'], causal_prefix_verified=True,
        causal_prefix_audit=dict(status='verified', decision_available=True, prefix_records=12, prefix_sha256='synthetic'),
        close_compilation=dict(status='close_compiled', known_position='0.001', working_orders=0,
            prefix_records=12, prefix_sha256='synthetic'), control_reused=False, orders=[],
        metrics=dict(actual_execution='unknown', conditional_closed_pnl=net, ending_position_quantity=position,
            pending_order_ids=pending or [], assumed_fills=fills, entry_quantity='0.001' if fills else '0',
            close_requested_quantity='0.001' if fills else None, close_quantity='0.001' if net is not None else None,
            fees='0.01' if fills else '0', outcome='closed_under_assumptions' if net is not None else
                'pending_at_source_end' if pending else 'open_exposure' if position != '0' else 'no_fills'))


def row(child=1, profile='baseline', status='verified', **kwargs):
    return dict(child=child, profile=profile, status=status, policy=policy(**kwargs) if status == 'verified' else None)


class DevelopmentEvaluationCoreTests(unittest.TestCase):
    def baseline(self, rows):
        return CORE.summarize(rows)['profiles'][0]

    def test_entire_development_cohort_is_selected_without_old_four_child_cap(self):
        selected=list(range(2,81))
        self.assertEqual(CORE.cohort(dict(candidate_partitions=dict(status='frozen_retrospective',
            development=selected, validation=[81], retrospective_test=[82]))), selected)

    def test_oversized_cohort_is_refused_rather_than_truncated(self):
        with self.assertRaisesRegex(ValueError, 'no truncation'):
            CORE.cohort(dict(candidate_partitions=dict(status='frozen_retrospective',
                development=list(range(1,130)), validation=[], retrospective_test=[])))

    def test_duplicate_unordered_boolean_or_empty_membership_is_refused(self):
        for selected in ([2,2], [2,1], [True], []):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                CORE.cohort(dict(candidate_partitions=dict(status='frozen_retrospective',
                    development=selected, validation=[], retrospective_test=[])))

    def test_overlapping_partitions_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            CORE.cohort(dict(candidate_partitions=dict(status='frozen_retrospective',
                development=[1], validation=[1], retrospective_test=[])))

    def test_closed_cycle_sum_retains_exact_decimal_precision_and_sign_counts(self):
        p=self.baseline([row(net='1.000000000000000001'),row(2,net='-0.000000000000000001'),row(3,net='0E-7')])
        self.assertEqual(p['closed_cycle_net'],'1.000000000000000000')
        self.assertTrue(p['coverage_complete'])
        self.assertEqual((p['positive_closed'],p['negative_closed'],p['zero_closed']),(1,1,1))

    def test_missing_or_not_run_cases_hide_an_otherwise_known_closed_sum(self):
        for status in ('unavailable','not_run'):
            with self.subTest(status=status):
                p=self.baseline([row(),row(2,status=status)])
                self.assertEqual(p['closed'],1);self.assertIsNone(p['closed_cycle_net']);self.assertFalse(p['coverage_complete'])

    def test_open_position_keeps_profile_total_unavailable(self):
        p=self.baseline([row(),row(2,net=None,position='0.0005',fills=1)])
        self.assertEqual(p['unresolved'],1);self.assertIsNone(p['closed_cycle_net'])

    def test_pending_order_while_flat_keeps_total_unavailable(self):
        p=self.baseline([row(),row(2,net=None,pending=['entry'],fills=0)])
        self.assertEqual(p['unresolved'],1);self.assertFalse(p['coverage_complete'])

    def test_no_signal_and_no_fill_are_accounted_for_without_becoming_zero_profit_trades(self):
        p=self.baseline([row(),row(2,status='no_signal'),row(3,net=None,fills=0)])
        self.assertEqual(p['closed_cycle_net'],'-0.1')
        self.assertEqual((p['closed'],p['no_signal'],p['no_fills'],p['zero_closed']),(1,1,1,0))

    def test_all_no_signal_or_no_fill_has_no_fabricated_financial_total(self):
        for cases in ([row(status='no_signal')],[row(net=None,fills=0)]):
            p=self.baseline(cases);self.assertTrue(p['coverage_complete']);self.assertIsNone(p['closed_cycle_net'])

    def test_profiles_stay_separate_without_a_pooled_financial_total(self):
        r=CORE.summarize([row(net='-2'),row(profile='zero-fee',net='1')])
        self.assertNotIn('closed_cycle_net',r)
        self.assertEqual(r['profiles'][0]['closed_cycle_net'],'-2')
        self.assertEqual(next(p for p in r['profiles'] if p['profile']=='zero-fee')['closed_cycle_net'],'1')

    def test_missing_child_in_a_profile_cannot_make_its_total_complete(self):
        r=CORE.summarize([row(),row(2),row(profile='zero-fee',net='1')])
        p=next(p for p in r['profiles'] if p['profile']=='zero-fee')
        self.assertFalse(p['coverage_complete']);self.assertIsNone(p['closed_cycle_net'])

    def test_duplicate_cases_and_unknown_profiles_are_refused(self):
        for cases in ([row(),row()],[row(profile='tuned-fee')]):
            with self.assertRaises(ValueError):CORE.summarize(cases)

    def test_unverified_case_cannot_keep_metrics(self):
        c=row();c['status']='unavailable'
        with self.assertRaisesRegex(ValueError,'unverified case'):CORE.summarize([c])

    def test_open_or_unfilled_case_cannot_claim_closed_pnl(self):
        for c in (row(position='0.001'),row(pending=['close']),row(fills=0)):
            with self.assertRaisesRegex(ValueError,'closed P&L'):CORE.summarize([c])

    def test_nonfinite_economics_and_unknown_actual_execution_are_refused(self):
        for c in (row(net='NaN'),row(position='Infinity')):
            with self.assertRaises(ValueError):CORE.summarize([c])
        c=row();c['policy']['metrics']['actual_execution']='known'
        with self.assertRaises(ValueError):CORE.summarize([c])

    def test_closed_filled_cycle_cannot_silently_lose_its_pnl(self):
        c=row(net=None)
        with self.assertRaisesRegex(ValueError,'lacks closed P&L'):CORE.summarize([c])
