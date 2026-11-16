# Collection runbook

This release collects public data only. It is not an execution service. Use the
existing checkout and `scripts/dev` to activate the pinned Rust toolchain.

## Run and verify a bounded session

From the repository root:

```sh
./scripts/verify-live 30 BTC mainnet
```

The optional arguments are duration in seconds, exact coin identifier and network.
For a longer short check use `./scripts/verify-live 180 BTC mainnet`. A fresh
`data/live-check-<UTC timestamp>-<random suffix>/` contains:

- `session.jsonl`: the application event journal.
- `live-quotes.jsonl` and `replayed-quotes.jsonl`: must match byte for byte.
- `capture.stderr` and `replay.stderr`: JSON summaries on success, errors on failure.
- `inspection.json`: collection diagnostics, written only after capture and replay pass.

The script exits immediately on any failed command or comparison. It never
deletes diagnostic artifacts or overwrites an existing session. A subscription
acknowledgement or empty quote file cannot pass. Public API access requires
`api.hyperliquid.xyz` or `api.hyperliquid-testnet.xyz`; no credentials are needed.

## Storage guardrails

Direct `capture` accepts:

| Flag | Default | Behavior |
| --- | --- | --- |
| `--max-journal-bytes` | 268435456 (256 MiB) | Refuse the next whole record if it exceeds this file budget |
| `--min-free-disk-bytes` | 1073741824 (1 GiB) | Check available filesystem space before creation and every append |

Setting the reserve to zero disables free-space checks explicitly; the positive
file budget still applies. Library code using `Journal::create` is unbounded;
capture uses `create_with_limits` with explicit limits instead.

Limit violations are terminal local recording errors, not network retries. No
unlogged market data is processed and no later application intent is sent. The
last successfully recorded prefix remains available. A full disk or failed write
also prevents continuation; the last line may then be incomplete. Very small
budgets can reject even the first event, leaving no usable prefix.

Free-space checks are best effort: other writers may consume space between a
check and a write. They do not reserve space at the operating-system level. The
file budget covers only the event journal, not stdout, verification artifacts,
other sessions or other processes. Monitor the filesystem as well.

On Unix, new journal creation synchronizes the file and its parent directory.
Each accepted record is synchronized before publication as before. This is not a
replicated archive; filesystem and hardware guarantees still apply.

Single-file `capture` stops at its limit. For automatic rotation, use `collect`:

```sh
./scripts/verify-collect 60 BTC mainnet 8192
```

The fourth argument sets segment bytes; 8192 forces small segments for a short
acceptance check. The helper puts its new container under `data/collect-check-*/session/`
and keeps quotes/diagnostics alongside it. Do not put extra files inside the
container itself. `replay --input DIRECTORY` and `inspect --input DIRECTORY` verify
the sealed checksums automatically. No credentials or funds are used.

Direct `collect` adds `--max-segment-bytes` (64 MiB default) and
`--max-session-bytes` (1 GiB default, including index growth). It retains old
segments and stops when the session budget is exhausted. It never deletes or
overwrites data. There is no automatic cross-session cleanup or restart-in-place.
Use a new directory after a restart. See [the format contract](segmented-format.md).

## Recover and inspect

```sh
./scripts/dev run --locked -- inspect --input data/example.jsonl --allow-incomplete
./scripts/dev run --locked -- replay --input data/example.jsonl --allow-incomplete
```

Recovery accepts a valid prefix, skips only an unterminated final fragment and
permits a missing end marker. Malformed complete records, invalid market data,
sequence gaps and unsupported versions still fail. An empty file has no valid
prefix. Do not use recovery flags to relabel interrupted work as complete.

For a directory, first stop its writer: replay/inspection takes a shared lock
and refuses an active collection. Recovery verifies every sealed checksum and
permits the one canonical unsealed tail. Its finalization footer must be committed
for `complete=true`; an event end alone does not finalize a directory. The
`storage` object distinguishes format, seals, tail and finalization status.

## Interpret the inspection report

