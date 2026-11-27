# R003: a prospective reversal pilot with bounded residual exits

Status: version-1 specification frozen before R003 implementation, new collection
or economic results, 28 November 2026 PKT. Experiment `r003-cost-reversion-001`,
signal `btc-bbo-cost-reversion-003`, exit policy `r003-bounded-residual-exit-001`.
The [policy constants](r003-cost-reversion-policy.json) are part of this contract.
There is no R003 runner, capture command or result yet. This change adds no orders,
runtime behavior, native schema or cloud-environment configuration.

## Hypothesis and separate evidence stages

The [R002 diagnostic](mac-r002-diagnostic-results.md) reports twelve negative
baseline closes, nine negative decision-midpoint benchmarks, a censored recording
boundary and incomplete exits. R003's reversal hypothesis is explicitly a design
choice made after those explored results. Reversing R002's reported gains/losses
would not produce a valid strategy: direction changes the touch, liquidity,
native fills, fees, risk and subsequent exit decisions.

Test whether a sufficiently large past 30-second BTC move reverses over the next
120 seconds enough to cover the declared taker-model costs. Keep one continuation
control with the same selected feature, 120-second hold and new exit rules.
This comparison isolates the two declared policies under the same research setup;
it cannot attribute a difference solely to signal direction when fills differ.
R001/R002 outcomes and their older horizons remain separate historical results.

First implement and verify lifecycle/selection/accounting using synthetic sources
and, if useful, the already explored archive. Those are software evidence only;
no old-data economic result can pass R003. Then freeze the tested producer/binary/
assets and a prospective capture intent before collecting a single new event.
Exactly one fixed new cohort supplies this feasibility pilot. Any positive result
can propose only an independently declared later confirmation cohort, never live
execution. A negative or sparse result is retained without parameter search.

## New dataset and stopping rule

Predeclare 64 numbered attempt slots, each requesting 300 seconds of BTC mainnet
public combined-feed capture. There are 5 hours 20 minutes of requested recording,
which may be collected in batches of at most twelve attempts (one hour of requested
recording). This is not a requirement for uninterrupted collection. Pause/resume
only the unstarted slots of the same bound manifest, with the same producer and
specification. A new manifest, restarted numbering or code change is a new cohort,
not a continuation of this pilot. The collection calendar ends seven days after
the first manifest is created. At expiry, unstarted slots become not run.

A completed capture requires exit code zero, a natively finalized source ending
with `duration_elapsed`, and a recorded source span of at least 300 seconds.
Finalization alone does not prove the requested capture window completed.

Persist and fsync each attempt's intent before spawning capture; failed spawn or
interruption consumes that slot. Retain files, errors, requested/observed durations,
start/end receipts, finalization and source identity. A 330-second wall timeout
bounds each child. Reconnects within a capture remain recorded events in that
attempt. There are no replacement attempts, repeated cohorts or extensions to
reach a signal count, favourable market regime or profit. Resume never overwrites
an existing attempt. Capture intent binds this protocol/policy and the software
freeze commit, installed binary, helpers, source policy and planned 300 seconds.
No strategy outcome readouts run until all 64 slots are terminal; capture health
and recorded prices may be monitored, and operator exposure is disclosed.

All 64 slots stay in every denominator. Freeze chronological thirds by planned
IDs: 1–21, 22–42, 43–64. Do not renumber failures or use old quality development/
validation/test membership. The new R003 manifest has its own versioned namespace.
Old recordings, old recovered prefixes and the 120-second feed check cannot be
substituted. Batch pauses, outages and calendar exclusions remain explicit.
The attempt count does not guarantee thirty signals, closes or statistical power.
If coverage/sample gates fail, stop with that result; further work needs a new plan.

Read-only native integrity/storage audit and independent BBO normalization bind
every retained source. Preserve all events and failed/unavailable slots. A valid
short finalized journal may still expose causal entries and ending inventory;
short duration cannot erase them. An unreadable/corrupt/unsealed input that cannot
be independently verified is unavailable/invalid, not repaired into a profitable
sample. Native data failures invalidate economic admission; capture or budget
shortfalls prevent a complete result. No collection-wide 24-hour gate is claimed.

