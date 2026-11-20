# Giethoorn

Replayable market-data infrastructure for a future systematic trading product.

**Current milestone:** make public market-data collection operationally reliable.
Live Hyperliquid capture, checksummed rotation and exact replay have been verified.
Storage budgets, offline inspection, archive audit and interrupted-session recovery
are implemented. A one-hour supervision baseline passed. Two cloud 24-hour
attempts stopped before completion; their retained recordings verify. The first
Mac day run failed after about 11.5 hours on a collector deadline; the user's
local native audit verifies 334,794 observations with the source unchanged.
The full 24-hour gate remains pending. See
[status](docs/status.md) for the current result.
Explicit schema-2 profiles separate BBO and
depth freshness; legacy capture output remains the default. No wallet, private keys,
live order placement, or live-feed strategy execution exists in this version. An isolated
offline paper model and Paper Lab support synthetic lifecycle/accounting scenarios
and source-traceable replay of recorded market marks; live-feed integration and
broader strategy evaluation remain ahead.
Controlled version-3 IOC scenarios now test simulated orders and explicit
fee/slippage/liquidity assumptions on saved recordings, without live execution.

## Get started

On an Intel Mac, use the [local Mac setup](docs/local-mac.md). Docker Desktop
builds/tests the Linux application and keeps recordings in `~/GiethoornData`.
No paid server or host Rust installation is required. Start with the offline lab
and 90-second recovery rehearsal before requesting a fresh 24-hour window.
Use `bash scripts/mac review` to audit a stopped local run offline, without
rebuilding the image or changing its recordings.
Use `bash scripts/mac replay N` to open one finalized child recording in the
offline Paper Lab; `N` is the child number shown in the review. This uses recorded
prices and feed health, with orders and fills disabled.
Use `bash scripts/mac quality` for an offline [dataset-quality report](docs/quality.md)
covering per-session gaps, feed freshness and candidate spans for the fixed study.
The [fixed signal study](docs/study.md) runs a predeclared prediction on one frozen
partition, defaulting to development while other groups remain unrun. Its metrics
describe predictions, with no orders or economic-performance claim.
The [first retrospective comparison](docs/r001-results.md) is complete; costs and
large missing-label shares still prevent a profitability conclusion.
The [costed paper probe](docs/cost-study.md) now compiles one causal R001 entry/close
per selected development recording across six assumed execution profiles. Its
portable report retains rejects, partial fills and unresolved exposure. These
independent exploratory cases do not constitute portfolio returns or live trading.
The [first Mac cost-probe readout](docs/cost-probe-results.md) reports losses in
all 13 closed cases, ten expired entries and one unresolved short. This small
mechanics suite establishes no positive economic evidence for the current policy.
Use `bash scripts/mac explain COST-ID` for the [read-only quote-window diagnostic](docs/expiry-review.md)
on a saved cost snapshot. It checks original source/ledger evidence and explains
order expiries while preserving every historical case outcome.
The [first Mac diagnostic readout](docs/mac-expiry-results.md) verifies the reported
38 orders and explains all 11 expiries as three shared request timelines whose
next native quote arrives after the model deadline. Physical cause remains unknown.
Use `bash scripts/mac cadence EXPLAIN-ID` for the [unique-source cadence audit](docs/cadence.md),
comparing all recorded BBO messages with native quote opportunities while retaining
connection boundaries, unusable updates and censored source edges.
The [first Mac cadence readout](docs/mac-cadence-results.md) reports 12,267 BBO
observations across four five-minute recordings, with raw/native counts matching
and 7.78% of complete within-connection intervals exceeding 250 ms.
Use `bash scripts/mac feed-check` for a [new 120-second recording check](docs/feed-check.md),
followed by independent offline integrity/replay/cadence verification. The first
attempt is retained even if it fails; existing collection evidence stays separate.

Requires Rust **1.91.1**, a C compiler, pkg-config, and OpenSSL development headers on
Linux. `rust-toolchain.toml` pins the toolchain; `Cargo.lock` pins dependencies.
Python 3.9+ and Bash are required for the operations checks/helpers.
The managed cloud already provides the system prerequisites. Its repeatable setup is:

