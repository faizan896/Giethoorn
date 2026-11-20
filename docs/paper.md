# Offline paper foundation and Paper Lab

The first paper slice implements deterministic order lifecycle, assumed fills,
FIFO linear-contract positions, exact fees/P&L and basic risk guards. It runs
offline alongside the public collector. It is not connected to a live strategy,
exchange order API, wallet or calibrated fill model.

A separate version-2 adapter now replays finalized schema-2 market recordings
through the paper mark ledger. It uses actual recorded prices and feed health;
orders and fills are disabled. The synthetic scenario and its v1 outputs remain
unchanged. See [the recorded-market decision](decisions/0004-recorded-paper.md).

Version 3 adds fixed, controlled IOC scenarios with explicitly assumed execution
costs. It keeps live strategy/order capabilities disabled. See
[the execution decision](decisions/0005-controlled-execution.md) for timing,
liquidity, cancellation, cost and unresolved-exposure semantics.

The [R001 costed policy probe](cost-study.md) now uses that unchanged native model
to compile causal entry/close requests on a small frozen development suite. Close
size depends on actual known entry fills, so its invariant is a fixed policy,
distinct from the fixed order lists in the batch runner below. It retains every
unresolved, rejected and unrun case and evaluates no combined portfolio return.

## Batch sensitivity testing

Use `python3 ops/paper_batch.py --binary target/debug/giethoorn --manifest
path/to/batch.json --output-dir data/batch-001` with a new output directory.
Each recording's order plan stays fixed; only the five execution assumptions
change between profiles. Paths below resolve relative to the manifest file:

```json
{
  "batch_version": 1,
  "label": "Fixed IOC sensitivity",
  "baseline_profile": "baseline",
  "datasets": [{
    "id": "btc-session",
    "label": "Saved BTC session",
    "recording": "../data/supervision-001/run-000002/session",
    "scenario": "fixed-scenario.json",
    "origin": "captured_public_data",
    "feed": "bbo"
  }],
  "profiles": [{
    "id": "baseline",
    "label": "Baseline",
    "assumptions": {
      "fee_rate": "0.0005", "slippage_bps": "1",
      "top_size_fraction": "0.25", "latency_ms": 100, "quote_wait_ms": 1000
    }
  }, {
    "id": "fee-stress",
    "label": "Higher fee",
    "assumptions": {
      "fee_rate": "0.001", "slippage_bps": "1",
      "top_size_fraction": "0.25", "latency_ms": 100, "quote_wait_ms": 1000
    }
  }],
  "limits": {
    "max_output_bytes": 1073741824, "min_free_bytes": 1073741824,
    "native_timeout_seconds": 120, "suite_timeout_seconds": 900
  }
}
```

Declare `synthetic_fixture` for generated test recordings. Limits allow at most
8 recordings, 8 profiles and 32 cases. Origin uses snake case in this JSON;
native CLI source declarations use kebab case. Unknown fields and duplicate IDs
are rejected. Every profile declares the full assumption set.

The runner pins its executable and snapshots each finalized recording before
running its cases. It retains original scenarios, fixed-plan/source fingerprints,
all case evidence, independent cost audits and exact ledger replay checks.
`batch-report.json` and `batch-lab.html` summarize the results. Download the HTML
and open it in your own browser; its filters, case details and JSON export work
offline. To attach it to the existing read-only monitor, add
`--batch-view data/batch-001/batch-lab.html`; `/batch` serves that fixed file.

Each row pairs only with the same recording's baseline. Changed fill paths and
ending exposure are explicit, and open positions use historical marks. Failed
and skipped cases have unavailable results rather than zero P&L. There is no
combined return or profit ranking. A fully verified matrix exits zero; failed or
unfinished cases produce a nonzero exit and a reviewable report. Budget checks
occur between bounded native operations; they are not a kernel quota or a hard
Python/filesystem deadline. See [decision 0006](decisions/0006-batch-sensitivity.md).

Sensitivity testing precedes empirical calibration: observed execution outcomes
are still needed to estimate actual latency, liquidity capture and slippage.
Before evaluating a strategy, define a separate trading hypothesis, fixed risk
limits and chronologically held-out recordings. Neither this report nor a passed
simulation completes the pending 24-hour collection gate.

## Test controlled orders on a recording

```sh
./scripts/dev build --locked
python3 ops/paper_execution.py --binary target/debug/giethoorn \
  --input data/supervision-001/run-000002/session \
  --scenario path/to/fixed-scenario.json \
  --output-dir data/execution-lab-001 --origin captured-public-data --feed bbo
```

Use a new output path. Scenario JSON declares version, label, account/risk limits,
fee rate, adverse slippage in basis points, top-size fraction, arrival delay,
fresh-quote window and fixed orders anchored to original market sequences.
`fixtures/paper-ioc-scenario-v1.json` is a synthetic-fixture example; its prices
and anchors are not an appropriate plan for an arbitrary real recording.