## Prefix-only feature and direction

Use exact rational/Decimal arithmetic and R002's unchanged *feature definition*,
implemented in separate R003 producers. Anchor five-second bins to the first raw
source timestamp; consider bins from +30 seconds. The first native-accepted,
positive-size bid/ask with `0 < bid < ask`, acknowledged fresh BBO and unique
exchange timestamp per connection is that bin's sole candidate. Missing history
or an abstention cannot select a replacement from the same bin.

For candidate time `t`, use the first eligible BBO in receive order within inclusive
`[t-30s, t-29.75s]` as historical reference. Require the same connection, boundary
quote ages at most 250 ms and accepted unique-BBO gaps at most 1,000 ms throughout
the history. Observed BBO unusability, reconnect or a receive-wall discontinuity
of at least 1,000 ms breaks history; monotonic regression is a source failure.
Depth does not refresh BBO; no interpolation or cross-attempt clock concatenation.

```text
M = (bid + ask) / 2
past_move_bps = 10000 * (M - historical_mid) / historical_mid
spread_bps = 10000 * (ask - bid) / M
hurdle_bps = spread_bps + 10 fee bps + 2 slippage bps + 2 buffer bps
```

When `past_move_bps >= hurdle_bps`, primary reversion sells and the continuation
control buys. At `past_move_bps <= -hurdle_bps`, reversion buys and control sells.
Equality qualifies; otherwise abstain. The hurdle is a past-move filter, not an
expected return or extra accounting charge. No imbalance confirmation, fitted
threshold, alternate horizon, instrument search or outcome-based feature filter
is included. Both arms and all profiles use the same first qualifying candidate
that also passes the announced time-budget rule below. Persist raw/native prices,
sizes, reference, exact fractions, source prefix and selected feature before any
label or fill. Reject/no fill/missing label never selects another entry.

## Announced time budget and source boundaries

Let `t0` be the attempt's first source monotonic timestamp. The pre-capture intent
announces a 300-second case budget, so scheduled end is `t0 + 300s`. This is known
at case initialization, independent of actual EOF. An entry at `t` requires:

```text
t + 120s hold + 10s exit window + 1s terminal reserve <= t0 + 300s
```

The inclusive latest entry offset is therefore +169 seconds. The budget allows
a candidate at +169s; one nanosecond later fails that gate, even if
the later recording runs longer. Persist budget-gated candidates and empty bins
separately from price abstentions and missing history. Never derive a cutoff from
the actual recorded end or drop R002 child 2 retrospectively. If required intent
is missing, do not invent it from a summary written after capture.

Stop entry candidate search at the announced cutoff, retaining the last considered
bin and the first source event at/after that boundary, if observed. Later entry
bins are explicitly outside the planned budget, not a new feature search over the
rest of the file. A quote beyond the cutoff cannot replace an earlier candidate.

Unexpected early EOF retains every already-selected entry and its own fills,
pending state and inventory. If no feature was selected and the full planned
entry window was not observed, report censored selection rather than a completed
no-signal search. A verified completed search may report no signal. There is no
position carry across recordings, no invented common monotonic clock, no timer
beyond observed EOF and no forced closing quote. These independent offline cases
do not implement a persistent trading account: open exposure blocks advancement.
Continuous inventory/recovery across rotations remains separate production work.

## Native-owned execution and bounded closing

Each attempt/arm/profile starts independently flat. Target 0.001 BTC, collateral
10,000 USDC, maximum absolute position 0.001 BTC, order notional 100 USDC, one
working order and loss halt 10 USDC. Reject oversized orders without resizing.
At each request, a buy limit is the current ask times `1.0002`; a sell limit is
the current bid times `0.9998`. Keep the six existing fee/delay/liquidity/slippage
profiles byte-for-value in the JSON. An arm has its own native ledger and assumed
capacity; the opposite control is a separate counterfactual, not a shared account.

