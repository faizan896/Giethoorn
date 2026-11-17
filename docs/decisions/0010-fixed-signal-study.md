# Decision 0010: fixed offline prediction study

## Scope and versions

Implement the predeclared `btc-bbo-imbalance-001` hypothesis for BTC mainnet.
Study policy/report, feature receipts and sample/outcome receipts each declare
version 1. Native event, normalization, recording, audit and paper contracts are
unchanged. The original release/experiment runner remain byte-identical. This
produces predictions; there are no orders, fills, positions, fees or P&L.

## Frozen admission and partition isolation

Require the admitted version-1 quality manifest and exact source inventories,
producer/auditor, policy, protocol, template/theme, audit and span fingerprints.
Hold a shared source lock throughout; copy quality evidence before outcomes.
Fresh native audit and quality recomputation must reproduce the frozen source,
audit output, market domain and chronological partition membership. Health checks
read the whole archive; signal outcomes are computed only for the selected group.

Development is the default. Validation and retrospective test require explicit
separate CLI selection; no `all` mode exists. Unrun/excluded rows have null scores.
Changed inputs, cohorts or verifiers refuse/invalidate results. This checks
internal consistency, not a signature or venue-authenticity proof. Synthetic
fixtures retain their declared origin and inspected sessions stay flagged.

## Causality

Align original records with their verified normalized observations by sequence,
connection and timestamps. Only acknowledged fresh two-sided BBO observations
with strictly newer exchange times can supply samples. Prices, coin and exchange
time must match their original message; sizes come from that exact message.
Native normalized midprices remain authoritative.

Use the first eligible quote once per five-second child-relative bin. Bid size
at least three times ask size predicts up, the reverse down; otherwise abstain.
Abstentions consume their bin. Empty bins remain empty. Feature receipts are
flushed separately before processing future records and are never replaced.

The label is the first eligible BBO 1,000–1,250 ms later within the same child and
connection. A gap over 250 ms, unusable feed, repeated exchange time, connection
change, detected clock step, expiry or source end makes a pending label missing.
Depth cannot refresh/label BBO. There is no interpolation or forward fill.

## Metrics and exact arithmetic

Retain samples, abstentions, available/missing labels, missing signal labels,
ties, empty bins and missing reasons. Hit rate uses labelled directional signals;
unchanged prices count as misses. Always-up/down controls use that same subset.
Zero-signal children stay visible. No independence, significance or economic-edge
claim follows from these descriptive counts.

Input decimals and each sample's signed basis-point change use exact fractions,
saved as integer numerator/denominator strings. Aggregate changes round each
sample half-even to 12 decimal places, sum integer ticks exactly, then round the
mean to 12 places. This avoids an unbounded common denominator across prices.
Display means round to six places; percentages to four. These representation
choices do not change the signal, label rules or cohort. No binary-float money
calculation is used. Exact per-sample fractions remain alongside the report.

## Runtime and acceptance

`scripts/mac study quality-ID [partition]` binds the parent named by that snapshot,
independently of a later `last-run` marker. Source/quality/helpers/templates are
read-only and networking disabled; output is a fresh directory. The existing
image/resource caps and 600-second job timeout apply. Feature/sample streams are
each capped at 64 MiB, quality input at 128 MiB, JSON at 6 MiB and HTML at 8 MiB.
Failure retains diagnostics and never admits partial scores. Provenance binds
source/quality, policy/code, feature/sample and view hashes.

Synthetic hand calculations test boundaries, gaps, independent feeds/connections,
clock steps, future-price independence, source identity, rounding and freezing.
Native acceptance verifies repeated feature/sample bytes on a separately recorded
small public archive. Those few outcomes are integration evidence, not research
or profit evidence. The portable offline view preserves unavailable groups,
exact JSON values and inert escaped strings. Mac study outcomes require its local run.
