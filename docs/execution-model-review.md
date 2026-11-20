# Offline execution-model assumption review

Status: initial source/interface review completed; the separate arrival-book
comparison is now [implemented](model-comparison.md) under
[decision 0015](decisions/0015-execution-model-comparison.md). The existing native binary, paper
versions, original policy and all saved economic outcomes remain unchanged.
This follows the [completed short Mac recording check](mac-feed-check-results.md).

## What the current model actually does

The implemented model is explicitly `assumed_next_fresh_quote_ioc_v1`, with
paper version 3 and execution-model version 1. In `src/paper/execution.rs`,
pending simulated orders wait for a later selected-feed `MarketObserved` event
at or after assumed arrival, strictly before expiry. An observed event at or
after expiry rejects the waiting simulated order before any quote attempt.
The original anchor/standing mark is not an execution opportunity. Source end
does not invent a fill, acknowledgement, expiry or closing price.

The independent verifier in `ops/paper_execution.py` requires a strictly later
source sequence, the same source quote and the declared timing window. This is
a deliberate, testable sensitivity assumption, not an actual order-channel
measurement. The earlier Mac probes behaved according to this rule; their
negative closed controls and unresolved short remain the recorded result.

The fresh check gives matching raw/native observations with roughly 7.33% of
complete intervals above 250 ms. Neither that fraction nor the 290.494621-ms p95
calibrates the chance that a request could execute. New public messages and the
matching of an order are separate observations.

## Official interface evidence, with limits

The official Python SDK was read at fixed commit
`2fdb18f9517675ea03695a0962bd19eece9c83f0`:

- [`utils/signing.py`](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/2fdb18f9517675ea03695a0962bd19eece9c83f0/hyperliquid/utils/signing.py)
  defines `Alo`, `Ioc` and `Gtc` limit time-in-force values.
- [`exchange.py`](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/2fdb18f9517675ea03695a0962bd19eece9c83f0/hyperliquid/exchange.py)
  constructs its market-open helper as an aggressive IOC limit order with a
  slippage-derived limit; market-close passes `reduce_only=True`. That helper's
  slippage setting bounds the submitted limit rather than observing an actual
  execution price. Our current model's adverse-slippage parameter instead
  multiplies a recorded touch to produce an assumed fill price. Those meanings
  must not be conflated. No SDK function was installed or executed here.
- [`utils/types.py`](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/2fdb18f9517675ea03695a0962bd19eece9c83f0/hyperliquid/utils/types.py)
  exposes distinct BBO, order-update and user-fill subscription interfaces.

These source facts do not establish BBO publishing frequency, venue matching
timing, queue/available size, account-specific fees or actual delivery/fills.
The official GitBook order-types, exchange-endpoint and subscriptions pages were
unavailable from this environment (HTTP CONNECT 403); no content from them is
claimed verified. Source snapshots/hashes and failed access receipts are retained
under the path at the end. Verified venue documentation and actual execution
telemetry remain separate calibration work.

## Comparison contract

Build an offline model-comparison view from a frozen scenario and original
source, with explicit source hashes and a new model/version decision. Keep the
existing next-new-quote output byte-identical and independently identifiable.
Do not change its rules in place or reclassify old losses as corrected returns.

The alternative is an **assumed arrival-book proxy**: at a declared simulated
arrival, inspect only the last selected-feed quote known at that time, retaining
its original sequence, receive time, connection, acknowledgement, prices, sizes
and age. A quiet window does not alone imply empty standing liquidity; the proxy
also cannot establish that the displayed quantity really remained executable.
Report eligibility and unknown actual execution separately from any optional,
explicitly assumed fill/cost calculation.

Before any output is generated, specify deterministic ordering for tied source,
request and assumed-arrival times; scheduled times must be labelled simulated
actions rather than rewritten original source records. No future quote may set
an earlier fill price. Freshness must be evaluated at arrival; a connection reset,
unusable update, stale quote or source end cannot be bridged to create liquidity.
Keep partial fills, shared/consumed size, equal-time ambiguity, limit protection,
fees, risk halts and unresolved exposure explicit. A proxy does not calibrate
maker queues, standing-size survival or the true quantity obtainable by an IOC.

Freeze the exact assumption grid and source cohort before inspecting its results.
Use hand-calculated synthetic quiet-window cases first: the current model may
expire while a prior quote exists; the alternative can report a causally known
reference quote without claiming that an actual venue fill occurred. Add arrival
ties, stale/empty/reconnect transitions, no usable quote, shared-size exhaustion,
limit breaches and EOF-before-arrival. Verify future-price independence and
financial arithmetic separately from ledger replay. Keep finite source/order/
output/time budgets and refuse corrupted or changed input.

The view should explain, per attempted order, which observation/rule each model
uses, why it abstains or assumes a fill, and how the declared costs follow.
It must distinguish unknown execution, rejected requests, partial fills and open
exposure from zero returns. This is an assumption comparison, not a calibrated
backtest, a new positive result for R001 or an activation of live trading.
Fresh economic confirmation needs its own frozen policy and later data; the
operational day gate also remains outstanding.

Evidence: `data/execution-semantics-sources-lbi2mlzs/` contains the pinned SDK
source snapshots/hashes and GitBook access receipts. No original Mac data is
included in that receipt.