Reuse the existing native manual-simulation schema/known-book-at-arrival model
through separate R003 orchestration. Its reference freshness remains 2,000 ms;
feature/close-decision freshness is the separately declared 250-ms research rule.
Keep source-before-equal-arrival ordering, exact native risk/fees/FIFO accounting,
original quote identity and conservative shared capacity. Actual execution is
unknown; the six assumptions are sensitivity controls, not calibration.

At `feature time + 120s`, activate a close window ending at `feature + 130s`.
Each request must be no later than that deadline minus the *maximum profile*
latency of 250 ms, so any declared arrival fits the common window. Within actual
source events, take the first fresh newly accepted unique BBO satisfying:

1. Its native source prefix has an entry and all previous orders terminal, with
   no working order, pending entry or cancellation. If the settled entry did not
   fill or the position is already flat, record that outcome without an exit.
2. Native risk is not halted and the settled residual is nonzero. Request the
   exact absolute residual on the opposite side, using that quote's fixed 2-bps
   envelope. Persist intent and its complete native control prefix first.
3. At most four closes, IDs `close-1` through `close-4`, may be requested. After
   each terminal close, only the first subsequent eligible new BBO may request
   another, with at least 250 ms between close requests and a different
   `(connection_id, exchange_time_ms)` from every earlier close request. A newly
   acknowledged fresh connection within the same recording may provide an exit.

Pending entry/order settlement may become known at a later source event inside
the window; it cannot be anticipated or overlapped. Risk halts prevent requests.
New requests refresh the price anchor from their own observed quote without
widening the 2-bps envelope. Never replenish consumed same-quote capacity, reverse
inventory, exceed original entry quantity or claim a cancelled IOC fully filled.
The four-request bound is a new post-R002 design choice, not a guarantee of flat
inventory or a result selected by replaying the old partial exits.

Stop requesting at flat inventory, risk halt, four closes, deadline or actual EOF.
Preserve terminal/rejection reason, reference/limit/assumed price, capacity, all
fees, exact remaining position and pending IDs. Distinguish attempts exhausted,
window exhausted, unobserved deadline, no eligible quote and source censorship.
No additional close, wider limit, EOF liquidation or manual repair is permitted.
Nonzero inventory or pending orders keep closed P&L unavailable. No fill and no
signal are distinct from the separately defined idle reference.

An optional diagnostic uses the first new same-connection accepted quote in
`[t+120s, t+120.25s]`, with history/label unique-BBO gaps at most 1,000 ms. Missing
labels stay missing and do not filter entry, execution, pair coverage or economics.
Use that same future quote for both arms. Signed midpoint change is
`entry_side_sign * 10000 * (future_mid - current_mid) / current_mid`, where buy
has sign +1 and sell -1. An unchanged midpoint is not a directional hit. This
quantity is a prediction diagnostic without fill-quantity weighting or costs,
separate from native conditional net and its actual assumed filled quantities.

## Coverage, exact economics and the fixed decision rule

Each planned attempt has two arm slots and six profiles: **64 × 2 × 6 = 768**.
Keep all no-signal, censored, failed, not-run, no-fill and open slots. Full arm/
profile net requires complete verified coverage, no unobserved/unavailable case,
no exposure/pending order and at least one filled, closed cycle. Apply exact
price/arrival/spread/slippage/fee identities to native closes, charging costs once.
Open cases keep known per-fill costs but have no closed decomposition.

Report each arm/profile separately and the defined idle reference (zero requests,
fees, position and trading P&L). Pair only the same attempt and profile: primary
closed net minus control closed net. Both original cases must be verified, filled
and flat with no pending order for that delta. Missing pairs remain unavailable
in the full denominator, not zero or a profitable-subset comparison. Fills/sizes
may differ, so this is a conditional policy comparison, not a pure price-sign
effect. No arm/profile P&L pooling, annualization or significance claim is allowed.

