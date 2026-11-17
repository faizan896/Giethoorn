"""Deterministic prediction study; no clocks, networking, orders or fills."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json

POLICY = dict(study_policy_version=1, study_id='btc-bbo-imbalance-001', coin='BTC', network='mainnet',
              sampling_bin_ns=5_000_000_000, size_multiple='3',
              min_label_ns=1_000_000_000, max_label_ns=1_250_000_000,
              max_bbo_gap_ns=250_000_000, clock_discontinuity_ns=1_000_000_000,
              unique_exchange_times_only=True, aggregate_bps_decimal_places=12,
              display_bps_decimal_places=6, rounding='half_even', orders_enabled=False)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def positive(text):
    require(type(text) is str and len(text) <= 128, 'bounded decimal string required')
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError('invalid decimal') from None
    require(value.is_finite() and value > 0 and abs(value.adjusted()) <= 128, 'positive bounded decimal required')
    return Fraction(value)


def exact(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def rounded_ticks(value, places=12):
    scaled = value * 10**places
    q, remainder = divmod(abs(scaled.numerator), scaled.denominator)
    q += 2*remainder > scaled.denominator or (2*remainder == scaled.denominator and q % 2 == 1)
    return -q if scaled < 0 else q


def fixed(ticks, places):
    whole, remainder = divmod(abs(ticks), 10**places)
    return ('-' if ticks < 0 else '')+str(whole)+(('.'+str(remainder).zfill(places)) if places else '')


class Stats:
    def __init__(self):
        self.counts = Counter()
        self.missing = Counter()
        self.signed_ticks = 0

    def feature(self, feature):
        self.counts['samples'] += 1
        self.counts['abstentions' if feature['prediction'] == 'abstain' else 'signals'] += 1

    def sample(self, feature, outcome):
        signal = feature['prediction'] != 'abstain'
        if outcome['status'] != 'labelled':
            self.counts['missing_labels'] += 1
            self.counts['missing_signal_labels'] += signal
            self.missing[outcome['reason']] += 1
            return
        self.counts['labelled_samples'] += 1
        if signal:
            self.counts['labelled_signals'] += 1
            self.counts['signal_hits'] += outcome['direction'] == feature['prediction']
            self.counts['unchanged_signal_labels'] += outcome['direction'] == 'unchanged'
            self.counts['always_up_hits'] += outcome['direction'] == 'up'
            self.counts['always_down_hits'] += outcome['direction'] == 'down'
            ratio = outcome['signed_mid_change_bps']
            self.signed_ticks += rounded_ticks(Fraction(int(ratio['numerator']), int(ratio['denominator'])))

    def merge(self, other):
        self.counts.update(other.counts)
        self.missing.update(other.missing)
        self.signed_ticks += other.signed_ticks

    def report(self):
        keys = ('source_records', 'accepted_bbo_observations', 'eligible_bbo_observations',
                'duplicate_bbo_observations', 'sampling_bins_without_eligible_bbo',
                'samples', 'signals', 'abstentions', 'labelled_samples', 'missing_labels',
                'labelled_signals', 'missing_signal_labels', 'signal_hits', 'unchanged_signal_labels',
                'always_up_hits', 'always_down_hits')
        result = {key: self.counts[key] for key in keys}
        n = result['labelled_signals']
        for label, numerator in [('hit_rate_percent', result['signal_hits']),
                                 ('always_up_percent', result['always_up_hits']),
                                 ('always_down_percent', result['always_down_hits'])]:
            result[label] = None if not n else fixed(rounded_ticks(Fraction(numerator*100, n), 4), 4)
        result['mean_signed_mid_change_bps_12dp'] = None if not n else fixed(rounded_ticks(Fraction(self.signed_ticks, n), 0), 12)
        places = POLICY['display_bps_decimal_places']
        result['mean_signed_mid_change_bps_display'] = None if not n else fixed(rounded_ticks(Fraction(self.signed_ticks, n*10**12), places), places)
        result['missing_label_reasons'] = dict(sorted(self.missing.items()))
        return result


def book(record, observation):
    require(record['event']['type'] == 'text_received', 'BBO observation lacks original message')
    value = json.loads(record['event']['text'])
    require(value['channel'] == 'bbo', 'original message is not BBO')
    data, quote = value['data'], observation['quote']
    require(data['coin'] == observation['coin'] and data['time'] == quote['exchange_time_ms'],
            'original BBO identity differs from native quote')
    require(len(data['bbo']) == 2 and all(data['bbo']), 'two-sided original BBO required')
    bid, ask = data['bbo']
    bid_px, ask_px, bid_size, ask_size = [positive(text) for text in (bid['px'], ask['px'], bid['sz'], ask['sz'])]
    mid = positive(quote['mid'])
    require(bid_px < ask_px and bid_px == positive(quote['bid']) and ask_px == positive(quote['ask'])
            and bid_px <= mid <= ask_px, 'original prices differ from native normalization')
    return mid, bid_size, ask_size, bid['sz'], ask['sz']


class Analyzer:
    """One child/connection timeline; each step returns immutable event receipts."""
    def __init__(self, child):
        self.child, self.stats = child, Stats()
        self.first = self.previous = None
        self.last_bbo_ns = None
        self.exchange_times = {}
        self.last_bin = None
        self.pending = None
        self.finished = False

    def resolve(self, reason=None, observation=None):
        if self.pending is None:
            return []
        feature = self.pending
        self.pending = None
        outcome = dict(status='unavailable', reason=reason, direction=None,
                       future=None, mid_change_bps=None, signed_mid_change_bps=None)
        if observation is not None:
            future_mid = positive(observation['quote']['mid'])
            initial_mid = positive(feature['mid'])
            change = (future_mid-initial_mid)/initial_mid*10_000
            direction = 'up' if change > 0 else 'down' if change < 0 else 'unchanged'
            signed = change if feature['prediction'] == 'up' else -change
            outcome.update(status='labelled', reason=None, direction=direction,
                future=dict(sequence=observation['sequence'], connection_id=observation['connection_id'],
                            monotonic_ns=observation['monotonic_ns'], local_time_ns=str(observation['local_time_ns']),
                            exchange_time_ms=observation['quote']['exchange_time_ms'], mid=observation['quote']['mid']),
                mid_change_bps=exact(change),
                signed_mid_change_bps=None if feature['prediction'] == 'abstain' else exact(signed))
        self.stats.sample(feature, outcome)
        return [('sample', dict(sample_version=1, feature=feature, outcome=outcome))]

    def step(self, record, observation):
        require(not self.finished, 'study child already ended')
        now = record['monotonic_ns']
        events = []
        self.stats.counts['source_records'] += 1
        if self.first is None:
            self.first = now
        if self.previous is not None:
            delta = now-self.previous['monotonic_ns']
            require(delta >= 0, 'study source monotonic clock regressed')
            clock_step = record['local_time_ns']-self.previous['local_time_ns']-delta
            if abs(clock_step) >= POLICY['clock_discontinuity_ns'] or record['local_time_ns'] < self.previous['local_time_ns']:
                events += self.resolve('clock_discontinuity')
                self.last_bbo_ns = None
        if self.pending is not None and record['connection_id'] != self.pending['connection_id']:
            events += self.resolve('connection_changed')
            self.last_bbo_ns = None
        if self.last_bbo_ns is not None and now-self.last_bbo_ns > POLICY['max_bbo_gap_ns']:
            events += self.resolve('bbo_gap_over_250ms')
            self.last_bbo_ns = None
        if self.pending is not None and now > self.pending['monotonic_ns']+POLICY['max_label_ns']:
            events += self.resolve('label_window_expired')
        if observation is not None:
            state = observation['feeds']['bbo']
            usable = state is not None and state['status'] == 'fresh' and state['acknowledged'] is True
            if not usable:
                events += self.resolve('feed_unusable')
                self.last_bbo_ns = None
            if observation['kind'] == 'bbo':
                self.stats.counts['accepted_bbo_observations'] += 1
                quote = observation.get('quote') or {}
                if usable and quote.get('mid') is not None:
                    connection, exchange = record['connection_id'], quote['exchange_time_ms']
                    old = self.exchange_times.get(connection)
                    require(old is None or exchange >= old, 'accepted BBO exchange timestamp regressed')
                    self.exchange_times[connection] = exchange
                    if old == exchange:
                        self.stats.counts['duplicate_bbo_observations'] += 1
                        events += self.resolve('repeated_exchange_timestamp')
                        self.last_bbo_ns = None
                    else:
                        _, bid_size, ask_size, bid_text, ask_text = book(record, observation)
                        self.stats.counts['eligible_bbo_observations'] += 1
                        self.last_bbo_ns = now
                        if self.pending is not None and now >= self.pending['monotonic_ns']+POLICY['min_label_ns']:
                            events += self.resolve(observation=observation)
                        bin_id = (now-self.first)//POLICY['sampling_bin_ns']
                        if bin_id != self.last_bin:
                            prediction = 'up' if bid_size >= 3*ask_size else 'down' if ask_size >= 3*bid_size else 'abstain'
                            feature = dict(feature_version=1, study_id=POLICY['study_id'], child=self.child, bin=bin_id, sequence=record['sequence'],
                                connection_id=connection, monotonic_ns=now, local_time_ns=str(record['local_time_ns']),
                                exchange_time_ms=exchange, coin=observation['coin'],
                                bid=quote['bid'], ask=quote['ask'], mid=quote['mid'],
                                bid_size=bid_text, ask_size=ask_text, prediction=prediction)
                            require(self.pending is None, 'sampling windows unexpectedly overlap')
                            self.pending, self.last_bin = feature, bin_id
                            self.stats.feature(feature)
                            events.append(('feature', feature))
                elif self.pending is not None:
                    events += self.resolve('feed_unusable')
                    self.last_bbo_ns = None
        self.previous = record
        return events

    def finish(self):
        require(not self.finished, 'study child already ended')
        self.finished = True
        if self.previous is not None:
            bins = (self.previous['monotonic_ns']-self.first)//POLICY['sampling_bin_ns']+1
            self.stats.counts['sampling_bins_without_eligible_bbo'] = bins-self.stats.counts['samples']
        return self.resolve('source_ended')
