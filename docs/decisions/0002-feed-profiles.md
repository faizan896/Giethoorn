# Decision: explicit feed profiles and normalization version 2

Status: accepted and implemented locally after measured diagnosis. Explicit
schema-2 depth, BBO and combined profiles are available. Legacy schema-1 capture
and output remain the default. No trading strategy or deployment is included.

## Evidence

Five-minute probes subscribed to `l2Book`, `bbo` and `trades` for BTC on one
WebSocket connection per network. Both used the independent Python
`websocket-client==1.9.0`, inherited proxy routing and verified TLS.

| Network / channel | Messages | Maximum receive gap |
| --- | ---: | ---: |
| Mainnet l2Book | 25 | 12.565 s |
| Mainnet bbo | 3,445 | 0.563 s |
| Mainnet trades | 1,259 (4,900 trades) | 1.780 s |
| Testnet l2Book | 59 | 5.736 s |
| Testnet bbo | 286 | 10.247 s |
| Testnet trades | 86 (270 trades) | 17.669 s |

The mainnet connection delivered fast BBO/trade messages between depth snapshots.
This excludes a *general* receive-loop/TLS/connection pause as the explanation for
the whole gap; it does not distinguish exchange-side depth publication from
channel-specific shaping elsewhere on the route. Testnet has different cadence
and activity and is not a mainnet latency calibration.

The software also consumed a real local WebSocket burst of 1,000 snapshots under
synchronized-write backpressure and rotation, with exact replay and no missing
observations. This is functional load evidence, not an HFT benchmark or proof
of complete venue delivery.

Source-clock deltas include clock offset, exchange batching and transport delay.
They are not RTT. Raw probes and their source are retained under the paths in
`status.md`; they are diagnostic files, not schema-1 journals.

## Accepted contract

Keep existing captures and normalization unchanged. Use a versioned profile
for depth-only, BBO-only and combined observations, with explicit feed identity:

1. A new session/normalization version records its profile and freshness policy.
   Readers route version 1 through the existing engine and retain its exact golden
   output. Unsupported versions fail rather than partially processing a session.
2. BBO state and depth snapshots are distinct. A fresh BBO must not overwrite an
   old depth snapshot or make stale depth look fresh. Each has its own source time,
   local sequence, connection identity and freshness status.
3. New observation output identifies source/kind. A depth/BBO disagreement can
   reflect asynchronous updates and must not silently be rewritten into a
   supposedly consistent full order book.
4. Freshness decisions consume recorded timer events and receive ordering, not
   calls to the live clock inside the engine. Reconnect clears both feed states.
5. Record raw subscriptions/messages and acknowledgements. A socket or pong alone
   does not establish that each required channel is delivering usable data.
6. Preserve exact decimals, independent timestamp regression checks and explicit
   empty sides. Never infer queue position or maker fills from BBO observations.

Raising the depth stall threshold to conceal slow data is not a substitute for
this distinction. Aggressive REST polling is also not a default fix: its costs,
limits, ordering and freshness need their own measured contract.

## Acceptance before strategy work

- Mixed-feed, equal-time, out-of-order and reconnect fixtures replay identically.
- A stalled depth stream stays stale while BBO is fresh, and vice versa.
- Legacy schema-1 captures still emit byte-identical output.
- Real combined captures demonstrate measured channel cadence without treating
  source-clock delta as network latency or completeness evidence.
- Risk consumers explicitly select which fresh state they require.

The implementation uses `feed_session_started` and `feed_timer` events in schema
2, with explicit `depth`, `bbo` and `freshness` observations. Subscription ACKs and
usable data are required independently for each selected channel. Missing ACKs or
empty updates cannot indefinitely extend the channel watchdog. Reconnect clears
active state and per-channel timestamp ordering; historical reports remain labeled.

Container version 1 is unchanged; its declared event schema is now enforced for
every sealed record before output, plus the recovery tail during replay. Mixed or
unsupported schemas fail. The version-1 golden fixture and historical live archives
remain compatible. See [the profile contract](../feed-profiles.md) for exact CLI,
output and freshness semantics, and [status](../status.md) for measured acceptance.
