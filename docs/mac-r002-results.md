# First supplied Mac R002 momentum result

Status: supplied Terminal readout accepted on 22 November 2026 PKT. All 79 frozen
development recordings were processed. Fourteen recordings produced a signal and
65 produced none: 84 verified child/profile cases and 390 explicit no-signal slots
out of 474 planned. There are 71 conditional closes, 12 open cases and one no-fill
case across profiles. The baseline has 12 negative closes and two open cases.
The frozen research classification is **incomplete**, with no production gate met.

## Scope and verification

The readout is for `~/GiethoornData/momentum-20261121T221741Z-XgpqRI/report`,
following the issued `4a1d0c614a412f4f0c82305da4d0051596fcf517` update and original
quality snapshot `quality-20261117T125619Z-mAfC1j`. It reports source, quality and
code unchanged, no error, and zero unavailable/not-run cases. All 79 progress rows
match the selected/no-signal membership. Earlier diagnostic and R001 bounded-exit
history embedded in the pasted file matches its accepted receipts and is excluded
from the new R002 experiment.

This workspace read supplied text, not original private Mac recordings, full native
ledgers, quote histories, source/asset hashes or control prefixes. Count/progress/
membership identities, exact feature arithmetic, quoted reference/label timing,
printed quantity conservation and baseline fee arithmetic were independently
checked here. The local runner reports native/source/causal verification; those
checks were not independently replayed on private files in this review. First
qualifying quote selection and complete interval continuity require retained
source receipts beyond this compact text. Actual execution remains unknown.

## Fixed selection and outcome coverage

Selected children are 2, 10, 13, 15, 18, 30, 32, 33, 51, 58, 62, 63, 70 and 71.
Thirteen signals predict up and one predicts down. All 14 printed midpoint moves,
spreads, round-trip assumptions and hurdles reproduce with exact rational math;
each qualifies under the frozen spread-plus-14-bps rule. Historical references
are within 29.75–30 seconds, with matching connection IDs and stated freshness.
Displayed 12-decimal values reproduce independent half-even rounding.

Across bins considered until selection or source end, there are 3,921 bins,
3,900 candidates, 21 bins without a candidate, 1,432 candidates with missing history,
2,454 abstentions and 14 selected signals. These stopped-per-recording counts are
not all possible intraday signals or independent observations. No-signal slots
are retained; they are not successful trades or fabricated zero-profit outcomes.

Every profile contains all 79 slots: 14 verified cases and 65 no signal.

| Profile | Closed | Open | No fills | Positive / negative closed | Complete conditional net |
| --- | ---: | ---: | ---: | --- | --- |
| Baseline | 12 | 2 | 0 | 0 / 12 | Unavailable |
| Lower fee | 12 | 2 | 0 | 2 / 10 | Unavailable |
| Zero fee | 12 | 2 | 0 | 2 / 10 | Unavailable |
| Delay stress | 12 | 2 | 0 | 0 / 12 | Unavailable |
| Liquidity stress | 12 | 2 | 0 | 0 / 12 | Unavailable |
| Slippage stress | 11 | 2 | 1 | 0 / 11 | Unavailable |

The four positive closed results occur only under cheaper-fee controls. Neither
can pass the fixed baseline gate. Counts across profiles describe assumptions
on the same recordings, not 84 independent markets. No profile financial values
are pooled. There are 84 entry requests, 77 first-close requests and 12 additional
closes, giving 89 close requests. Known actual executions remain zero.

## Residual positions and the no-fill exception

All 12 open cases are on children 2 and 32, under all six profiles. They have no
pending order and unavailable closed P&L. The Terminal field `unresolved_cases`
contains 13 exception rows: these 12 open cases plus the separate no-fill case.
Outcome and position fields, rather than that list name, identify exposure.

| Child and profile | Entry filled, BTC | First close filled | Extra requested | Extra filled | Ending BTC |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2: all six | 0.001 | No close | No request | No request | 0.001 |
| 32: baseline, lower fee, zero fee, slippage stress | 0.001 | 0.00016 | 0.00084 | 0.00016 | 0.00068 |
| 32: delay stress | 0.001 | 0.00016 | 0.00084 | 0 | 0.00084 |
| 32: liquidity stress | 0.001 | 0.000064 | 0.000936 | 0.000064 | 0.000872 |

Child 2 reports `missing_decision` and no extra close. Its feature is at about
285.225 seconds, implying a first-close window at about 315.225–316.225 seconds.
No eligible decision was reported there. The compact text does not supply source
end or the surrounding quote window, so EOF versus a feed/quote gap is not
independently established. A missing original close cannot invent a later retry.

For child 32, reported entry minus both close fills exactly reproduces every
ending position. Extra requests equal the residual already left by the first
attempt. The liquidity-profile fills are exactly 0.4 times the baseline fills,
consistent with the frozen 10% versus 25% assumed capacity fractions. Execution
reference/fill prices, capacity receipts and order-level rejection/outcome details
are not printed here; these counts do not establish an actual venue shortage or
the reason delay stress fills zero.

Baseline child 18 has a smaller 0.000375-BTC entry. Its first close fills 0.0000975
and extra close fills precisely the remaining 0.0002775, ending flat. This case
remains a loss of `-0.034609450766625` USDC after `0.024397459016625` assumed fees.
Child 30 slippage stress reports zero entry fill, position and fees, with no close.
Its unavailable P&L is separate from a zero-profit trade. The exact entry nonfill
reason is absent from this compact readout.

## Economic and research decision

All 12 baseline closed cases are negative. Adding their reported fees back leaves
ten negative values and two positives: child 51 `0.04896740000` and child 62
`0.04197130000` USDC. Both are negative after baseline fees. This add-back still
contains spread and assumed slippage; it is not a raw-price return or an
independently paired zero-fee simulation. Fee reduction alone does not resolve
the ten already-negative add-back cases or the open exposure.

Ten of 14 selected features have valid forward labels; seven move against the
predicted direction and three with it. Four labels remain missing: three for a
gap over 1,000 ms and one for unusable BBO. This is a small, correlated descriptive
subset, not statistical significance, actual execution or a full strategy return.
A large move before entry did not guarantee continuation after entry.

The chronological thirds retain 26/26/27 recordings and 5/4/5 selected signals.
Baseline closed counts are 4/3/5. The first two thirds retain one open case each;
their totals remain unavailable. The final third's complete baseline net
`-0.53855340735` USDC matches the sum of its five printed negative closes.
The full baseline/profile totals remain unavailable because of the open cases.

Accept software processing while keeping the frozen **incomplete** classification:
required profiles retain exposure. Independently, every required profile has fewer
than 30 closes and every baseline third fewer than ten, so sample thresholds are
also unmet. The observed baseline closes supply no positive economic evidence.
R001 and R002 use different entries/horizons; their closed subsets are not a paired
return improvement comparison. All previous results retain their own outcomes.

Keep R002 at research stage. Any follow-up needs its own declared protocol and
retains this attempt; a useful read-only diagnostic would inspect the missing
window and partial/zero-fill receipts without changing the hurdle or forcing
flat inventory. No further Mac command, capture or replay is needed to accept
this result. Runtime, native schemas, frozen policy/protocol and old producers
are unchanged by this documentation acceptance. The day gate, actual execution
calibration, new-data confirmation and production stages remain open.

Receipt: `data/mac-r002-review-20261121T224503Z-r_uqrwp8/review.json`.
