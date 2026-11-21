# Decision: a separately declared cost-screened momentum study

Status: specification frozen before implementation; software/native/browser
acceptance and first supplied Mac readout accepted on 22 November 2026 PKT.
Signal `btc-bbo-cost-momentum-002`; experiment
`r002-cost-momentum-001`; new feature/policy/report namespaces at version 1.
This introduces no native event, recording or execution-schema change.

The [accepted R001 bounded result](../mac-bounded-exit-results.md) still has 77
negative baseline closes and two unresolved baseline cases. Additional closes
reduce some exposure without establishing a positive edge. R002 declares one
new hypothesis: 30-second price momentum larger than a fixed current-cost screen
continues enough over the next 30 seconds to cover actual conditional execution
costs. Past momentum is a selection rule, not an expected-profit estimate.

The [protocol](../r002-cost-momentum-plan.md) fixes the historical reference,
five-second candidate bins, one first qualifying feature per child, all existing
development members and six unchanged profiles, native-prefix close sizing and
one bounded residual retry. The hurdle is current spread plus 14 bps: ten fee,
two adverse-slippage and two buffer bps. Native execution charges its own actual
conditional fill costs without charging that screen again.

The 30-second history has a separately declared one-second maximum BBO gap;
feature/close quotes keep the existing 250-ms freshness bound. Missing/stale/
reconnected history cannot be replaced or interpolated. First close uses an
observed fresh BBO from +30 through +31 seconds and known settled native state.
Missing/pending/partial/risk-rejected exposure remains explicit. Original R001
rules, quality spans, negative results, producers, native binary and image stay
fixed. Implement R002 in separate helpers; no old helper is patched at runtime.

The fixed baseline and required adverse-cost profiles need complete coverage,
at least 30 closed cases each and positive complete net. Baseline also needs ten
closes and positive net in every frozen chronological third. These are research
screens, not statistical significance or trading approval. Insufficient data,
unresolved exposure or negative results are retained without a parameter search.
Only a passing candidate warrants a separately predeclared new-data study.
All existing partitions are explored and cannot become a new holdout by renaming.

Frozen SHA256 values:

- Protocol: `1e84c6beeb92f7522c4e1a2d571e4990466705b51318198264849417e5e03c02`.
- [Policy constants](../r002-cost-momentum-policy.json):
  `d6ee87006f5c39800da3be2e1a8a678a0d7b29f73b1f6bb5fb5218931245907b`.

Seven synthetic exact-arithmetic examples check up/down/abstention, wide spread,
both equality boundaries and a flat price. Six profile definitions and risk/limit
constants equal existing values, and the 79-child chronological thirds have
26/26/27 members. Bounds and references are checked. These are specification
checks, not native acceptance or R002 market results. Receipt:
`data/r002-specification-review-20261121T200749Z-axvez5nh/review.json`.

`bash scripts/mac momentum QUALITY-ID` now implements the causal selector,
separate native close compiler, bounded residual close and portable offline report.
Complete control prefixes and retained artifact hashes are checked without
changing old helpers, native schemas, protocol, constants or executable/image.
All 479 Python tests pass, including 23 native checks also passing inside the
unchanged Mac image. Six retained synthetic native profile cases exercise the
30-second signal and exact residual/cost accounting. These are software results.

Two ordinary-user full-wrapper repeats preserve five saved cloud development
sources/30 no-signal slots. Their roughly 12-second duration is below R002 warmup;
the correct result is insufficient data, with no economic evaluation. All cases/
counts/gates repeat exactly. Of 104 bound artifacts per trial, 103 repeat byte for
byte; only the review timestamp differs. Offline desktop/mobile/native/474-case
stress checks pass with exact export and unavailable-state handling, without
browser errors or network requests. Native desktop/mobile screenshots were reviewed.
Receipt: `data/momentum-acceptance-1511jj3c/native-release.json`.

The [first supplied Mac readout](../mac-r002-results.md), for
`momentum-20261121T221741Z-XgpqRI/report` after the issued `4a1d0c6` update,
reports complete processing: 14 selected recordings/84 verified child-profile
cases and 65 no-signal recordings/390 slots. Source/quality/code are unchanged,
with no unavailable/not-run case. There are 71 closes, 12 open cases and one
no fill; all six complete profile totals remain unavailable. Baseline has
12 negative closes and two open cases. The frozen gate correctly stays incomplete.

Exact text-level feature/reference/hurdle/label arithmetic, counts, signed fills,
fee consistency and chronological baseline coverage checks pass. Ten forward
labels include seven moves against the signal; missing labels remain missing.
Fee add-back leaves ten baseline closes negative and two positive, while all
12 are negative after baseline fees. These small descriptive subsets establish
no calibrated edge. Original private source, ledgers and prefix hashes were not
independently replayed here. Receipt:
`data/mac-r002-review-20261121T224503Z-r_uqrwp8/review.json`.

Keep R002 at research stage under its frozen rules. No further capture/replay is
needed to accept this readout. See [the operator guide](../r002-cost-momentum.md).
Actual execution is unknown, orders remain disabled, and the day gate,
execution calibration, new-data confirmation and production stages remain open.
