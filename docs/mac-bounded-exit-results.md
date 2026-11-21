# First supplied Mac bounded-exit result

Status: supplied Terminal output accepted on 21 November 2026 PKT. All 474 cases
verify under the unchanged frozen development cohort. Twelve additional closes
produce two full fills and ten partial fills. Conditional closes increase from
461 to 463; unresolved cases decrease from 12 to 10; the one no-fill case remains.
The baseline still has 77 negative closes and two open cases. This supplies no
positive economic evidence for R001.

## Scope and evidence

The readout is for
`~/GiethoornData/bounded-exit-20261121T162831Z-JMVRwJ/report`, following the issued
`564fd1807d9df8ad3557947651c234f589fe3edb` update. It identifies experiment
`r001-bounded-exit-002`, the original quality snapshot and development children
2–80. All 79 progress rows report six verified cases. Source, quality and code
are reported unchanged, with no error, missing signal, unavailable or not-run case.

The control totals exactly match the previously accepted
[one-close evaluation](mac-development-evaluation-results.md): 474 verified,
461 closed, 12 unresolved, one no fill, 474 entries and 473 first closes. The new
run adds 12 closes, giving 485 close requests. Every original case remains in its
profile's denominator. The earlier 13-case diagnostic embedded in the pasted
history matches the accepted diagnostic and was not counted as a new experiment.

This workspace checked the supplied text rather than reading private Mac source,
full case ledgers, source quotes/sizes/limits, audit inventories or native prefixes.
Exact cohort/progress/count identities, residual sizing, signed fill conservation,
baseline continuity and paired fee ratios were recomputed here. Integrity and
prefix verification remain reports from the local runner, not a new independent
cloud replay. All fills are manual simulation; actual execution remains unknown.

## Every profile remains visible

Each row contains 79 verified independent cases on the same recordings under a
different assumption profile. Counts are not independent market samples and
financial values are not pooled into a portfolio return.

| Profile | Extra requests | Closed | Unresolved | No fills | Positive / negative closed | Complete conditional net, USDC |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Baseline | 2 | 77 | 2 | 0 | 0 / 77 | Unavailable |
| Lower fee | 2 | 77 | 2 | 0 | 0 / 77 | Unavailable |
| Zero fee | 2 | 77 | 2 | 0 | 2 / 75 | Unavailable |
| Delay stress | 2 | 79 | 0 | 0 | 0 / 79 | -5.551578761947125 |
| Liquidity stress | 2 | 77 | 2 | 0 | 0 / 77 | Unavailable |
| Slippage stress | 2 | 76 | 2 | 1 | 0 / 76 | Unavailable |

The delay-stress total is now available because all its cases finish closed. It is
reported by the runner; its 77 unchanged closed case values are not individually
printed, so this review does not independently recompute that full sum. Every
delay-stress close is negative. The other five profiles retain open exposure and
correctly unavailable complete totals. The original controls retain their original
unavailable totals; there is no complete control-to-new net difference to compute.

## What changed in the two source sessions

All retries occur on children 8 and 56, under all six profiles. All 12 are compiled
for precisely the contemporaneously known short residual, with reported verified
prefixes and no pending order at source end. Each signed ending position equals
its control position plus the new buy fill; no position reverses direction.

| Child and profile | Known short before retry, BTC | Extra buy requested | Extra buy filled | Ending BTC | Extra outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| 8: baseline, lower fee, zero fee, slippage stress | -0.001 | 0.001 | 0.00037 | -0.00063 | Partial, remainder cancelled |
| 8: delay stress | -0.001 | 0.001 | 0.001 | 0 | Filled |
| 8: liquidity stress | -0.001 | 0.001 | 0.000148 | -0.000852 | Partial, remainder cancelled |
| 56: baseline, lower fee, zero fee, slippage stress | -0.0007025 | 0.0007025 | 0.0002425 | -0.00046 | Partial, remainder cancelled |
| 56: delay stress | -0.0007575 | 0.0007575 | 0.0007575 | 0 | Filled |
| 56: liquidity stress | -0.000881 | 0.000881 | 0.000097 | -0.000784 | Partial, remainder cancelled |

Baseline child 8's total assumed fees rise from `0.03232776690` to
`0.044294208424500` USDC, an additional `0.011966441524500`. Child 56 rises from
`0.042117962024250` to `0.049991026752000`, an additional `0.007873064727750`.
Both still have unavailable closed P&L. All 77 previously closed baseline outcomes,
exact fees/net, ending positions and pending states remain unchanged.

The two new delay-stress closes have conditional net `-0.0916088007` and
`-0.07891060005` USDC. Their original open cases had unavailable closed P&L;
these new negative values are not a return improvement against zero. A later
assumed arrival encountering different displayed capacity does not establish that
more delay is preferable or that an actual venue would fill those quantities.
The ten remaining partial fills demonstrate the model's finite assumed capacity,
not a separately measured physical shortage. The slippage no-fill entry remains
separate from a zero-profit trade.

## Decision and next work

Accept this bounded exposure-management experiment as completed under its fixed
one-extra-attempt cap. It reduces inventory in these cases but does not guarantee
flat inventory. Persistent residual exposure remains a limitation for later live
use. The existing R001 policy retains negative baseline evidence and is not ready
for promotion to funded trading.

Further strategy research needs its own fixed hypothesis, causal signal and
cost/exit rules before outcome inspection, followed by separately frozen new-data
confirmation if development evidence warrants it. All original partitions are
already explored. The operational day gate, actual fill calibration, forward
paper integration, exchange/testnet reconciliation and separately approved funded
pilot remain open. This research result does not advance another production gate.

No further Mac command, capture or replay is needed to accept this readout. This
acceptance changes documentation only; runtime, frozen protocols, native schemas,
producer assets and prior negative/open artifacts remain unchanged. Receipt:
`data/mac-bounded-exit-review-20261121T183909Z-wpn2g4g6/review.json`.