```sh
bash scripts/cloud-setup.sh
./scripts/check
```

On other machines, install Rust through [rustup](https://rustup.rs), plus the system
prerequisites (Ubuntu: `build-essential pkg-config libssl-dev ca-certificates`).
`scripts/dev` activates the managed cloud toolchain if present and otherwise uses
your installed Cargo. All commands below run from this checkout; no Git worktree
is required.

### See collection in a dashboard

```sh
python3 ops/dashboard.py --experiment data/reliability-24h-001 --port 3000
```

This read-only monitor shows real recorded prices, independent feed health,
replay verification and experiment progress. Run it on the machine holding the
experiment. `Save view` exports an interactive HTML snapshot that opens without
the server. See [viewing and snapshot instructions](docs/dashboard.md) and
[the current handoff](docs/status.md) for the actual running experiment/artifacts.
The monitor and Paper Lab use a shared [Giethoorn-inspired design](docs/design.md).

### Try the offline Paper Lab

```sh
./scripts/dev run --locked -- paper-replay --input fixtures/paper-synthetic-v1.jsonl
./scripts/dev build --locked
python3 ops/paper_demo.py --binary target/debug/giethoorn --output-dir data/paper-lab-001
```

The generated `paper-lab.html` plays a clearly synthetic order/fill scenario, with
Rust-generated positions, fees, P&L and risk states. No orders are sent. See
[the paper model and visible lab](docs/paper.md) for assumptions and viewing steps.

### Replay recorded prices in Paper Lab

```sh
./scripts/dev build --locked
python3 ops/paper_market.py --binary target/debug/giethoorn \
  --input data/supervision-001/run-000002/session \
  --output-dir data/recorded-paper-001 \
  --origin captured-public-data --feed bbo
```

This offline adapter requires a finalized schema-2 recording. Its portable lab
shows recorded prices, independent feed health and source-event references.
Orders and fills are disabled; it does not claim strategy performance or a passed
24-hour collection window. See [recorded replay and provenance](docs/decisions/0004-recorded-paper.md).

### Test controlled execution scenarios

```sh
python3 ops/paper_execution.py --binary target/debug/giethoorn \
  --input data/supervision-001/run-000002/session \
  --scenario path/to/fixed-scenario.json \
  --output-dir data/execution-lab-001 --origin captured-public-data --feed bbo
```

The predeclared scenario supplies prices/quantities, source-event anchors, risk
limits and assumed costs/timing. It produces an offline lab and independent cost
audit. See [the scenario guide](docs/paper.md) and
[the execution assumptions](docs/decisions/0005-controlled-execution.md).

### Compare fixed scenarios across assumptions

```sh
python3 ops/paper_batch.py --binary target/debug/giethoorn \
  --manifest path/to/batch-manifest.json --output-dir data/batch-001
```

The bounded offline runner freezes each recording and order plan, then compares
declared fee, slippage, delay and liquidity profiles. It retains verified, failed
and unfinished cases in a portable Batch Lab and JSON report. This is sensitivity
testing with uncalibrated assumptions. See [manifest format and viewing](docs/paper.md#batch-sensitivity-testing).

### Try replay without an exchange connection

```sh
./scripts/dev run --locked -- replay --input fixtures/hyperliquid-btc.jsonl
```

The checked-in fixture is **synthetic**, not a real exchange capture. It exercises
decimal precision, stale snapshots and reconnects. Three JSON quote observations go
to stdout; a JSON summary goes to stderr. The matching golden output is in
`fixtures/hyperliquid-btc.quotes.jsonl` and is checked by the CLI integration test.

### Capture public market data

```sh
./scripts/dev run --locked -- capture \
  --coin BTC --network mainnet \
  --output data/btc-session-001.jsonl --duration-secs 60 \
  > btc-live-quotes.jsonl
```

Use `--network testnet` for testnet. These are public read-only subscriptions, so
neither network requires credentials. Coin identifiers are case-sensitive: use the
exchange's exact identifier. One coin and one connection are active at a time.

The output journal must be a **new path**; the program never overwrites a session.
Its parent directory is created automatically. Prefer `data/` for local recordings
and output, since Git ignores that directory. Journals can become large; select a
bounded duration and monitor free disk space. This single-file command stops at
its budget; use `collect` below for rotation.
Capture defaults to a 256 MiB journal limit and a 1 GiB free-space reserve. Set
`--max-journal-bytes` and `--min-free-disk-bytes` explicitly to change these limits.
Hitting a limit stops capture with a nonzero exit status and preserves its prefix.
These limits cover the journal, not redirected stdout or other processes' files.

### Collect with checksummed rotation

```sh
./scripts/dev run --locked -- collect \
  --coin BTC --network mainnet --duration-secs 3600 \
  --output-dir data/btc-collection-001 \
  --max-segment-bytes 67108864 --max-session-bytes 1073741824 \
  > btc-live-quotes.jsonl
./scripts/dev run --locked -- replay --input data/btc-collection-001 \
  > btc-replayed-quotes.jsonl
cmp btc-live-quotes.jsonl btc-replayed-quotes.jsonl
```

The collection directory must be **new**. Segments default to 64 MiB, and the
whole-session budget defaults to 1 GiB including the index. Rotation keeps the
same connection and event sequence. Sealed segments carry SHA-256 checksums;
replay verifies every sealed file before emitting quotes. The event schema and
single-file recordings remain compatible.

For a bounded acceptance check that forces small segments:

```sh
./scripts/verify-collect 60 BTC mainnet 8192
```

Replay and `inspect` accept either a single file or a collection directory. Stop
the collection process before reading a directory: a shared/exclusive lock rejects
active writers. After an interrupted collection, use `--allow-incomplete` to recover
the verified sealed prefix and its one unsealed tail. Recovery never disables
checksums on sealed files. See [container format and recovery](docs/segmented-format.md).

### Verify live versus replay output

```sh
./scripts/dev run --locked -- replay --input data/btc-session-001.jsonl \
  > btc-replayed-quotes.jsonl
cmp btc-live-quotes.jsonl btc-replayed-quotes.jsonl
```

For a repeatable live check that creates its own artifact directory and enforces
all command exit statuses:

```sh
./scripts/verify-live 30 BTC mainnet
```

It captures usable data, replays, compares output and writes an inspection report.
Failed runs retain their diagnostics under `data/`.

Replay requires no network access. Capture and replay share the same engine; their
quote streams must match byte for byte. A nonzero exit status is a failure even if
partial quotes were printed. A summary's `complete` field means an end event was
recorded (and, for a directory, its finalization footer was committed); check
`end_reason` too, since a failed capture can have a complete journal.
`last_quote` is historical and does not establish current market-data freshness.

If capture is killed or its output/disk fails, recover only its valid prefix:

```sh
./scripts/dev run --locked -- replay --input data/btc-session-001.jsonl \
  --allow-incomplete
```

Recovery drops only an unterminated last record and permits a missing session end.
It still rejects malformed complete records, sequence gaps and unsupported schemas.
Any quotes emitted before a replay error are provisional until replay succeeds.

### Select fast quotes and depth independently

```sh
./scripts/dev run --locked -- collect --feed-profile combined \
  --coin BTC --duration-secs 120 --output-dir data/combined-001 \
  > data/combined-001.live.jsonl
./scripts/dev run --locked -- replay --input data/combined-001 \
  > data/combined-001.replayed.jsonl
cmp data/combined-001.live.jsonl data/combined-001.replayed.jsonl
```

An explicit `depth`, `bbo` or `combined` profile selects schema 2, with separate
ACKs, freshness, timestamp ordering and observations. A fresh BBO cannot refresh
old depth. Recorded timers reproduce stale transitions during replay. Omitting
the profile keeps the original schema-1 contract. See
[feed profiles and output](docs/feed-profiles.md).

### Inspect collection quality

```sh
./scripts/dev run --locked -- inspect --input data/btc-session-001.jsonl
```

This emits one JSON report with session status, file size, connection errors,
one-/two-sided snapshot counts, snapshot gaps, reconnect gaps and recorded timing.
Use `--allow-incomplete` for crash-prefix diagnostics. A successfully parsed
inspection can describe a failed capture: check its `status` and `session.end_reason`.
Timing refers to the recording, not current market health. See the
[collection runbook](docs/operations.md) for interpretation and limits.

### Supervise bounded collection runs

```sh
./scripts/dev run --locked -- supervise --coin BTC --duration-secs 1800 \
  --run-duration-secs 300 --max-restarts 3 --output-dir data/supervision-001
```

The Unix supervisor snapshots the collector binary, creates a new directory per
run, validates checksums/replay before restarting, and samples child memory and
file descriptors. Network failures and SIGKILL recovery have bounded retries;
corruption and recording failures stop supervision. SIGINT/SIGTERM stops the
owned child gracefully, with forced-stop and parent-liveness guards. See
[supervision, budgets and result interpretation](docs/supervision.md).

### Audit saved supervision evidence

```sh
./scripts/dev run --locked -- audit-supervision --input data/supervision-001 \
  > data/supervision-001.audit.json
```

The read-only audit recomputes hashes, lifecycle, market identity, replay output,
caches, counters and resource maxima. `integrity: verified` is separate from a
healthy completed window. Active or unfinished supervision roots are rejected;
recover their individual recordings explicitly. See [auditing](docs/auditing.md).

Reviewable service artifacts and their current validation limits are described
in [deployment](docs/deployment.md). No service installation is performed by setup.
The [reliability experiment](docs/reliability-experiment.md) documents scheduled
connection/crash faults, bounded recovery and the actual 24-hour completion rule.

## Reliability rules

- Every application event is appended and `sync_data` completes before processing
  it or sending the associated outgoing message. This prioritizes auditability over
  latency; it is not a benchmarked HFT transport.
- Sequence numbers define local event order. Both local wall-clock nanoseconds and
  monotonic elapsed nanoseconds are recorded; replay never consults the clock.
- Prices and sizes use exact bounded decimals, never floating point. Unsupported
  precision, invalid levels and crossed books fail explicitly.
- Each `l2Book` message replaces the full subscribed depth. It is not a delta and
  does not provide a full market-by-order book or queue position.
- Disconnects clear the book. Reconnect attempts use bounded exponential backoff
  and resubscribe. The default allows three retries across the whole session.
- No new valid snapshot for 15 seconds triggers reconnect; adjust
  `--stale-after-secs` for a quiet market. Older exchange timestamps are ignored
  within a connection; equal timestamps are accepted in local receive order.
  Explicit profiles use independent required-channel deadlines instead; their
  defaults are 15 seconds for depth and two seconds for BBO.
- Journal, validation and quote-output errors stop capture immediately. They are
  never treated as retryable network failures.
- Storage limits are checked before writes. Free-space checks are best effort
  on a shared filesystem; they are not an operating-system storage quota.
- HTTP CONNECT proxies and `HTTPS_PROXY`/`https_proxy`, `ALL_PROXY`/`all_proxy`, and
  `NO_PROXY`/`no_proxy` are supported. TLS verification remains enabled. Handshake
  headers are allowlisted; proxy credentials and cookies are not logged.

## Validation and next milestones

`./scripts/check` runs formatting, Clippy with warnings denied, engine and journal
tests, CLI golden-output tests, and real local WebSocket integration tests. CI runs
the same checks without contacting an exchange. Linux integration tests also run
the production CLI through a local HTTP CONNECT proxy and TLS server, checking
both successful certificate verification and rejection of invalid certificates.
A live capture/replay comparison is a separate acceptance check, not something
the offline fixture can prove.

See [the architecture](docs/architecture.md), [milestone acceptance criteria](docs/roadmap.md),
and [the development handoff](docs/status.md). This is a foundation, not a deployed
or profitable trading product.
