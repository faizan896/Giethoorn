# Decision: separately versioned bounded additional-close experiment

Status: implementation, software acceptance and first supplied Mac readout accepted.
Follow the
[predeclared bounded-exit protocol](../bounded-exit-plan.md), experiment
`r001-bounded-exit-002`, with new policy/report namespaces at version 1.

The supplied development exceptions reconcile with the unchanged model:
six closes fail its price-limit test, six close partly within its assumed
liquidity budget, and one entry fails its price-limit test. Quantity/accounting
arithmetic matches; this evidence does not demonstrate an engine bug. Original
outcomes and all declared cost/limit/size rules remain their own results.

The new experiment permits only one additional close after the original attempt
has terminal native state. Choose the first subsequent eligible native BBO from
information available then and size only from the settled residual position.
Require complete control/new prefix equality before that request and independent
source/Decimal/native checks. Keep risk halt, source EOF and missing/partial
execution states explicit; no limit widening or loop until flat is allowed.

Reuse the full frozen development cohort and six profiles, not only observed
exceptions. Preserve entry/first-close requests, native schemas and old producer
assets. Bound the extra work and retain unavailable cases without replacements.
This is an exposure-management experiment on explored data. It cannot establish
a profitable R001 edge, actual fill calibration or readiness for funded trading.

`bash scripts/mac bounded-exit QUALITY-ID` now implements this protocol through
new helpers and a new offline report. It reproduces unchanged one-close controls,
persists the optional request/receipt before replay, and checks complete native
prefix equality plus independent side/size/anchor/limit arithmetic. Retained
control hashes are rechecked after the extra replay. Changed source, quality,
protocol, producer or binary invalidates both comparison sides. The frozen
protocol remains byte-identical, SHA256
`894827116ac7023bba4c10c9b0ae511d08ff18b124b36cbbf6d446df4649e2c7`.

All 405 Python tests pass, including 28 new native checks. Those 28 also pass
inside the unchanged Mac image. A retained synthetic partial-close case requests
only its remaining 0.00075 BTC and closes with negative conditional net; pending,
partial and risk-rejected extra attempts keep exposure. Two ordinary-user Docker
trials on the separate five-child/30-case cloud sample reproduce all original
controls exactly. All sample controls already close, so zero retries are issued.
Of 1,464 bound artifacts per trial, 1,463 repeat byte for byte; the sole difference
is `reviewed_at_utc`, with every other receipt field exact.

Offline desktop/mobile checks pass for native output, exact export, a labelled
synthetic 474-case layout and unavailable outcomes/totals without errors or
network requests. Source/quality/native/image and old producers are unchanged.
No private Mac source was accessed or new capture performed. See [the operator guide](../bounded-exit.md)
and `data/bounded-exit-acceptance-ecwx2mrn/native-release.json`.

The [supplied Mac result](../mac-bounded-exit-results.md), accepted on
21 November 2026 PKT, reports all 79 children/474 cases verified, unchanged
source/quality/code and exactly reproduced old control totals. Twelve extra
requests produce ten partial and two full fills. Closes rise from 461 to 463,
unresolved cases fall from 12 to ten, and one no-fill case remains. Both new
closes are negative delay-stress cases. Baseline retains two open cases and its
77 closed values remain exactly unchanged and negative. Delay stress alone now
has a complete conditional total, reported as `-5.551578761947125` USDC; all other
profile totals remain unavailable. Its original control total remains unavailable.

Exact text-level membership/count/position/fee checks pass, without independent
access to private native ledgers or source quotes. Accept the bounded experiment
while retaining residual inventory, the one-extra-attempt cap and the negative
economic conclusion. The result does not demonstrate a preferable delay profile
or complete a production gate. No further capture/replay is needed for acceptance.
Receipt: `data/mac-bounded-exit-review-20261121T183909Z-wpn2g4g6/review.json`.