The portable lab shows simulated orders/fills, positions, P&L, cumulative assumed
costs, source/scenario fingerprints and price/P&L chart controls. The exporter
checks exact ledger replay and writes `cost-audit.json` from independent Decimal
checks. All acknowledgement/fill/cancel events are modeled assumptions. A replay
can finish with open positions or pending orders and exposes those states.

The Rust-only equivalent is `paper-execution-replay --input DIR --scenario FILE
--output-dir NEW_DIR --origin captured-public-data --feed bbo`.

## Replay a finalized market recording

Build the debug binary, then use a new output directory:

```sh
./scripts/dev build --locked
python3 ops/paper_market.py --binary target/debug/giethoorn \
  --input data/supervision-001/run-000002/session \
  --output-dir data/recorded-paper-001 \
  --origin captured-public-data --feed bbo
```

Declare `synthetic-fixture` when the recording is generated test data. The helper
validates and copies the closed source, persists mapped paper inputs and original
event links, independently replays them, and writes `paper-lab.html`. Download
that HTML to inspect prices, recorded freshness and exact event provenance offline.
Its assumed account stays flat: no strategy decisions, orders or fills are made.

The source must be a finalized schema-2 segmented directory with the selected
channel enabled. Active, unfinalized, corrupt, oversized or unsupported sources
fail. The first adapter handles one child recording and fewer than 10,000 original
events, without truncation. Completion attests that recording, not the supervisor's
24-hour gate. Every generated paper input is saved before processing, and original
recordings are never changed.

The equivalent Rust-only export is `paper-market-replay --input DIR --output-dir
NEW_DIR --origin captured-public-data --feed bbo`. Its output parent must exist.
It writes `source/`, the manifest, `paper-input.jsonl`, `paper-updates.jsonl`,
`market-links.jsonl`, `paper-report.json` and `market-replay.json`.

## Replay the synthetic scenario

```sh
./scripts/dev run --locked -- paper-replay \
  --input fixtures/paper-synthetic-v1.jsonl \
  > data/paper-updates.jsonl 2> data/paper-report.json
```

Twenty-nine versioned input events produce one derived update per event and a
final report. The scenario demonstrates partial fills during cancellation,
duplicate-fill protection, a late cancel ACK after full fill, stale-data rejection,
long-to-short-to-flat positions and manual halt. Its prices, fills and fixed fee
rate are scripted. No trading strategy or exchange execution was performed.

The hand-calculated example ends with realized FIFO P&L `1.6`, fees `0.0592`, net
P&L `1.5408`, and paper collateral `10001.5408`, from starting collateral `10000`.
Those are accounting test vectors, not measured profit. Monetary output remains
exact decimal strings. Reports expose historical-mark freshness and unresolved
working orders/positions; completion means an end event, not a flat account.

Malformed complete records, unknown fields/versions, reused IDs with changed
payloads, invalid transitions and unsupported arithmetic fail. Explicit
`--allow-incomplete` permits a valid unfinished prefix and its last torn fragment;
it never skips corrupt complete input or trailing data after completion.

## Open the visible Paper Lab

Build the development binary without replacing the collector's release:

```sh
./scripts/dev build --locked
python3 ops/paper_demo.py --binary target/debug/giethoorn \
  --output-dir data/paper-lab-001
```

Use a new directory. The helper invokes the actual Rust CLI, keeps scenario,
updates, report and input/binary hashes, then writes `paper-lab.html`. Download and
open that self-contained HTML. Play/pause, previous/next, the scrubber and event
trace navigate actual precomputed model states offline. No network is required.

To link it from a local monitor on the machine holding the files:

```sh
python3 ops/dashboard.py --experiment data/reliability-24h-001 --port 3000 \
  --paper-view data/paper-lab-001/paper-lab.html
```

`/paper` is served only when explicitly configured. It serves the saved artifact;
HTTP requests never execute a binary or submit orders. Main-monitor saved snapshots
hide that live-server navigation. Cloud preview forwarding is currently unavailable
in this chat, so portable views/screenshots are the immediate viewing path.

## Limits and next step

Read [the accepted model decision](decisions/0003-paper-model.md) for the exact
FIFO, fee, stale-data, cancellation and halt semantics. The first slice has no
automatic market-touch fills, funding, margin, liquidation, queue or execution
latency model. There is no arbitrary-order entry form or live-feed paper adapter.

Offline model work and recorded-market replay proceed alongside the outstanding
collection reliability work. Explicit execution assumptions, actual reliability
gate review and calibration precede live strategy simulation.
[status.md](status.md) records current evidence and experiment state.
