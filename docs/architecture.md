# Architecture decision: an auditable data foundation

Status: accepted for milestone 1.

Start with a small Rust application and library, not a multi-service platform.
Rust provides explicit state and memory ownership, while retaining a path to lower
latency later. Use established TLS/WebSocket libraries and synchronous networking.
The deterministic engine must remain independent of those choices.

```text
public WebSocket -> journal append + sync -> engine -> quote JSONL
                         |
                         +---- replay -> same engine -> identical quote JSONL
```

## Boundaries

| Module | Responsibility |
| --- | --- |
| `event` | Versioned recording format, timestamps, connection identity |
| `journal` | Timestamped appends, storage-mode selection, strict streaming replay |
| `segments` | Container version 1, SHA-256 seals, rotation, budget and recovery |
| `supervisor` | Bounded child processes, validation, restart policy and resource samples |
| `transport` | TCP, HTTP CONNECT, verified TLS, HTTP upgrade |
| `capture` | Connection lifecycle, heartbeat, retry budget, output and shutdown |
| `hyperliquid` | Wire protocol validation and exact decimal book snapshots |
| `engine` | Pure recorded-event-to-state and quote transitions |
| `lifecycle` | Shared sequence, schema and connection-state validation |
| `feeds` | Schema-2 normalization, independent channel state and recorded-time freshness |

There is one synchronous owner of network connections, event ordering and writes
in this version. It processes one public coin and either legacy depth or explicit
depth/BBO subscriptions on the same socket. Separating networking and
state into threads now would add queue/backpressure failure modes without an
established latency budget. A future reactor/queue must retain the same replay
contract and prove its benefit with measurements.

## Recording contract, schema 1

Each newline-terminated JSON object has a schema version, contiguous one-based
sequence, Unix local timestamp in nanoseconds, elapsed monotonic nanoseconds,
connection ID and tagged event. Sessions cannot be concatenated silently.
Nanosecond fields are JSON u64 integers: Python/Rust readers preserve them, while
a future JavaScript consumer must use a lossless integer parser rather than
converting them to `Number`.

Session events use connection zero. Attempts increment the connection ID. A book
exists only while connected and after a valid snapshot. Invalid input clears the
active book and is fatal; it is retained in the journal for diagnosis. Replay
fails at that same input rather than silently skipping a bad event.

The log records connection attempts, TCP availability, the WebSocket upgrade,
incoming/outgoing application messages and observed control messages. Handshake
headers use an allowlist. A `text_sent` event records an **intent before a send**;
it does not prove successful delivery. Schema-2 public subscription ACKs are
recorded and matched separately. Order acknowledgement will be a separate fact if
orders are introduced.

This is an application-level event log, not packet capture. It does not preserve
encrypted TLS records, proxy credentials, kernel timestamps, frame fragmentation
or every intermediate transport write. Event timestamps are taken at the
application observation boundary, before JSON parsing and durable processing.

Every record is synchronized before further state processing or application
messages. This deliberately trades throughput for simple failure semantics.
`sync_data` is subject to the underlying filesystem/storage contract; it is not
a distributed backup. On Unix, file creation also syncs the file and its parent
directory. Capture now enforces a per-journal byte budget and a best-effort free
disk reserve. The new directory container adds SHA-256 seals, rotation and a
whole-session limit. Single-file logs retain structural validation without hashes.
Cross-session archival/retention, replication and migrations remain future work.
Neither format is tamper-proof or cryptographically authenticated: an attacker
could rewrite both an index and its data. See [the container contract](segmented-format.md).

Replay uses sequence order and recorded time only. Wall time can move backward;
monotonic elapsed time cannot. The current engine has no time-based trading
decisions. Future expiry/risk/strategy decisions must consume recorded timer
events, never call the clock inside the engine.

Recovery is explicit: only a valid complete prefix is replayed, with an incomplete
status when there is no end event. A corrupt full line is never ignored. Streaming
outputs can precede a later validation failure: consumers must honor the exit
status. Record size is bounded at 4 MiB and incoming WebSocket messages at 1 MiB.

## Market semantics

Hyperliquid `l2Book` sends bid and ask depth snapshots with `px` and `sz` as strings
and `n` as the aggregate order count. We validate both sides and replace both
atomically. Empty sides are valid but produce no midprice. Levels must have
positive exact decimals and counts and strictly sorted unique prices.

Decimals use `rust_decimal`, bounded by its 96-bit coefficient and maximum scale
of 28. Parsing may not round. Midprice and spread arithmetic are checked for
representability. A stale exchange timestamp is ignored inside a connection;
duplicate/equal timestamps are accepted because there is no exchange sequence
in this feed. This does not establish lossless delivery or global ordering.

The session's last quote is historical. Connection closure and errors clear active
state even though that historical observation remains in the report. A successful
capture requires a usable two-sided observation; a port or subscription ACK alone
does not qualify.

Protocol references: the official [WebSocket implementation](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/hyperliquid/websocket_manager.py)
and [message types](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/hyperliquid/utils/types.py).
Real endpoint capture and short rotation checks have passed. Observed feed cadence
still needs venue/network diagnosis before time-sensitive strategies; see `status.md`.

## Dependency and operational policy

- Pin Rust and commit Cargo.lock. CI uses `--locked` and the same local checks.
- Review dependency upgrades deliberately; do not disable TLS/checksum validation.
- Store captures outside tracked source. Do not introduce private keys into logs.
- Keep strategy, risk, reconciliation and exchange-specific transport separate.
- Measure latency, disk throughput and data loss before selecting infrastructure
  or claiming any HFT capability.

## Additive operational interfaces

The capture byte/free-space guards and offline `inspect` command do not change
schema 1 or quote serialization. `replay_observed` validates records through the
same engine before exposing them to diagnostic measurements. Diagnostics neither
feed back into engine state nor consult a live clock. Source-clock deltas are
reported with their clock-offset caveat; they are not interpreted as network RTT.

Default directory storage is container version 1 around unchanged event schema 1.
`CaptureOptions` explicitly selects a `JournalMode`. `collect` retains one engine,
sequence and monotonic origin across files; it never reconnects to rotate. Replay
and inspection select a directory or single file, and all sealed hashes are
verified before directory events enter the same deterministic engine. Recovery
of an unfinalized container explicitly reports an incomplete session even when a
durable event end exists without its container footer.

Explicit feed profiles add schema 2 while preserving the schema-1 default and
golden output. Container 1 now declares and enforces either event version. A
`MarketEngine` routes by the first recorded version, never payload inference;
both engines share lifecycle validation. Schema-2 timer events and receive order
drive independent BBO/depth freshness without a live clock. Output labels market
source and health-only transitions. See [the format decision](decisions/0002-feed-profiles.md)
and [profile contract](feed-profiles.md). No strategy/risk consumer is implemented.

The supervisor stays outside deterministic engine state. Its control events,
signals, scheduling and telemetry do not enter market replay. Every child gets
a fresh container; cross-run gaps are explicit. After a crash, original quote
output may be a prefix of replay because WAL sync precedes output. Finalized
runs still require exact bytes. The subprocess exit contract separates exhausted
transport errors from recording/data/output failures. This public-data policy is
not automatic order-engine recovery. See `supervision.md`.
