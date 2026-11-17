# First costed execution probe

Status: specification only; the policy compiler/runner is not implemented.
Existing version-3 fixed IOC replay and its independent cost/ledger checks are
available. The [R001 results](r001-results.md) are conditional price predictions,
not a costed strategy result. All original partitions are now explored; this
next experiment is exploratory on that data. Later confirmation needs new frozen
recordings after the execution policy is locked.

## Small acceptance suite before broader evaluation

Use the earliest four development candidates in the frozen capture order, without
selecting by signal outcome. Allow one entry/exit cycle per child: choose the
first directional R001 feature at least five seconds after that child's start.
An abstention is not an entry; after selecting a directional feature, a rejected
or unfilled attempt must not be replaced with a later, better-looking signal.
Keep other children not-run and every selected attempt visible.

The suite tests mechanics and cost sensitivity, not whole-strategy profitability.
Do not select only signals with available future prediction labels. Prospective
entry eligibility uses information available at the feature only. Missing future
data must remain part of exposure/outcome accounting after an entry attempt.

## Proposed paper assumptions

Starting paper collateral is 10,000 USDC, target quantity 0.001 BTC, order notional
cap 100 USDC, maximum absolute position 0.001 BTC, maximum one working order and
loss halt 10 USDC. These are test assumptions, not funded sizing or calibrated
venue limits. An order exceeding a cap is rejected rather than silently resized.
Use a two-basis-point protective limit envelope around the currently observed
opposite touch; no future price chooses the limit.

| Profile | Fee per side, bps | Adverse slippage per side, bps | Top-size fraction | Arrival delay, ms | Quote wait, ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 5 | 1 | 0.25 | 100 | 250 |
| Lower-fee assumption | 1 | 1 | 0.25 | 100 | 250 |
| Zero-fee control | 0 | 1 | 0.25 | 100 | 250 |
| Delay stress | 5 | 1 | 0.25 | 250 | 250 |
| Liquidity stress | 5 | 1 | 0.10 | 100 | 250 |
| Slippage stress | 5 | 2 | 0.25 | 100 | 250 |

Four children by six profiles gives 24 bounded cases. None of these rates,
liquidity fractions or delays are measured venue/account parameters. Preserve
the existing native model's source/derived bounds and a finite suite/output
budget, retaining failed/not-run cases if admission ends.

## Causal close quantity is mandatory

Request entry in the predicted direction using the existing causal IOC model.
The close decision is the first recorded event at/after feature time plus one
second with usable BBO and no more than 250 ms of quote age. Do not insert an
operational clock/ACK/fill into a missing recorded interval. Report late decisions.
Close only the actual position already known at that decision, with the opposite
side and no reversal. An unfilled entry does not create an exit trade.

The existing native engine accepts fixed scenarios, not an adaptive policy. A
compiler may materialize the two-order case using an entry-only control replay,
but must read only fills/state at or before the close-decision sequence. Keep
that control, its prefix boundary and the compiled scenario. Prove future-price
independence and that adding the close leaves the entry prefix unchanged. An
actual entry fill quantity inferred later in the recording cannot size an earlier
close. Otherwise a separate policy adapter is required; do not silently change
native version-3 semantics.

Exit quantity can differ across profiles because entry fills differ. Compare a
fixed policy fingerprint with explicit path/exposure changes rather than claiming
the existing batch runner's fixed-order-plan contract still holds. Keep the
existing ledger/risk guards. A close can be rejected, partially filled, pending
or unresolved; do not bypass a guard or fabricate flattening. New entry attempts
stop after a loss halt or unresolved exposure.

## Outputs and required checks

Retain original input and policy/profile fingerprints, the selected source
feature, control replay, causal prefix, compiled requests and every execution
trace. Independently verify fees, spread/slippage decomposition, fills and exact
ledger algebra using the existing native/Decimal checks. Spread/slippage already
embedded in fill prices must not be charged again.

Report entry/exit completion, quantities, fees, closed-case P&L, historical-mark
open exposure, pending orders, rejects and late/missing decisions separately.
Never infer a net return for unknown outcomes or drop unresolved cases from a
success denominator. Each child is an independent flat-start probe, explicitly
not a continuous portfolio; there is no aggregated portfolio profit or annualized
performance claim. Venue increments/minimums and actual execution calibration
remain outside the existing model and must stay visible.

Acceptance needs hand-calculated full/partial/no-fill cases, no over-close after
partial entry, missing-data/source-end exposure, expiry and risk rejection,
reproducibility, source preservation and future independence. The raw fee-hurdle
worksheet cannot substitute for these execution checks.
