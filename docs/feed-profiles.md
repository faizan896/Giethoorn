# Explicit feed profiles and freshness

Omitting `--feed-profile` keeps the schema-1 depth-only recorder and its exact
quote output. Explicit `depth`, `bbo` or `combined` profiles select schema 2. The
profile is recorded; readers never infer it from messages or guess unknown versions.

## Capture and replay

```sh
./scripts/dev run --locked -- collect --coin BTC --network mainnet \
  --feed-profile combined --duration-secs 120 \
  --depth-stale-after-ms 15000 --bbo-stale-after-ms 2000 \
  --feed-timer-ms 250 --output-dir data/combined-001 \
  > data/combined-001.live.jsonl
./scripts/dev run --locked -- replay --input data/combined-001 \
  > data/combined-001.replayed.jsonl
cmp data/combined-001.live.jsonl data/combined-001.replayed.jsonl
./scripts/dev run --locked -- inspect --input data/combined-001
```

Use new paths. `capture`, `collect` and `supervise` accept the same profile/timing
flags. `--stale-after-secs` belongs to the legacy contract and conflicts with an
explicit profile. Profile-specific timing flags require a profile.

The example values are defaults, not calibrated risk parameters. Timing must be
positive and fit u64 nanoseconds. The timer interval is at most 250 ms and no
larger than any selected channel threshold. I/O scheduling and durable-write
backpressure can delay observation; this is not a real-time deadline guarantee.

## Version and output contract

A schema-2 session starts with `feed_session_started`, including the exact policy.
All subsequent records use schema 2. Container version 1 retains its existing
layout/checksum algorithm and explicitly declares event schema 1 or 2; readers
reject record/header disagreement. Existing version-1 fixtures still replay to
the same exact bytes. Unsupported and mixed event versions fail.

Schema-2 output has `normalization_version: 2` and `kind: depth`, `bbo` or
`freshness`. It includes record/connection identity, receive timestamps, coin and
the state of each selected feed. Market observations carry their own exact-decimal
`quote`; freshness-only observations carry no quote. Disabled feed states are null.
Depth and BBO can disagree because their observations arrive asynchronously.

Each feed state contains its ACK flag, status, threshold and latest observation's
sequence, exchange timestamp and recorded age. `all_required_fresh` is true only
when every selected channel is acknowledged and has current two-sided data.
Consumers must explicitly select which channels they require; faster BBO must not
refresh depth or imply a coherent full order book or maker fill.

| Status | Recorded meaning |
| --- | --- |
| `disconnected` | No valid active connection/state; latest live identity is cleared |
| `awaiting_acknowledgement` | Selected subscription has no matching ACK yet |
| `awaiting_data` | ACK received, but no accepted observation yet |
| `fresh` | Acknowledged two-sided data is younger than its threshold |
| `empty` | Latest accepted update has a missing side, within the usable-data deadline |
| `stale` | Deadline reached; includes absent ACKs/data and prolonged empty data |

Age describes the latest accepted update, including empty sides. The watchdog
deadline uses the last two-sided update, or connection-open time if none exists.
Before ACK it uses connection-open time, so unacknowledged data cannot perpetually
extend that deadline. Equality with the threshold is stale. Older source timestamps
are ignored independently for each feed; equal times retain receive order.

The I/O layer persists `feed_timer` records before applying elapsed-time changes.
The engine also observes recorded receive order and timestamps. A timer can emit a
freshness transition without incoming messages. No live clock enters replay.
Any required feed reaching its deadline triggers bounded reconnect; other active
channels and pongs do not suppress it. Reconnect clears both active feeds and ACKs.

## Reports and inspection

For schema 2, session `last_quote` is null; each feed has a separately labeled
historical `last_observation`. `feeds.current` describes the final recorded state,
usually disconnected after normal shutdown. Neither historical quotes nor an
offline inspection establish current freshness.

`all_required_fresh_observed` means all selected feeds were simultaneously fresh
at least once in the session. It is a data-usability check, not trading readiness
or continuous coverage. Successful capture requires it; complete failed recordings
still have `end_reason: failed` and a nonzero capture exit.

Inspection provides per-feed counts, within-connection gaps, initial waits, final
ages and source-clock deltas. Aggregate snapshot counts include both feeds;
aggregate maximum gap is the largest per-feed gap, and final age is the largest
observed per-feed age. Thus fast quote traffic cannot hide an old depth update.
Clock deltas are receive wall time minus exchange time, not RTT.

Freshness describes locally observed data age. It cannot prove recent exchange
generation, synchronized clocks or complete delivery. Receipt is timestamped before
durable processing; publication/backpressure delay is not an HFT latency guarantee.

The Rust replay callback now receives `Observation`, a legacy quote or explicit
version-2 observation. `Observation::quote()` accesses market observations;
`Observation::source()` identifies version-2 sources. Default serialized CLI output
is unchanged; this is an intentional library API change in the unpublished 0.1.0.

The combined fixture is synthetic and exercises independent stalls, equal/older
timestamps, missing sides and reconnect resets. Live acceptance and its limits are
recorded in [status.md](status.md).