`inspect` performs the same validation as replay before printing one JSON object.
Its successful exit means the journal was readable; it does not mean collection
was successful. Look at `status`, `session.complete` and `session.end_reason`:

| Status | Meaning |
| --- | --- |
| `completed` | Closed session with a two-sided observation and no recorded connection errors |
| `completed_with_connection_errors` | Completed collection, but connection errors occurred; review the log |
| `failed` | A session end explicitly records failure |
| `incomplete` | Recovery mode read a prefix with no session end |
| `no_usable_data` | Closed session has no accepted two-sided observation |

Measurements:

- `file_bytes` is the file size observed when inspection opens the file. For an
  active file, it may differ from the eventual size; use completed files for final results.
- `recorded_duration_ns` spans the first and last accepted event timestamps.
- `max_snapshot_gap_ns` covers consecutive accepted snapshots on the same
  connection. Stale ignored snapshots do not reset it; outages between connections
  are counted separately in `max_disconnected_ns`.
- `max_first_snapshot_wait_ns` starts when the WebSocket opens, not at TCP connect.
- `max_disconnected_ns` includes a disconnected tail through the last recorded
  event, including a normal close. It excludes initial connection setup.
- `snapshot_age_at_end_ns` is measured at the last recorded event, not at inspection
  wall time. It does not establish that the last quote is currently fresh or connected.
- `observed_source_clock_delta` is local receive wall time minus exchange time,
  in milliseconds. It includes clock offset, exchange batching and transport delay.
  Negative values are preserved. It is not network RTT or a latency benchmark.

Inspection output is a new diagnostic interface. The existing event schema and
quote output have not changed; prior fixtures still replay byte for byte.

## Observed feed cadence

Short live checks on the current cloud path observed snapshot gaps up to about
12.5 seconds. An independent Python WebSocket client observed the same cadence
and matching post-subscription exchange timestamps, while REST samples showed
changing books between those updates. This localizes the behavior beyond a
Rust-only decoder issue. Later five-minute combined-feed probes received fast BBO
and trade messages between sparse depth snapshots on the same mainnet socket.
That excludes a general connection/receive pause as the whole explanation; it
does not distinguish exchange publication from channel-specific path shaping.
Testnet behaved differently and cannot calibrate mainnet latency.

See `status.md` for evidence and
[the accepted feed-profile contract](decisions/0002-feed-profiles.md) before using
these channels for time-sensitive strategies. Keep separate depth/BBO freshness;
a fresh BBO must not refresh stale depth. Omitting `--feed-profile` retains the
schema-1 depth-only contract. Explicit depth, BBO and combined profiles use schema
2; see [feed profiles](feed-profiles.md) for flags, output and per-channel metrics.

## Audit a completed supervisor archive

```sh
./scripts/dev run --locked -- audit-supervision --input data/supervision-001 \
  > data/supervision-001.audit.json
```

Run this after supervisor shutdown and keep its output outside the root. The audit
rehashes recordings and executable, replays output, and recomputes lifecycle,
quota and resource evidence. Check both operating status and
`full_window_completed`: verified integrity alone does not mean healthy operation.
See [the audit contract](auditing.md). Missing final summaries require per-child
inspection/recovery, not changing metadata to imply completion.

## Before a 24-hour run

Checksummed rotation, whole-session limits and bounded process supervision are
implemented. Local fault tests exercise restart/reconnect, SIGKILL recovery,
graceful shutdown, orphan prevention, watchdog and integrity-failure behavior.
See [the supervisor runbook](supervision.md). A native launcher and offline-verified
service candidate are available in [deployment.md](deployment.md). Next is the
actual 24-hour gate, target-host service/reboot ownership and a cross-session
archive/retention plan. The [controlled experiment](reliability-experiment.md) has
started; [status.md](status.md) records its path and current completion status.
The bounded live checks do not establish unattended
24-hour reliability. No 24-hour run should be marked complete without its actual
capture, resource measurements and fault-recovery results.
