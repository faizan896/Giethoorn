# R002: fixed 30-second momentum with a cost screen

Status: frozen specification before R002 implementation or results, 22 November
2026 PKT. Signal ID: `btc-bbo-cost-momentum-002`. Experiment ID:
`r002-cost-momentum-001`. The accompanying [policy constants](r002-cost-momentum-policy.json)
are part of this specification. R002 feature, policy and report namespaces start
at version 1. Implementation and evaluation are pending; there is no R002 command.

## Hypothesis and limits of the screen

The [accepted R001 result](mac-bounded-exit-results.md) retains negative baseline
closes and unresolved exposure. R002 tests one different hypothesis: a past
30-second price move large relative to current assumed trading costs continues
over the next 30 seconds enough to produce positive conditional IOC results.
The threshold is a design choice after R001, not an estimated expected return,
calibrated fee quote or promise of future movement. No R002 source outcomes have
been inspected to select these constants. There is no parameter search in R002.

For a current accepted bid `B`, ask `A`, midpoint `M = (B+A)/2`, and historical
midpoint `M0`, compute using exact rational/Decimal arithmetic:

```text
past_move_bps = 10000 * (M - M0) / M0
current_spread_bps = 10000 * (A - B) / M
assumed_round_trip_cost_bps = current_spread_bps + 2*5 + 2*1
entry_hurdle_bps = assumed_round_trip_cost_bps + 2
```

The fixed baseline assumes 5 bps fees and 1 bp adverse slippage per filled leg;
the additional 2 bps is a research buffer. The hurdle is therefore current spread
plus 14 bps. Emit up when `past_move_bps >= entry_hurdle_bps`, down when
`past_move_bps <= -entry_hurdle_bps`, and otherwise abstain. Equality qualifies.
With bid 99.99/ask 100.01 the hurdle is 16 bps. A historical midpoint of 99.8
gives about +20.0401 bps and qualifies up; 100.2 gives about -19.9601 bps and
qualifies down; 99.9 gives about +10.0100 bps and abstains. These are synthetic
arithmetic examples, not market results.

Past movement does not pay a later trade's costs. Actual conditional net comes
only from subsequent native simulated fills and their fees. The estimated spread
screen is symmetric and uses the current book; future spread, prices, fees on
different notionals and incomplete fills can make realized costs different.
The hurdle is never added as another charge to the execution ledger: spread
and slippage already embedded in native fill prices are counted once.

## Frozen data and causal candidate selection

Use the original quality snapshot's entire frozen development cohort in capture
order: the supplied Mac has 79 children/474 child-profile cases. Validation and
retrospective-test children are outside this experiment. All original partitions
are already explored, so this is exploratory development, not an untouched test.
Keep no-signal, no-fill, failed, not-run and unresolved children without replacement.
Original R001 quality spans remain their own diagnostics. R002's different history
rule gets separate receipts and never rewrites the old 250-ms span policy.

Within each child, anchor five-second bins to its first source monotonic timestamp.
Consider bins beginning at +30 seconds. Choose the first native-accepted positive,
two-sided, noncrossed, acknowledged fresh BBO in each bin with a new exchange
timestamp on its recorded connection. Freeze that candidate even when its history
is missing or its move abstains; another quote in the same bin cannot replace it.
An empty bin stays missing. Keep all raw events in normalization/native replay.

For a candidate at `t`, historical reference is the first such BBO in receive order
with time in the inclusive interval `[t-30 seconds, t-29.75 seconds]`. Use no
interpolation or backward fill. Require the candidate and reference on the same
connection, quote age at each feature boundary at most 250 ms, and unique accepted
BBO gaps at most 1,000 ms throughout that history. Exact boundaries qualify.
Observed BBO unusability, disconnect/reconnect, monotonic regression or a receive
wall-clock discontinuity of at least 1,000 ms invalidates that history; depth
freshness alone does not refresh or invalidate BBO. A regressed monotonic clock
is a source failure. Retain missing-history reasons rather than relaxing a bound.

Reference lookup, gap checks and all features use only source up through `t`.
Select the first qualifying directional candidate per child for every profile.
Persist its source sequence/connection/times, raw/native bid/ask, historical
reference, exact move/spread/hurdle, source-prefix identity and selection receipt
before any forward label or profile executes. A later label, fill, rejection,
missing exit or favorable price cannot change it or select another entry.
Record considered/missing/abstaining bins up to selection or source end; these
counts are not all possible intraday signals. No R001 imbalance confirmation or
additional fitted filter is used.

## Conditional execution and missing outcomes

Each child/profile starts independently flat with one entry cycle. Buy for up and
sell for down, target 0.001 BTC, starting collateral 10,000 USDC, maximum absolute
position 0.001 BTC, order notional cap 100 USDC, one working order and 10-USDC loss
halt. Oversized orders are rejected rather than resized. Protective limits are
the observed ask times `1.0002` for a buy and bid times `0.9998` for a sell.

Retain exactly the six existing [cost profiles](cost-study-plan.md): baseline,
lower fee, zero fee, delay stress, liquidity stress and slippage stress. Their
complete constants are copied in the policy JSON. Every profile uses the same
feature and baseline hurdle; cheaper fees never admit different signals. Rates,
capacity fractions and latency are assumptions rather than venue measurements.
The fixed baseline is primary; profiles are not a search for a winning setting.

