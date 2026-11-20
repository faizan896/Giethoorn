# Decision: read-only expiry diagnostics, version 1

Status: implemented for existing R001 cost-probe artifacts. Existing recording,
normalization, paper v1/v2/v3, cost policy and report schemas remain unchanged.
The new outputs are `expiry_report_version: 1` and
`order_diagnostic_version: 1`. All nanosecond source/boundary/offset fields use
decimal strings; financial values are copied/verified exact decimal strings.

The first Mac probe reports ten expired entries and an unresolved short after a
close expiry. A cost summary cannot explain event timing or distinguish a shifted
eligibility window from better execution. This diagnostic binds each existing
request and its declared arrival/exclusive expiry to original recorded events.
It includes all selected cases and only originally requested orders. No trading
policy, intent, fill, acknowledgement or post-source liquidation is generated.

## Verification before explanation

Admit only preserved cost-report version 1 with the supported original policy,
profiles, limits and code/asset fingerprints. Bind the full bundle inventory and
copied frozen quality/source metadata; verify membership and lifecycle counts.
The installed native binary must match the original artifact's pinned hash.

Fresh mark-only replay and normalization verify each child once. Compare its
source/report/market streams to each saved control and compiled case. Replay the
already persisted paper input through the native ledger and compare exact updates
and final report. Independently verify costs/size/timing with the existing Decimal
auditor. Reconstruct the original feature and causal close prefix to compare the
saved plan, receipts and metrics; do not execute another scenario. No new native
execution semantics or lower-level schema is introduced.

Order inspection must agree with the first resolvable recorded event. A pending
order resolves on the first subsequent selected-feed native opportunity at/after
arrival and strictly before expiry; otherwise the first observed event reaching
expiry rejects it. At exact expiry a fresh quote still cannot fill it. An early
ledger rejection is separate. No resolving event leaves the order pending.
Partial/zero fills preserve IOC cancellation semantics and shared/equal-time
liquidity assumptions. Missing/duplicate or inconsistent source/trace transitions
are refused rather than assigned a plausible explanation.

## Presentation and scope

Retain the request, nearest original events around arrival/expiry, first usable
native opportunities, actual observed resolution and source gaps, with references.
Declared boundaries are labelled assumptions rather than inserted clock events.
The portable view filters case/order diagnoses and exposes original risk, quantity,
position, pending state and event sequence. Time-unit formatting uses integer
arithmetic; raw JSON download preserves exact strings and large integers.
Unknown/unadmitted diagnostics stay unavailable with their reason.

Baseline `[100,350)` ms and delay-stress `[250,500)` ms windows are shifted rather
than nested. Different fill counts do not measure latency or establish that extra
delay helps. Recorded gaps do not identify a venue, transport, power or machine
failure component. The report keeps that root cause unknown. No profit is newly
estimated, aggregated or selected by successful outcomes.

Read-only snapshots, a full before/after input/code/binary check, finite native
timeouts and disk/output/record bounds apply. Any changed evidence invalidates
all diagnostic rows. The Mac wrapper uses the existing image, network disabled,
read-only source/helpers and a new output directory, without collector changes.

Acceptance covers golden synthetic lifecycles, exclusive expiry, stale and repeated
quotes, original source references, pending ends, partial fills and risk rejection,
shifted windows with native source/ledger checks, corruption/refusals, preservation,
repeatability and offline browser rendering. A separate saved cloud artifact is
software evidence; it is not the user's Mac result or execution calibration.
