# First supplied Mac R002 retained-evidence diagnostic

Status: supplied Terminal readout accepted on 28 November 2026 PKT. The Mac reports
completed verification of 79 copied recordings, 173 distinct saved manual ledgers
and 71 closed-case cost identities, with input/code unchanged and no error.
The original R002 research classification remains **incomplete**. These are
manual paper simulations; actual execution remains unknown.

## Scope and evidence

The issued update is `452a39f96b5fb4c1f17f363b590f2bcdde21b046`. The command inspects
the original `momentum-20261121T221741Z-XgpqRI/report` and writes the separate
`~/GiethoornData/momentum-explain-20261127T215129Z-O4twGK/report/`.
All 79 progress rows verify children 2–80 in their original order, with six slots
each. This reconciles the original 474-slot denominator: 84 selected cases and
390 no-signal slots. The 173 ledger checks equal the original 84 entry controls,
77 first-close ledgers and 12 residual-close ledgers; reused controls are counted
once. Seventy-one cost identities match the original 71 conditional closes.

This review independently parsed supplied text, reconciled all progress/case
membership and original outcomes, and checked all twelve printed closed baseline
identities using exact rational arithmetic. Every printed exception's position,
request/fill quantities and price-limit classification reproduce. The Mac runner
reports native replay, inventory, source, producer and prefix verification.
Private recordings, native ledgers, full diagnostic JSON and audit-inventory
hashes were not supplied or independently inspected/replayed in this workspace;
the other 59 closed-cost identities remain reported by the runner. The copied
collection-wide quality audit is a historical bound receipt, rather than a fresh
audit of the entire original archive. No production gate is completed.

## Why the original positions remain open

**Child 2, all six profiles:** the actual recorded source ends at
`300118287205` ns. The original first-close window starts at `315225345691` and
ends at `316225345691` ns, consistent with the original feature at `285225345691`.
The source ends **15.107058486 seconds before the window opens**. The reported
`source_ended_before_close_window`, `missing_decision` and `no_first_close` agree.
The filled 0.001-BTC entry stays open; no later price or forced close is invented.
This is a censored recording boundary, not evidence of a physical network fault
or actual venue inability to execute. The compact readout does not print the
source-end reason or the full boundary-event receipts.

**Child 32, all six profiles:** eligible original close quotes exist. Partial
fills equal the smaller remaining assumed capacity of the marketable requests.

| Profile | First close requested / filled, BTC | Extra requested / filled, BTC | Ending BTC |
| --- | --- | --- | --- |
| Baseline, lower fee, zero fee, slippage stress | 0.001 / 0.00016 | 0.00084 / 0.00016 | 0.00068 |
| Delay stress | 0.001 / 0.00016 | 0.00084 / 0 | 0.00084 |
| Liquidity stress | 0.001 / 0.000064 | 0.000936 / 0.000064 | 0.000872 |

Baseline's 0.00016-BTC cap and liquidity stress's 0.000064 cap imply the same
0.00064-BTC recorded reference top size under their frozen 25% and 10% assumptions.
At those requests, nominal and remaining capacity agree. This establishes the
simulation's capacity restriction, not actual venue liquidity or a physical cause.

Delay stress's residual sell request is separately **not marketable**: the assumed
price `65063.493` is `3.491` USDC per BTC below its `65066.984` sell limit. Remaining
assumed capacity is `0.238255` BTC, greater than its 0.00084 request, so that retry
does not fail from insufficient capacity. Its first close remains capacity-limited.
Slippage stress's child-32 entry and closes fill exactly at their inclusive limits;
the printed classifications respect those boundaries.

All twelve open cases retain their original positions, no pending orders and
unavailable closed P&L. The maximum-one-extra-close rule is preserved.

## Why the separate entry did not fill

**Child 30, slippage stress:** the assumed buy price `64997.997` exceeds its
`64992.996` limit by `5.001` USDC per BTC. The 0.001-BTC request has 0.00157 BTC of
remaining assumed capacity, but is correctly classified `not_marketable` and fills
zero. The prior result's zero fees/flat position and `flat_no_close` agree.
This is the thirteenth exception row, separate from the twelve open cases and
from a fabricated zero-profit trade. There is no native rejection detail printed;
the assumed-price/limit relation explains the nonfill under this manual model.

## What the closed-case accounting says

All twelve baseline closed nets and fees exactly match the
[previously accepted result](mac-r002-results.md). For each, independently require:

```text
decision-midpoint cashflow - signed arrival price change
  - spread - assumed slippage - fees = native conditional closed net
```

Nine of twelve original decision-midpoint benchmarks are negative; three are
positive, on children 33, 51 and 62. After the original costs, all twelve nets are
negative. These benchmarks condition on the original assumed filled quantities
and request times; they are not executable midpoint strategies, expected returns
or an independent forecast-accuracy statistic. They differ from the ten available
forward labels, which have their own missing-data and timing rules.

For example, baseline child 51 has `0.063` USDC of decision-midpoint cashflow,
zero arrival change, `0.001` spread, `0.0130326` assumed slippage and
`0.0651629969` fees, giving the original `-0.0161955969` conditional net exactly.
Child 18's partial entry and two exits similarly reproduce
`-0.034609450766625` using midpoint cashflow `-0.00454125`, arrival cost
`0.00041625`, spread `0.000375`, slippage `0.00487949175` and fees
`0.024397459016625`.

Signed arrival costs are favourable for children 13 and 62 and adverse for 18 and
30; the other eight baseline closed cases have zero arrival cost. Adding fees
back still leaves ten negative results and two positives, as previously accepted.
Neither lower fees alone nor resolving the recording-boundary explanation supplies
positive baseline economic evidence. No open case gets a closed decomposition,
no profile total becomes complete, and the six assumptions are not pooled.

## Decision and next work

Accept the diagnostic processing and explanations while preserving every original
R002 outcome, the incomplete research classification and unmet sample thresholds.
The twelve negative baseline closes and two open baseline positions remain the
same result. The recorded-data replay/accounting checks have passed on the Mac;
a profitable economic hypothesis remains unestablished.

No additional Terminal run or capture is needed to accept this readout. A new
research protocol must separately specify position handling across recording
boundaries, partial/nonmarketable exits and its economic hypothesis before any
new result. Retrospective EOF must not become a future-aware entry filter; removing
open cases, loosening limits or retuning R002 on these outcomes would change the
experiment. Any modified policy gets its own identity and independent confirmation.
The 24-hour reliability, actual-execution calibration and production gates remain
open. This acceptance changes documentation only.

Receipt: `data/mac-r002-diagnostic-review-20261128-jkoccmp7/review.json`.
