# Decision: recorded-feed cadence version 1

Status: implemented as a source-observation audit of preserved quote-window
artifacts. New output namespaces are `cadence_report_version: 1`,
`cadence_policy_version: 1`, `cadence_recording_version: 1` and
`cadence_interval_version: 1`. Existing recording, normalization, paper, signal,
cost and expiry versions remain unchanged, as do their producer source/assets.

The first Mac diagnostic supplies three shared request timelines, not enough to
establish general feed behavior. Cadence therefore measures all observations in
the already selected unique recordings, independently of trade success. The input
is a preserved explain snapshot; it already contains native source copies and
the original cost/source receipts. No new capture or trading policy is required.

## Unique sources and connection domains

Bind the input inventory, producer code/assets and installed binary. Validate
original source manifest members and recompute native recording identities.
Deduplicate identical source identities, retaining child aliases. Six profiles
never multiply a market timeline. Missing/bad sources remain visible without a
replacement recording. A fresh native mark-only replay must reproduce each
unique source's saved source/report/market streams before metrics are admitted.

Raw BBO arrivals include valid empty/unusable, repeated and older exchange-time
messages, with explicit state/acknowledgement context. Native opportunities use
the unchanged fresh selected-BBO replay definition. The prediction study's
unique-exchange-time and continuous-label filters are not cadence filters.

Create intervals only between consecutive observations of the same series in
one child/connection. Recording-level distributions combine those interval
samples, with per-connection distributions retained, rather than joining clocks.
Source zero-time intervals are real data. A monotonic regression or corrupt source
is refused. Leading/trailing silence uses the observed connection's first/last
events and is explicitly censored; no hypothetical next observation is added.
Connection open/acknowledgement/error/close and empty windows remain context.

Clock-step flags use the previously declared 1-second wall-minus-monotonic
discontinuity threshold or a backward wall clock. Keep affected monotonic intervals
and their crossed-step counts. Such flags are not an identified physical cause.

## Exact descriptive statistics

Use integer nanoseconds and nearest-rank p50/p90/p95/p99, with rank
`ceil(p*n/100)` for nonempty sorted samples. Empty samples have unavailable
quantiles/minimum/maximum. Nonoverlapping bins are `[0,50]`, `(50,100]`,
`(100,250]`, `(250,350]`, `(350,500]`, `(500,1000]`, `(1000,+infinity)` ms.
Retain exact interval receipts and stable longest-five source references.
Time values serialize as decimal strings; browser formatting uses integer
arithmetic and raw JSON downloads preserve exact values.

The portable report selects recording/connection/series and compares stored
statistics/histograms. It does not re-evaluate a signal, order or profit. Original
order neighborhoods are retained solely as existing context. Interarrival
histograms are not request-conditioned fill probabilities or network latency.
Quiet public messages do not prove that standing venue liquidity was unavailable.

## Refusals, budgets and acceptance

Input, code/assets and installed binary are fingerprinted before/after. A change
invalidates admitted metrics while preserving audit files. Use read-only input,
create-new output, no network, 1-GiB output cap, 1-GiB free-space reserve,
300-second admission deadline, 128-MiB source reservation and existing native
source/event limits. The Mac wrapper adds a 360-second outer timeout.

Acceptance covers hand-calculated quantiles/bins, reconnects, empty/single/zero
intervals, repeated/older/one-sided messages, censored ends, clock steps, exact
timestamps, identity deduplication, corruption, budget refusal, preservation and
native replay reproducibility. Offline browser checks cover distinct/sparse
series and unavailable data as well as ordinary native source artifacts. Separate
cloud software evidence must not be labelled as the actual Mac cadence result.