Use the unchanged known-book native/manual proxy and independent source/Decimal
cost checker. Separately versioned R002 compilers supply new timing/decisions;
old R001 helpers, protocols, templates, native schemas and binary remain unchanged.
At the first fresh, newly accepted BBO from `t+30` through `t+31` seconds inclusive,
use the complete entry-control native prefix already known then. A healthy newly
acknowledged connection within that same child may supply the close quote after a
reconnect. Flat or pending entry, risk halt or absent eligible quote means no first
close is invented or selected later. Close only the settled known residual with
opposite side and unchanged protective envelope. Record lateness and missing reason.

After a compiled first close reaches terminal native state with no working order
or pending cancellation, permit at most one extra close, `close-retry`, under the
existing [bounded-close eligibility rules](bounded-exit-plan.md). It uses the first
subsequent fresh accepted BBO and exact native residual then, without another
31-second cutoff. A native halt prevents it. A third close, widened limit, forced
fill or drain beyond actual recorded EOF is forbidden. Maximum requests per case
are entry, first close and optional extra. Preserve pending, partial and rejected
states and all fees. Ending exposure and unknown closed P&L remain explicit.

An optional prediction diagnostic labels the first new accepted BBO in
`[t+30, t+30.25 seconds]`, on the feature connection with no unique BBO gap over
1,000 ms or observed unusable interval. Report signed mid movement and all missing
labels without replacing a missing outcome with zero. This diagnostic cannot
filter entry or economic coverage and is not a trade return.

## Decision rule fixed before results

All selected cases and profiles remain visible. Report native quantities, full
fees, exposure/pending state, requests/fills/rejections, candidate availability
and exact conditional net. Show the intentionally idle no-trade reference
separately: no requests, fees or exposure and zero trading P&L by definition.
An unfilled or missing R002 trade is not relabelled as that reference.

A profile total requires every selected slot verified or explicitly no-signal,
no unavailable/not-run/unresolved case and at least one complete filled cycle.
Sum only that profile's closed cycles beside its full denominators. Keep unknown
closed P&L unavailable; never pool profiles or annualize these independent cases.
Split selected children into chronological thirds before signals: first floor(N/3),
next floor(N/3), then remainder. For 79 children these have 26/26/27 members.
Do not balance groups using the number or profitability of qualifying signals.

Apply these classifications in order:

1. Changed/corrupt evidence or failed native/causal/financial verification:
   **invalid**; economic metrics are not admitted.
2. Unavailable/not-run cases, exposure or pending orders in baseline or any of
   delay/liquidity/slippage stress: **incomplete**; no advancement.
3. Fewer than 30 closed cycles in baseline or any required stress profile, or
   fewer than ten baseline closes in any chronological third: **insufficient data**.
4. Complete baseline net at or below zero overall or in any third:
   **no positive development evidence**.
5. A complete delay/liquidity/slippage-stress net at or below zero:
   **cost-sensitive candidate**, without advancement.
6. Otherwise: **candidate for separately predeclared new-data confirmation only**.

The count/third rules are feasibility screens, not confidence intervals or a claim
that adjacent recordings are independent. Lower-fee/zero-fee results stay visible
but cannot pass these gates for the baseline. Sample insufficiency is a valid
result; thresholds/horizon/size/costs and membership stay fixed in this version.
Any later revision needs a new experiment ID and records all prior attempts.
R002 cannot complete the operational day gate, execution calibration, forward
paper, exchange/testnet reconciliation or funded-trading approval.

## Evidence, bounds and implementation acceptance

Require stopped read-only source/quality, fresh native archive audit and identical
frozen source/membership. Reuse the installed image; no new capture or build is
needed for software development. Hash source, quality, native binary, producer,
templates, this protocol and policy before/after. Output is new/private/outside
inputs, with no network and a bound external artifact inventory. Unknown actual
execution remains explicit. No compiled binary from supplied evidence is executed.

Bounds: 128 children/768 cases, 4,096 considered bins per child, 10,000 retained
history observations, three requests per case, 16-GiB output cap, 1-GiB free
reserve, 32-MiB report reserve, 128-MiB per source and 384-MiB case admission.
Existing stricter native source/paper/checkpoint/per-case bounds remain enabled.
Suite admission is 3,600 seconds, native calls 30 seconds, outer timeout 3,660
seconds. Exceeding bounds retains failed/not-run slots without truncation or
replacement. No partial suite earns complete financial totals.

Before Mac delivery, require hand-computed up/down/abstention and exact-boundary
cases; future-price, future-label and future-fill independence; bin/reference
selection; missing/stale/duplicate/reconnect/clock histories; all six identical
feature selections; source-end and partial-entry/exit behavior; exact costs and
native prefix equality before each close; all gate classifications and third
denominators; input/producer/protocol mutation and bounded offline orchestration.
Require ordinary-user repeats in the existing image and offline desktop/mobile
views with exact JSON export. Clearly distinguish synthetic/software samples
from a later actual Mac result. This specification itself implements no signal,
capture, strategy evaluation or actual order placement.
