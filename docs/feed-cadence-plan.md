# Recorded-feed cadence calibration

Status: specification only; a dedicated cadence exporter is not implemented.
The [first Mac expiry diagnostic](mac-expiry-results.md) explains three shared
request timelines but cannot determine general feed behavior, order-channel
latency, actual executable liquidity or representative fill probabilities.

## Start with the existing recordings

Use the four unique original recording identities behind the admitted cost
snapshot. Bind their existing source/quality/native fingerprints and recheck
preservation. Deduplicate by original recording identity before counting messages;
six profiles must not multiply one source timeline six times. Retain each child
and connection as its own clock domain. Refuse corrupted/unverifiable inputs and
preserve unavailable results rather than repairing them or inventing intervals.

Do not compute new trades, prediction scores or P&L. Keep the completed cost
policy, its ten expired entries, one unresolved short and 13 closed losses
unchanged. This is an exploratory measurement of stored public-data observations,
not a replacement evaluation cohort or an optimization of expiry thresholds.

## Measure two distinct interval series

1. Recorded BBO message intervals: successive source events on the BBO channel
   within a connection, including valid one-sided/empty or subsequently unusable
   observations as explicitly labelled message states.
2. Native selected-BBO opportunity intervals: successive fresh `market_observed`
   events admitted by the unchanged native mark-only replay within a connection.

Report counts, source identity, duration, enabled feeds/freshness policy,
acknowledgements, connection boundaries, repeated exchange times, zero monotonic
intervals, unusable observations and source-clock discontinuities separately.
Do not apply the prediction study's unique-time/250-ms label filter to erase gaps
from either cadence series. Repeated exchange times do not replenish liquidity.

For each series/child/connection retain interval count, exact minimum/maximum,
and nearest-rank p50/p90/p95/p99, using integer nanoseconds. Predeclare bins
`<=50`, `<=100`, `<=250`, `<=350`, `<=500`, `<=1000`, and `>1000` ms, with clear
nonoverlapping edges in output. These bins reflect existing exploratory timing
questions; they are not a newly validated trading rule. With no intervals, values
are unavailable. Initial/tail silence is separately censored, not treated as a
known next message. Never connect clocks across reconnects or child boundaries.

Use original sequence/timestamp references to retain the longest intervals and
the previously reported expiry neighborhoods for inspection. Raw receive versus
exchange timestamp differences are not an order-network latency measurement.
Message-gap histograms are not probabilities that a taker IOC could execute.

## Separate source observations from model assumptions

Compare the observed series with the already declared `[100,350)` and `[250,500)`
ms model windows as context. Do not widen either window after viewing this
measurement and relabel the old result as improved. A quiet public stream does
not demonstrate absent standing liquidity; publishing cadence, market changes,
transport behavior and recording-machine effects remain separate hypotheses.
Venue publishing semantics need their own verified documentation/telemetry before
being used as a calibrated fact.

Reuse exact native source normalization and finite source/event bounds, with a
read-only input, independent output, bounded audit children and before/after
fingerprints. Checks must cover duplicates, one-sided observations, reconnects,
clock jumps, censored ends, empty series, percentile/bin boundaries, preservation
and refusing a changed source. Preserve exact timestamps in report/JSON export.

## A later fresh recording

If a separate check of recording behavior is needed, first lock a short
120-second public BTC/mainnet capture protocol, explicit feed/freshness/timer
configuration, storage limits and output identity. Use the existing Docker image
with no deliberately injected disconnect/crash. Retain completion or failure,
raw source and native audit, with no automatic replacement by a cleaner-looking
sample. This would be a new calibration sample, not a prospective economic test.

No new capture is required to build and check the cadence exporter. Broader
economic work comes after data/model assumptions are understood and its own
signal, entry/exit and cost rules are versioned before results. The original
archive is already explored; later confirmation requires separately frozen data.
The operational day gate and actual execution calibration remain open.
