# One bounded additional close: predeclared safety experiment

Status: protocol frozen before implementation and before new policy results.
Experiment ID: `r001-bounded-exit-002`. Proposed namespaces are
`bounded_exit_policy_version: 1` and `bounded_exit_report_version: 1`.
This follows the [accepted 13-case diagnostic](mac-development-exceptions.md).
It addresses residual inventory after a single IOC close. It is not a new alpha
signal, calibrated execution model, prospective holdout or live-trading gate.

## Frozen cohort and unchanged control

Use the original admitted quality snapshot's entire frozen development cohort
in capture order, with the same six original profiles. Refuse more than 128
children/768 cases without truncation or replacement. The supplied Mac cohort
has 79 children/474 cases. Do not select only the 13 exceptions or omit negative,
unfilled, no-signal, failed or not-run cases. All data are already explored;
the experiment is exploratory.

Keep the original R001 first-feature selection, five-second warmup, one-second
first-close rule, 0.001-BTC target, collateral, risk/loss limits, protective
two-basis-point envelope and all fee/slippage/size/latency profiles unchanged.
Reproduce the original causal one-close policy as the control. Its entry and
first-close request IDs, quantities, sides, limits and anchors must stay exact.
Each child/profile starts independently flat with one entry cycle.

## Eligibility from contemporaneous native state

Allow **at most one additional close**, request ID `close-retry`, giving a
maximum three requests per case: entry, original close and optional extra close.
This is a fixed retry cap, not a loop until flat.

Scan original source in receive order for a new native-accepted usable BBO
strictly after the original close's anchor sequence. At each candidate, use
only the control's complete native input/link/update prefix already known there,
including queued arrivals/cancellations resolved before a request at that anchor
under the existing equal-time rules. Exclude later source sequences even at
the same timestamp. Never inspect the control's EOF position to size an earlier
request or wait for a favorable future price.

Require an original compiled close that has reached native terminal state,
with no working/pending order or outstanding cancellation. A still working
first attempt cannot overlap a second request; continue scanning source until
it is contemporaneously settled. An absent original close means no extra close
is invented. A flat position means no extra close is needed.

Use the first candidate satisfying settled-order and usable-book conditions.
Its selected BBO must be acknowledged/fresh on its current recorded connection,
no older than the unchanged 250-ms decision freshness bound. Depth updates,
timers, generated replay end and interpolated events are not new retry quotes.
If native risk is halted there, record `risk_halted` and issue no new request;
do not resume selection at a later favorable price or bypass the halt.

For a settled nonzero position, verify exact signed fill conservation, original
entry direction and absolute quantity no greater than the entry already filled
at that prefix or the fixed target. Compile the
opposite-side extra close for **that residual quantity only**, at that source
anchor. Apply the same protective limit formula to the quote known then; do not
widen the envelope or change assumed slippage, fees or latency to obtain a fill.
Source-end/missing quote or unresolved first-order state leaves the original
exposure explicitly unresolved.

## Native replay and retained outcomes

Persist the new decision, position/risk/working-order state and compiled plan
before running the extra-order replay. Its complete prefix before `close-retry`
must match the original one-close control exactly. Independently verify side,
quantity, anchor, limit and the bound prefix state/hash. The unchanged manual
proxy, independent source/Decimal checker and native ledger remain authoritative.
Do not mutate old helper bodies or native schemas to support the extra request.

The additional attempt can be unmarketable, rejected, partial or pending beyond
source end. Keep its actual conditional outcome; no further retry, forced close,
invented price, reduce-only support or manufactured source timestamp is allowed.
Never drain an arrival beyond actual recorded EOF. Zero fills and unresolved
positions have unavailable closed P&L rather than a zero-profit trade.

Retain original entry control, one-close control and optional new plan, complete
ledgers/links, source identity, candidate prefix/decision receipt, all native
checkpoint receipts and independent cost audits. Clearly distinguish observed
public source from assumed manual fills. Actual venue execution remains unknown.

## Reporting and admission

Report every original case and its control/new outcomes, optional retry decision,
requested/filled residual quantity, fees, pending state and ending exposure.
Report source-time delay to the retry separately from assumed order latency.
Show transitions such as open-to-closed and open-to-open without treating a
previous unavailable closed P&L as a return comparator. Compare net deltas only
when both cases finish closed; do not call added fees or recovered inventory
proof of improved profitability.

Keep profiles separate with complete denominators. A profile net statistic is
available only when all its selected cases are accounted for, no case remains
unresolved and at least one cycle closes, under the existing evaluation rule.
No pooled portfolio/annualized return or selection of a best profile is allowed.
R001's existing negative economic result remains unchanged regardless of whether
more cases become flat in this new experiment.

Use stopped read-only source/quality, the installed native image, new private
output outside all inputs and no network. Bind original inputs, binary, helpers,
assets, policy and this protocol before/after. Any change invalidates all new
metrics. Keep failures/not-run cases without replacements.

Bounds are 128 children/768 cases, three requests per case, 16 GiB total output,
1 GiB free reserve, 32 MiB report reservation, 128 MiB per source and 384 MiB
per entry/control/extra-order case admission. Native source/paper/call/checkpoint
bounds and stricter local space checks remain enabled. Suite admission is
3,600 seconds, native calls 30 seconds and outer timeout 3,660 seconds. Record
unavailable/not-run cases on refusal rather than selecting smaller substitutes.

Before delivery, require hand-calculated full/partial/no retry cases, exact
residual sizing and costs, first-attempt pending/terminal transitions, later-source
and equal-time causality, future independence, stale/missing/reconnected data,
EOF-pending extra orders and risk/loss rejection. Test unchanged original plans,
source/producer mutation, finite admission, repeatable native artifacts and
offline desktop/mobile views. This protocol does not implement or authorize
actual orders. The operational day gate, execution calibration and later frozen
new-data economic confirmation remain open.
