# R002 retained-evidence diagnostic, version 1

This is a read-only diagnostic of a completed `r002-cost-momentum-001` bundle.
It does not change that experiment, choose another entry, retry another order,
change a profile, tune a threshold or request new market data. Its namespace is
`r002-retained-diagnostic-001`; original native and research schemas stay fixed.

## Admission and verification

Require the original completed, unchanged version-1 R002 report; its complete
inventory; the original frozen R002 specifications and producer fingerprints;
the installed executable matching the original binary; and the copied admitted
quality manifest. Never execute a binary supplied inside an evidence bundle.
Preserve every frozen development recording and every one of its six case slots.
Reject unsafe paths, symlinks, unsupported files, duplicate JSON keys, nonfinite
numbers, missing artifacts, extra unbound artifacts and incomplete bundles.

Re-run the installed native market adapter and normalizer on each already saved
selected recording. Require byte equality with the retained market and normalized
outputs and bind each recording to the copied original source inventory. Recheck
original feature selection and labels without choosing replacement entries.
Re-run native paper replay only on the already saved manual inputs for each
distinct entry, first-close and residual-close ledger. Require exact retained
updates/reports, checkpoint prefix hashes and independent source/Decimal ledger
verification. Recheck original entry and close/retry prefix receipts, compact
case results, totals and research classification. No policy producer is invoked.

The copied quality audit remains a bound historical receipt. This diagnostic
independently replays the selected copied recordings, not every recording in the
original collection archive. Before/after full bundle fingerprints and producer,
diagnostic, specification and installed-binary hashes must agree. Any failure
invalidates the new diagnostic, suppresses its admitted financial analysis and
leaves the original result untouched. A new output directory retains failure
receipts. Successful native temporary outputs may be removed only after byte
equality, with paths, byte counts and SHA-256 receipts retained.

## Missing close windows and order capacity

Use the original feature and the fixed inclusive 30–31-second close window.
Distinguish a source ending before the window, ending inside an unobserved
remainder, and an observed window lacking an eligible native BBO. Count all BBO
messages separately from eligible native decisions. Retain boundary events,
connection/feed state and actual source-end reason; never interpolate a quote or
force a close at EOF. A missing close alone does not identify a physical cause.

For every original requested order retain side, requested/filled size, request
and assumed-arrival time, original decision quote, arrival reference, reference
age/eligibility, touch, assumed price, limit, marketability, native rejection and
final lifecycle. Display reference top size, assumed size fraction and remaining
shared capacity. A partial fill is capacity-limited only when the verified
marketable order fills exactly that smaller remaining capacity. Capacity is a
model assumption, not actual venue liquidity. The difference from current top
size can include previous fills, conservative earlier caps or ambiguous quotes.

## Exact cost identity

For each filled order, let `s=+1` for buy and `s=-1` for sell, `q` be its actual
assumed filled quantity, `D` the midpoint at the original decision, `M` the
midpoint of the known arrival reference, `T` its side's touch and `F` the assumed
fill price. Compute exactly from decimal strings:

* decision-midpoint cashflow: `sum(-s*q*D)`;
* arrival price change cost: `sum(s*q*(M-D))`, signed and possibly favourable;
* half-spread cost: `sum(s*q*(T-M))`;
* assumed slippage cost: `sum(s*q*(F-T))`;
* native assumed fees: `sum(fee)`.

For a native fully closed case with no pending order, require
`closed net = midpoint cashflow - arrival change - spread - slippage - fees`.
This is an accounting identity conditional on the original assumed fills, not
an executable midpoint strategy, expected return or calibrated latency effect.
Open/pending cases retain per-fill costs and inventory but have no closed
decomposition or closed P&L. No fill and no signal remain distinct unavailable
outcomes. Never pool six assumption profiles or report a portfolio return.
Preserve the original development screen and its incomplete totals.

## Bounds and presentation

Input at most 17 GiB, 100,000 files, 128 MiB per file; original JSON report at
most 6 MiB. Original cohort bounds remain 128 children and 768 case slots. New
output at most 1 GiB, with 1 GiB free reserve, 32 MiB report reserve and 128 MiB
admission allowance. Whole diagnostic budget 3,600 seconds; each native process
30 seconds with 32 MiB per stream; outer Mac timeout 3,660 seconds. Boundaries
and times export as decimal strings without JavaScript precision loss.

Create a portable browser report and raw JSON with clear source origin, original
versus diagnostic status, complete case coverage, baseline movement/cost identity
and per-order exception evidence. Render untrusted strings as text, with no
external resources. A diagnostic failure must hide admitted financial values.
Synthetic tests must stay labelled synthetic. No wallet, credentials, live order,
fresh capture, image rebuild or production-gate advancement is part of this work.
