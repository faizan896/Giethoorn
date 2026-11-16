# Decision: isolated paper model, version 1

Status: implemented as an offline research prototype. Development can proceed
alongside the collector reliability experiment. Live-feed integration, calibrated
simulation and strategy activation still require their acceptance gates.

## Boundary and version

`paper-replay` consumes a separate stream with `paper_schema_version: 1`, local
sequence, recorded monotonic time and explicitly typed paper events. It cannot
parse a market journal as executions. Market event/normalization schemas 1 and 2
and their golden output remain unchanged. No exchange order adapter exists.

Every scenario declares `synthetic` or `manual_simulation` provenance. Every output
frame repeats paper mode and its source. The demo exporter accepts synthetic
scenarios only. Future captured-data adapters need explicit source references and
a reviewed version decision, not relabeling scripted data as live.

## Order model

Limit orders move through pending new, open, partially filled, pending cancel and
filled/cancelled/rejected states. Acceptance is explicit. Pending cancellation
continues reserving exposure until acknowledgement. Fills can race a cancellation;
a full fill remains filled when its pending cancellation ACK arrives later.

Client-order identities cannot be reused for different intent. Known identical
order/fill/ACK repeats are idempotent where specified; a fill identity with a
different payload is an error. New fills on unacknowledged or terminal orders,
overfills and off-limit prices fail transactionally. Paper replay never skips
malformed complete records or invents missing acknowledgement.

## Fill and financial assumptions

Fills are explicit `assumed_fill` inputs. A quote touch never produces a maker fill.
There is no queue model, latency model or inference of actual venue execution.

Positions use a USDC-denominated linear-contract FIFO ledger. Opposite fills close
old lots first and may open a position in the other direction. This is a declared
research accounting model; it does not claim to reproduce Hyperliquid's venue
accounting, margin, liquidation or funding rules.

All amounts are plain decimal strings. Parsing and arithmetic reject unsupported
precision instead of rounding. Representation is bounded to a 96-bit coefficient
and scale 28, with checked i128 intermediate arithmetic. Some mathematically
representable extreme calculations are conservatively rejected when an
intermediate does not fit. FIFO lots avoid dividing a cost basis into repeating
average prices. Invalid transitions/overflow leave the previous model state intact.

For the configured fixed assumed fee rate:

```text
fee                 = fill price × fill quantity × fee rate
collateral balance  = starting collateral + realized FIFO P&L − fees
equity              = collateral balance + marked unrealized P&L
net P&L             = equity − starting collateral
```

Opening contract notional is not deducted as spot principal. Funding, rebates,
margin, liquidation, borrowing, venue increments and cross-currency conversion
are unmodeled. A historical mark can value a report, but it remains labeled stale
or disconnected and cannot authorize new orders.

## Risk and limits

New orders require a fresh recorded market mark. Recorded timers expose stale
data without a live clock. Limits cover working-order count, per-order notional
and worst possible long/short position. Opposite unconfirmed orders do not net
away exposure. A loss from starting collateral at or beyond the configured limit
latches a halt; manual halt is also supported. Neither halt nor session end
invents cancellations or flattens positions. Known-order fills remain accountable
during a stale/disconnected period.

The first model uses a transaction copy with fixed limits: 10,000 input records,
1,000 unique orders, 5,000 unique fills and 64 KiB per input record. It is not a
benchmarked HFT execution loop. A live/interactive adapter must persist input and
intent before processing/sending, and must preserve this replay contract.

## Acceptance and next work

The synthetic golden scenario and 22 Rust tests verify lifecycle, cancellation
races, idempotency, FIFO long/short/flat accounting, exact fees, risk reservations,
loss/stale-data halts, atomic failure, strict input and real CLI output. The visible
Paper Lab plays those actual Rust-generated frames; it does not calculate account
state in JavaScript. Demo values are not strategy-performance evidence.

Next: review the actual 24-hour gate, implement an explicit audited-data adapter,
calibrate conservative fill/fee/latency assumptions and only then evaluate a
strategy. Authenticated testnet orders remain a later separate capability.
