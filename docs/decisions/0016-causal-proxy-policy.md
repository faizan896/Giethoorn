# Decision: causal known-book proxy policy version 1

Status: implemented and accepted following the predeclared
[causal policy protocol](../causal-proxy-policy-plan.md). New namespaces are
`causal_proxy_policy_version: 1`, `policy_report_version: 1` and
`close_compilation_version: 1`, with policy ID `r001-known-book-causal-001`.
Existing native schemas/binary, signal, proxy compiler/verifier, fixed comparison,
cost policy and historical artifacts remain unchanged.

## Entry control and own-position close

Read the same preserved cost cohort and six profiles, revalidate its source/
quality/policy/producer and exact original native ledgers, and reproduce the
original entry-only scenario. Run that entry through the unchanged known-book
proxy as a separately retained manual-simulation control.

Reuse the original source-based close-decision rule: first usable observed event
at/after the fixed one-second horizon with a same-connection BBO no older than
250 ms. It need not be a new quote event. No source event or wall clock is
interpolated. Native prefix state includes source through that exact sequence
and queued actions already resolved by the decision time, including equal-time
arrivals that precede a request there. Exclude later source sequences even when
their timestamps match, and later scheduled actions using the same source prefix.

Read the control's native position, working-order state and risk at that prefix.
A pending entry means no close; zero position means no close. A settled nonzero
position must match entry direction and not exceed the fixed target/entry size.
Compile one opposite-side close for that own quantity, with the original limit
rule applied only to the decision's known quote. Preserve all other scenario
fields and the exact entry. No original-model close quantity is imported.

Run the new plan with the unchanged manual proxy. Its complete input/link/update
prefix before the close request must match the control prefix exactly, and the
receipt binds its state/count/hash. Verify close quantity, side, anchor and limit
from native prefix state independently of the compiler's chosen order. Existing
proxy source/Decimal/ledger checks remain required for both control and final.

## Missing, partial and rejected outcomes

No decision before EOF leaves the entry-only plan. Pending/partial entries,
partial closes, stale/missing arrival references, loss/risk rejection and pending
exit retain their actual simulated state. Native risk remains authoritative:
no halt bypass, reduce-only invention, forced flattening, replacement order or
later resizing. No fill or unresolved exposure has unavailable closed P&L,
not a fabricated zero return. Reuse the control when no new close is compiled.

The source origin remains captured public data or a clearly labelled synthetic
fixture; every order/fill/ACK in the proxy ledger remains manual simulation.
Actual venue execution stays unknown. This is an exploratory causal policy
experiment on already exposed data, not a pristine holdout or evidence that the
known-book assumptions are calibrated. Do not overwrite prior losing results.

## Admission and acceptance

Use explicit read-only cost input, private create-new output and no network.
Bind input, helpers/assets and native executable before/after; changes invalidate
all policy metrics. Preserve failed/not-run cases without replacement. Limits
remain 24 cases/two requests, existing native source/paper bounds, 2-GiB output,
1-GiB free reserve, 900-second suite and 30-second native calls. Admit control
and final work before starting and preserve failed child diagnostics.

Acceptance must exercise full/partial/no entry, own-position quantity, exact
costs, future prices/control fills, same-time source/arrival boundaries, no close
without position, missing decision, pending entry/exit, partial exit and native
loss/risk halt. Test source/producer corruption, prefix mismatch, admission
refusal, old-artifact preservation and portable offline desktop/mobile views.
Separate software samples from subsequent actual Mac policy results. The full-day
gate, actual execution calibration and later frozen-data economic confirmation
remain open.

All 315 Python tests, two ordinary-user Docker trials and offline desktop/mobile
browser checks pass. The 19 new native policy cases cover the declared causal,
quantity, accounting and unresolved-state boundaries. Exact repeated artifacts
and unchanged original assets are recorded in
`data/causal-policy-acceptance-vtgegra5/native-release.json`.
The [actual supplied Mac policy readout](../mac-causal-policy-results.md) is now
accepted, with 24 conditional closes, all negative. Its private native receipts
were not independently replayed here. See the [operator guide](../causal-proxy-policy.md).
