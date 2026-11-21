# Decision: a separately declared cost-screened momentum study

Status: specification frozen on 22 November 2026 PKT, before R002 implementation
or results. Signal `btc-bbo-cost-momentum-002`; experiment
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

The next work is the causal feature selector, separate native execution compiler,
offline runner and portable report, followed by the protocol's software acceptance
before any Mac evaluation. There is no R002 command or implementation yet. No new
capture is needed for that development; actual orders remain disabled. The day
gate, execution calibration and production stages remain open.
