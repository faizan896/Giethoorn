# Decision: causal R001 IOC policy compilation, cost probe version 1

Status: implemented for bounded offline exploratory mechanics and cost testing.
No native event, paper, recording or normalization schema is changed. Paper v3
continues to execute fixed scenarios with its existing exact financial and risk
semantics. Live strategy/order integration remains absent.

## Policy instead of a fixed order list

The direction-score study does not account for execution. Subtracting fees from
its labelled-subset mean would discard missing outcomes and cannot model actual
inventory. A fixed full-size exit after a partial/no-fill entry could reverse
the position. The Python cost-policy compiler therefore uses an entry-only
control plus a second replay with a causally sized close.

The policy is version 1, `r001-ioc-probe-001`. Its canonical policy/profile/limit
fingerprint is distinct from the raw fingerprint of each compiled scenario.
Select up to four earliest frozen development candidates, once, before outcomes;
select their first directional R001 feature after five seconds. Do not require a
future prediction label. One cycle per recording/profile prevents replacement
attempts and new entries after unresolved exposure or a halt. Each case starts
flat independently; it is not a continuous portfolio.

The first usable recorded BBO state at/after feature time plus one second is the
close decision; quote age must be at most 250 ms and native market state fresh.
Missing intervals insert no clock events. A late decision is explicit. The
control's actual fills and position at or before this sequence size the opposite
request. Pending entry state at this boundary is refused rather than guessed.
The original IOC arrival-plus-wait is shorter than the close horizon, so an
observed decision event should have resolved/expired the entry first.

## Causal proof and accounting

Persist the original feature, entry-only scenario/replay, decision boundary,
prefix receipt and compiled scenario before processing the second replay. Compare
every prefix account/risk/event/order transition, link and execution receipt up
to the close request. Only the frame's scenario hash is removed, because adding
an order necessarily changes that hash. The recording fingerprint, financial
state and all original references remain bound. Any mismatch refuses the case.
Tests change future prices after the decision and require identical requests.

No-fill/rejected entry produces no exit; missing decision leaves inventory open.
A partial entry sizes a smaller close. The native risk ledger can still reject
that close, and IOC liquidity/limits can leave it partial/pending. Never bypass
risk or fabricate flattening. Fee, price/size/timing and ledger checks reuse the
independent Decimal verifier and exact native paper replay.

Report version 1 retains closed, unresolved, rejected, no-fill, no-signal, failed
and not-run cases separately. Closed-case P&L is available only after a filled
entry ends flat without pending orders. Open exposure has a historical mark,
never an inferred closed return. Cost components already embedded in fill prices
are not subtracted again. Baseline comparisons expose changed entry/close size
and execution paths. Their invariant is the policy, not the existing fixed-plan
batch runner's order-list fingerprint.

## Admission and limits

Use the stopped source's shared lock and the frozen study's exact quality/auditor
fingerprints. Repeat native audit and quality verification before execution and
match each copied session to the original inventory. Pin the executable; recheck
source, frozen quality, binary, code and assets after the suite. Changed evidence
invalidates all admitted metrics while retaining diagnostic artifacts.

At most 24 cases, 900-second suite deadline, 30 seconds per native call, 2-GiB
output budget, 1-GiB free-space reserve and conservative 256-MiB case admission
remain fixed. Preserve native 16-MiB recording, 10,000-event, derived-byte and
exact-decimal bounds. Oversized/failed/unadmitted selected cases are not replaced.
The Mac wrapper reuses the existing image with read-only source/helpers, no
network, existing resource limits and a 960-second outer timeout.

The [policy specification](../cost-study-plan.md) fixes all rates and test sizing.
They are illustrative, not venue calibration. Fresh frozen data is needed for
later confirmation after new policy choices. This experiment does not clear the
24-hour operational gate, statistical/economic validity or live-order readiness.
