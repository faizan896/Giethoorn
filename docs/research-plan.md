# First offline research study

Status: specification prepared before signal results. The research runner and
dataset-quality report below are not implemented yet. Existing Paper Lab replays
recorded marks or fixed protocol scenarios; neither generates this signal. This
plan does not change an engine, recording or paper schema.

The immediate input is the user's locally audited BTC archive: 133 finalized
children and one recovered prefix, with 334,794 observations across both feeds.
That aggregate is not a count of independent BBO signals or continuous coverage.
The parent day run failed; individual finalized children can still support offline
work. Raw Mac recordings remain local.

## 1. Freeze and qualify the dataset

Recompute the native archive audit and freeze a manifest before reading outcome
statistics. Bind the audit, binary, input files and this protocol by SHA-256.
Declare `captured_public_data` explicitly. Keep each child and connection as a
separate time domain; child monotonic clocks must never be concatenated directly.
Exclude the recovered prefix from this finalized-source study without repairing
it or dropping it from the archive inventory.

For every child, report source identity, finalization/end reason, BBO versus depth
counts, usable BBO counts, within-connection gaps, reconnects, recorded fresh/stale
intervals and wall-clock discontinuities. Preserve negative source-clock deltas;
receive-wall-time minus exchange time is not network latency. Report the watchdog
child's 1,818-second process duration separately from its recorded usable spans.
Do not turn the producer's 11.5-hour elapsed time into continuous usable coverage.

Use only acknowledged, positive-size, two-sided BBO observations accepted by the
existing native normalization/freshness rules. A depth update cannot refresh BBO.
For this short-horizon study, additionally require BBO gaps no larger than 250 ms
throughout a feature/label interval. This is a declared research filter, not a
measured venue execution guarantee. Label excluded observations and intervals by
reason. If usable data is sparse, report insufficient data rather than relaxing
the filter after inspecting returns. Never replace an unknown outcome with zero.

## 2. Specify one signal before evaluating it

Study ID: `btc-bbo-imbalance-001`. Hypothesis: unusually asymmetric displayed
best-bid/best-ask size predicts the direction of the midprice one second later.
This is a falsifiable prediction study, not a market-making or HFT profit claim.

At the first eligible new BBO observation after each five-second sampling boundary
relative to that child's start, emit at most one observation for that bin. A
missing bin stays missing. Use current accepted BBO sizes only: predict up when
bid size is at least three times ask size, down when ask size is at least three
times bid size, and abstain otherwise. Use exact decimal comparisons. Preserve
the feature's original sequence, connection, timestamp, prices and sizes.

Emit the feature using information available up to that source event only. A
quality violation discovered later makes its label unavailable; retain the
original feature and do not retrospectively choose a replacement in that bin.

The outcome uses the first new accepted BBO quote at least 1,000 ms and at most
1,250 ms after the feature, within the same child and connection and subject to
the interval-quality rule above. A disconnect, unusable feed or missing quote
makes the outcome unavailable. Do not interpolate, forward-fill across gaps or
read future prices to construct the signal. Label up, down and unchanged midprice
separately; an unchanged price is not a directional success.

Report signals, abstentions, missing labels, directional hits, ties and exact
signed midprice changes in basis points. Retain zero-signal sessions and show
per-child results. Repeated/equal-time observations are not independent samples;
do not convert the raw event count into statistical confidence or an annualized
return. Validate future-price independence and hand-calculated synthetic cases
before running any captured data.

## 3. Separate development from evaluation

Freeze qualified children in capture/run order. Allocate the first floor(60% of
children) to development, the next floor(20%) to validation and the remainder to
a retrospective test partition. Never shuffle adjacent events or move children
after seeing outcomes. Feature/label intervals cannot cross child, connection
or partition boundaries. Show excluded children and all partition membership.

Run 134 has already been selected for visual inspection; flag that exposure in
the dataset manifest. A retrospective partition in this small existing archive
must not be described as a pristine prospective holdout. Any generalization
claim requires separately frozen later recordings after the signal and cost
assumptions have been locked. No new long collection is required to build and
validate the quality and research tooling.

## 4. Add costs only after the prediction study

A directional signal is not a trade or a fill. Before an economic test, separately
freeze the entry/exit rule, paper quantity/notional limits, working-order cap,
loss halt, handling of missing exits and assumed arrival/expiry parameters.
Reuse the existing causal IOC model and exact independent cost/ledger checks.
Charge entry and exit fees and count the spread and adverse slippage already
embedded in simulated fill prices once. Retain partial fills, rejected orders
and unresolved exposure; do not invent a closing price or drop a failed case.

Test fixed fee, delay, liquidity and slippage assumptions as sensitivity profiles,
not calibrated measurements. No results have been computed for this signal.
The study cannot complete the 24-hour reliability gate or enable live execution.
