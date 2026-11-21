# Run the fixed R002 momentum study

R002 now has a causal selector, native paper execution runner and portable report.
The [protocol](r002-cost-momentum-plan.md) and [constants](r002-cost-momentum-policy.json)
remain byte-identical to their preimplementation versions in `5b70337`. Their
historical status text records that freeze; this page describes the implementation.
Actual Mac results are pending. Software acceptance does not establish an edge.

Open Docker Desktop, install the momentum source update and run:

```sh
bash scripts/mac momentum quality-20261117T125619Z-mAfC1j
```

This uses the original stopped source and all 79 frozen development children,
with six profiles per child: 474 planned cases. It reuses the installed image
offline and requires no new capture or rebuild. Existing collector/monitor and
`last-run` stay fixed. Keep Terminal open for progress and the final readout;
macOS opens `~/GiethoornData/momentum-TIMESTAMP-SUFFIX/report/momentum.html`.
Paste the final output to review the actual result.

## What the program does

Within each recording, the first qualifying five-second candidate after 30 seconds
of causal history becomes its only entry feature. Its past 30-second midpoint
move must cross the current full spread plus 14 bps: ten for assumed round-trip
fees, two for slippage and two as a buffer. Every profile gets that same feature.
This is a past-movement filter, not a forecast of profit. Native accounting charges
the subsequent conditional fill costs once; the screen is not another fee.

History, reference and candidate bins follow the frozen one-second maximum gap,
250-ms reference tolerance, freshness/acknowledgement and connection/clock rules.
Independent native normalization must match original quote identities. Missing
history and abstention keep their first candidate rather than a later substitute
in the same bin. The selected feature, full candidate receipt and independent
arithmetic audit are saved before any forward label or execution.

The first fresh quote from 30 through 31 seconds after the feature can supply the
first close. Its quantity comes only from settled native position already known
there, with exact control-prefix equality. Risk halt, pending entry or missing
decision retains the actual state. One optional extra close may then use a fresh
quote and settled residual under the unchanged bounded-close rules. Three orders
are the maximum. Source-end, rejected and partial fills remain explicit; nothing
forces flat inventory. All retained control files are hashed before later replays
and checked again, including reused entry controls.

## Reading the report

The report shows source/policy preservation, planned and selected cases, no-signal/
no-fill/unavailable states, six separate profile totals, frozen chronological
thirds, exact feature/cost values, native decisions and ending exposure. Its raw
JSON export preserves exact amounts and timestamp strings. A complete profile
net requires every selected case accounted for, no unresolved position or pending
order and at least one closed cycle. Unknown closed P&L remains unavailable.

The research screen requires at least 30 closed baseline cases and 30 in each
required stress profile, at least ten baseline closes in each chronological third,
complete prescribed coverage and strictly positive prescribed totals. Fewer
signals or closes means insufficient data; incomplete exposure blocks advancement.
Lower/zero fees cannot pass the gate for the baseline. A passing candidate would
still need a separately predeclared new-data confirmation. All old partitions
are explored. The defined idle no-trade reference is separate from a failed,
missing or unfilled trade; no profiles are pooled into portfolio returns.

Software processing can complete with no signal and unavailable financial totals.
That is a valid result. Repeating a failed case, reducing the hurdle after seeing
outcomes or selecting another child would change this experiment. Actual venue
execution is unknown; the day gate and remaining production stages stay open.

## Bounds and evidence

Output is private and outside all inputs. Source, quality, executable, helpers,
template and both frozen specifications are bound before/after. Native archive,
source/normalization, causal or financial verification failure invalidates economic
admission. Space/time refusal keeps planned cases not-run without replacement.
The runner has a 16-GiB output cap, 1-GiB free reserve, one-hour suite admission
and 3,660-second outer timeout; existing stricter native bounds remain enabled.
It does not reserve all 16 GiB up front. A hard timeout may leave diagnostics
without final HTML. Full controls, ledgers, decisions and receipts remain bound
in `audit-inventory.json`, whose hash/count appear in the report.

All 479 Python tests pass: the 405 existing checks plus 31 signal/gate, 23 native,
18 admission and two Mac-wrapper checks. The 23 new native checks also pass inside
the unchanged Mac image. A retained synthetic source exercises fresh normalization,
saved selection and all six native profiles. Its baseline first close fills
0.00025 BTC and extra close fills only the residual 0.00075; ending position is zero
with exact conditional net `-0.000140240001` USDC. Other native checks cover both
directions, future independence, reconnection/equal-time boundaries, loss/notional
guards, partial/pending EOF states, immutable controls and exact repeat.

Two ordinary-user full-wrapper trials preserve all five development recordings
on the separate saved cloud software sample, producing 30 no-signal slots and
`insufficient_data`. Those sources last about 12 seconds, below the 30-second
warmup: this verifies refusal/coverage mechanics, not R002 economic performance.
Both trials' cases, features, counts and screen repeat exactly. All 104 bound
artifacts verify; 103 repeat byte for byte. Only `reviewed_at_utc` in the quality
review receipt differs, with every other field identical. Old producers, native
binary/image and frozen specifications remain unchanged.

Offline desktop and 390/320-pixel browser checks pass for saved/native fixtures,
exact amounts/export, a labelled synthetic 474-case layout, missing/open/pending/
risk states, incomplete totals and inert hostile text, with no errors or network
requests. Desktop native and mobile screenshots were visually reviewed. Receipt:
`data/momentum-acceptance-1511jj3c/native-release.json`.
No private Mac data was accessed or new public capture performed here. See
[decision 0019](decisions/0019-r002-cost-momentum.md).
