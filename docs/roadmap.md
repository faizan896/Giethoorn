# Product roadmap and acceptance gates

The first product is a dependable research and execution foundation. Do not add a
second exchange or a profitability claim before the preceding gates are met.

## 1. Capture and deterministic replay — live acceptance passed

Deliver a CLI, explicit connection lifecycle, exact prices, durable versioned
records, strict replay and automated regression checks.

Acceptance:

- Golden fixture replay and real local WebSocket capture/replay match byte for byte.
- Invalid data, stale snapshots, empty sides, sequence gaps, crashed captures,
  disconnect/reconnect and local recording failures have executable tests.
- A real Hyperliquid session contains valid books and replays identically.
- After live acceptance, run a longer capture to measure data rate, disk usage,
  stalls, reconnect behavior and latency before planning unattended collection.

Offline and real Hyperliquid capture/replay checks have passed in the restored
published environment. See `docs/status.md` for exact evidence. Short acceptance
checks do not establish unattended collection reliability.

## 2. Sustainable collection and paper execution — current milestone

Add checksummed log segments, rotation, disk/retention limits, metrics, a supervised
24-hour run and a replay inspection interface. Add desired-order and order-lifecycle
models plus a paper execution adapter.

Implemented so far: per-journal and whole-session byte limits, a best-effort disk
reserve, SHA-256 segment seals, rotation, explicit crash-prefix recovery, offline
inspection and reproducible live verification helpers. A real process-kill test
verifies recovery of sealed data and its unsealed tail. Bounded supervision now
validates before restarting and has executable disconnect, kill, integrity,
shutdown, watchdog and parent-death tests. Offline supervision audit independently
recomputes archive evidence. A full one-hour live supervision window passed with
12 finalized children, 304 snapshots and exact replay, with independent hashes.
A 1,000-snapshot local burst passes exact replay; native service-launcher
acceptance and offline unit syntax checks also pass.
Explicit schema-2 feed profiles now implement separate depth/BBO freshness while
keeping legacy output exact. The live combined-feed check and real network/crash
fault rehearsal pass. Two actual 24-hour attempts stopped before completion;
retained recordings verify but the full gate remains pending. Broader load exercises, target-host
service/reboot ownership and cross-session archival/retention remain. See
`decisions/0002-feed-profiles.md` and `reliability-experiment.md`.
An isolated offline paper ledger and synthetic Paper Lab now exercise order states,
cancel/fill races, idempotency, FIFO positions, exact fees/P&L and basic risk guards.
This development proceeds alongside collection checks; live-feed paper integration
and strategy activation still follow the actual reliability gate and explicit
fill-model calibration. See `paper.md` and `decisions/0003-paper-model.md`.
The version-2 recorded-market adapter now maps finalized schema-2 recordings to
source-linked offline paper marks and historical feed health. Orders and fills
remain disabled in this mode; it does not bypass the live-integration or strategy
gates. See `decisions/0004-recorded-paper.md`.
Version 3 now runs predeclared offline IOC order scenarios on those recordings,
with explicit fee, adverse-slippage, latency and shared-size-cap assumptions.
The ledger and an independent Decimal check verify costs and unresolved exposure.
This is controlled protocol testing; model calibration and strategy evaluation
remain ahead. See `decisions/0005-controlled-execution.md`.

Acceptance: a 24-hour capture survives injected disconnects and controlled restarts;
recovery is documented; resource use is bounded; paper decisions replay exactly.
Simulation must label its queue/fill/latency assumptions. Never treat top-of-book
touches as guaranteed maker fills.

Offline preparation now has a [first research protocol](research-plan.md): freeze
and qualify the existing data, test one fixed BBO-size prediction hypothesis,
retain chronological evaluation partitions, then specify a separate costed test.
The [quality report](quality.md) implements the first dataset qualification step;
the signal runner is not implemented yet.
This preparation does not activate strategies or change the collection gate.

## 3. Single-venue execution and risk

Introduce authenticated execution as a separately configured capability. Add unique
client order identities, pending states, acknowledgements, partial fills,
idempotency, rate limits, startup reconciliation, inventory/exposure limits,
stale-data protection and an emergency stop.

Acceptance: testnet scenarios prove each lifecycle and risk transition, including
unknown send outcomes and cancel/fill races. Replaying a session reproduces every
decision. A documented operational gate precedes any funded deployment.

## 4. Cross-venue execution

Add Lighter and a hedge coordinator. Account for venue-specific sizing, account
models, balances, fees, funding, basis risk and margin independently.

Acceptance: partial maker fills, rejected/delayed hedges, outages and recovery are
reconciled; maximum unhedged exposure and its permitted duration are enforced.

## 5. Research and economic validation

Build a calibrated simulator from real captures and executions. Add reproducible
datasets, versioned strategy configuration, held-out evaluation, cost accounting,
and operational dashboards. Measure adverse selection and hedge slippage.

Acceptance: simulated behavior is reconciled to real observations, assumptions
and discrepancies are visible, and economic claims include costs and uncertainty.

## Decisions deferred until evidence exists

Kernel timestamping, epoll/mio, custom queues, colocation, additional markets,
multi-tenant services, billing and a polished UI. Each needs a measured requirement
or user workflow; none is a prerequisite for validating the data foundation.