A complete baseline paired total requires a complete pair for **every selected
feature**. A no-fill baseline arm leaves that selected feature's pair unavailable,
even if both standalone profiles otherwise have complete totals. It therefore
blocks advancement rather than being omitted from the paired total. Completed
no-signal slots supply coverage but have no fabricated zero-P&L pair and do not
count toward the minimum thirty pairs.

Require primary baseline, delay, liquidity and slippage stress, plus the baseline
continuation control. Lower/zero-fee controls cannot pass a primary gate. Apply
these classes in order:

1. Changed/corrupt source, software/specification drift, causal/native/financial
   verification failure: **invalid**, with no admitted economics.
2. Incomplete collection, unavailable/not-run/censored required cases, open
   inventory or pending orders in any required profile/control, or any selected
   feature without a complete baseline pair: **incomplete**.
3. Fewer than 30 closes in any required primary profile, fewer than ten primary
   baseline closes per fixed third, fewer than 30 complete baseline pairs or ten
   pairs per third: **insufficient_data**.
4. Primary baseline net at or below zero overall or in any fixed third:
   **no_positive_pilot_evidence**.
5. A required primary stress net at or below zero: **cost_sensitive_candidate**.
6. Complete baseline paired difference at or below zero overall or in any third:
   **not_better_than_paired_control**.
7. Otherwise: **candidate_for_independent_new_block_confirmation_only**.

Thirty/ten are predeclared feasibility screens, not statistical-power calculations.
Each of classes 1–6 stops advancement; class 7 requests a separately frozen new
confirmation cohort, not a trading gate. Do not extend/replace this pilot or
change constants after its outcome. Any revised hypothesis gets a new ID and
retains this attempt. Profitability and sufficient signal count are not promised.

## Resource bounds and implementation acceptance

Reuse the installed image and native schemas; add separate R003 helpers, manifests,
reports and launcher commands only after implementation. Bind every new capture
intent, protocol/policy, installed executable, producer/assets and source before/
after. Execute only the installed verified native binary, never one inside a
supplied bundle. Collection may use public networking; all economic replay is
offline with read-only evidence mounts, ordinary-user limits and a separate output.
The policy pins the original Mac native binary SHA-256. Record the Mac's actual
image ID at manifest creation and require it unchanged; a cloud test image's ID
must not be substituted for the user's image. Host/synthetic test binaries are
separately labelled and cannot supply the prospective economic pilot.

Bounds are fixed in JSON: 64 attempts, 768 cases, five requests per case, 64 bins
per attempt, 9,900 source records, native paper 10,000 records and 193 checkpoints
per ledger; 32-MiB source per attempt, 16-GiB input/output, 1-GiB free reserve,
32-MiB report reserve, 128-MiB source and 384-MiB case admission. Replay suite
3,600 seconds, native calls 30 seconds, outer timeout 3,660 seconds. Capture has
its separate wall/calendar budgets. A bound hit preserves all slots and incomplete
full totals without truncation, replacement or reading a profitable subset.

Before any new economic data, require hand-computed up/down/abstention, budget
and exact-price boundaries; future-price/EOF/fill independence; equal-time,
duplicate, gap, reconnect/clock and no-signal/censored cases; shared feature hashes
across both arms/profiles; native partial/pending/rejected entry and all four exit
stages; capacity exhaustion, risk halts, pending cancellation, deadlines/early EOF;
full causal prefix/intent immutability and exact finance; pair/third denominators
and every decision class; manifest resume/no replacement/calendar expiry; resource
and mutation failures; ordinary-user repeated runs in the unchanged image and
offline desktop/mobile HTML/JSON. Native record/checkpoint limits stay enabled.
Synthetic/software proofs are labelled separately from the future pilot.

Current acceptance is the specification and policy consistency review only. Next
build the offline runner and capture-manifest machinery, complete those checks,
then issue a tested Mac command. No Mac action or new collection is needed now.
