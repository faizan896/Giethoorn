# Recorded BBO cadence audit

This offline tool measures observation intervals in the unique recorded sources
behind an existing quote-window diagnostic. It compares all recorded BBO messages
with native selected-BBO quote opportunities, without new trades, prediction
scores, P&L or a claim about order latency or real fill probabilities.

## Run the saved snapshot

After installing the cadence update, open Docker Desktop and run:

```sh
bash scripts/mac cadence explain-20261120T131432Z-o7WCIL
```

Use the **explain snapshot ID**, rather than a cost/quality/collection ID. The
command reads its private native source copies and existing original receipts.
It reuses the current image with read-only input/helpers and network disabled.
It does not require another collection, host Python/Rust or an image rebuild.

A new `~/GiethoornData/cadence-TIMESTAMP-SUFFIX/report/cadence.html` opens in the
browser. Terminal output includes per-recording raw/native counts, exact
millisecond p50/p95/p99/maximum and the seven nonoverlapping histogram bins.
Paste that output for review; no additional extraction command is needed. The
portable HTML works without a server and exports the original JSON exactly.

Keep the producer snapshot and its original helper/template versions unchanged.
Checksums, producer code/assets, copied cost policy and installed executable must
match. Unexpected files or changed evidence cause refusal or unavailable metrics.
A budget refusal remains not-run; a missing/bad selected source is not replaced
with a later recording. A process timeout/shutdown can retain partial audits
without a final report. The internal deadline is 300 seconds, outer Mac timeout
360 seconds, output cap 1 GiB and free-space reserve 1 GiB.

## What the counts mean

Sources are grouped by the native original recording SHA-256. Six execution
profiles do not multiply one feed six times. If selected child IDs themselves
refer to identical original bytes, they are labelled shared aliases and measured
once. Every selected child remains accounted for, including an unavailable source.

The two series are:

- **Recorded BBO messages:** original BBO-channel arrivals, including valid
  one-sided, unusable, repeated and older exchange-time messages. Source labels
  retain acknowledgement/state and older/repeated timestamp counts.
- **Native opportunities:** fresh selected-BBO `market_observed` events from the
  unchanged native mark-only replay. Repeated exchange times may be opportunities
  without replenishing available simulated liquidity.

Each connection has its own interval series. A disconnect/reconnect is never an
interval between the two connections' messages. Recording-level percentiles pool
only already formed within-connection intervals; they do not concatenate clocks.
Other-channel messages and timers remain source context rather than BBO samples.
The prediction study's unique-time/250-ms label filter does not remove gaps here.

The median is nearest-rank p50, and p90/p95/p99 use the same integer rule:
sort `n` intervals, take one-based rank `ceil(p*n/100)`. No average/interpolation
is used. With zero intervals all percentiles/minimum/maximum are unavailable.
A genuine zero-nanosecond interval is retained as a measured zero.

Bins are `[0,50]`, `(50,100]`, `(100,250]`, `(250,350]`, `(350,500]`, `(500,1000]`
and `(1000,+infinity)` ms. They are descriptive predeclared exploratory bins,
not newly validated expiry choices. Histogram counts sum to measured intervals.
The view changes recording, connection and series without recalculating outcomes.

Connection windows run from the first to last original event carrying that
connection ID. Opening, acknowledgement and terminal markers remain visible as
context. Leading/trailing observed silence is censored and can include startup/
shutdown; it is not a complete interval to an invented next message. A connection
with no message has an observed empty span and unavailable interval statistics.
Source clock discontinuities are flagged without dropping the crossed intervals.

## Integrity and retained evidence

Admission binds the preserved version-1 quote-window report, every indexed audit
artifact, original producer hashes/assets, copied cost policy and native binary.
For each unique source, a fresh native mark-only replay must reproduce the saved
report and source-derived streams. Source identities must agree with original
cost/diagnostic case receipts. No saved trading scenario is rerun by this tool.
This is a fresh observation audit; it does not re-attest actual venue execution.

Each `recordings/run-N/` folder retains the fresh native export,
`cadence-recording.json` and `intervals.jsonl`. Every interval has original start/
end sequence, connection, exact source timestamps and crossed-clock-step count.
The report includes the five longest intervals per series/connection and the
already diagnosed original order neighborhoods, without creating new requests.
All nanosecond values remain decimal strings; the browser formats them using
integer arithmetic. Financial values are not recomputed.

The full input and helper/binary fingerprints are checked before/after. Changes
invalidate all admitted measurements. Input follows the existing regular-file
2-GiB/8,192-file bounds; native sources retain 16-MiB/10,000-event limits. Each
source needs a conservative 128-MiB output reservation, interval exports are
capped at 64 MiB and individual native calls at 30 seconds. The report/HTML retain
finite size bounds. The installed binary is used, not an executable in the input.

See [decision 0013](decisions/0013-recorded-cadence.md) and
[the original calibration protocol](feed-cadence-plan.md). Publishing behavior,
market activity, transport and machine effects cannot be identified from cadence
alone. Quiet public data does not establish absent standing liquidity. These
intervals are not an order-latency SLA or a fill probability; original cost results,
the operational day gate and fresh-data economic confirmation remain unchanged.
