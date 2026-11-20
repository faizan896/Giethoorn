# First Mac R001 cost-probe results

Status: the bounded mechanics suite completed on 20 November 2026. All 24 paper
cases were reported verified, with source, frozen quality and code unchanged.
Every one of the 13 closed cases lost money under its declared assumptions.
Ten entries expired before a usable simulated fill opportunity; one filled short
remains unresolved after its close expired. This provides no positive economic
evidence for the current policy. Four recordings cannot establish its general
performance or statistical significance.

## Scope and provenance

The user supplied the Terminal summary and compact per-case extraction from
`~/GiethoornData/cost-20261120T115202Z-fKjWVP/report/cost-report.json`. This workspace
has not read or independently audited the original Mac report or recordings.
The retained receipt explicitly identifies user-terminal provenance. Decimal
arithmetic, case membership and lifecycle identities were recomputed here.

Selected children are 2, 3, 4 and 5, from the development partition of frozen
quality snapshot `quality-20261117T125619Z-mAfC1j`, source
`start-20261116T161743Z-8dyq7k`. Their six profiles produce 24 independent paper
starts, not 24 independent market samples. Fees/latency/liquidity are illustrative
assumptions rather than venue measurements. The reported policy fingerprint
`59041d3571df9b5e2ceb9a89c8ae332a789bd3f2cdbb1c9827c25dcdfa42d15e`
matches the unchanged released policy/profile/limit configuration.

All filled entries in this extraction have quantity 0.001 BTC. Each closed case
also exits 0.001 BTC and ends flat, without pending orders. An expired entry has
zero fill, fees and position; its closed P&L is unavailable, not a zero-return
trade. The open case has entry fill 0.001 BTC, exit fill zero, position
**−0.001 BTC**, fees **0.03227727195 USDC** and no pending orders. Its closed P&L
remains unavailable. No open-case mark, unrealized value or decision timing was
included in the extraction.

## Two comparable closed recordings

All amounts below are exact reported strings in USDC. Pre-fee values add fees
back to the baseline net; spread/slippage are already reflected in execution
prices and remain included. They are not the earlier signal's midprice return.

| Recording | Baseline net P&L | Baseline fees | Derived P&L before fees | Zero-fee control net |
| --- | ---: | ---: | ---: | ---: |
| 3 | -0.07074739965 | 0.06478949965 | -0.0059579 | -0.0059579 |
| 4 | -0.0777168 | 0.064764 | -0.0129528 | -0.0129528 |

The one-basis-point fee profiles improve reported net P&L by 0.05183159972 and
0.0518112 USDC relative to baseline. Their fees are exactly one fifth of baseline,
and their add-back-fee P&L matches the corresponding zero-fee control. Lower fees
do not make these two cases profitable. The extraction alone does not establish
identical complete execution paths across profiles, nor separate the remaining
loss into market movement, spread and slippage.

## Every selected case

Entry/close expiry here means the reported native-model reason
`simulated IOC expired before a usable quote`. It is not an actual venue order
rejection or a proven cause such as Internet outage or measured network latency.
`Unavailable` is retained for rejected/unresolved closed P&L. There is no pooled
portfolio P&L or average that drops those cases.

| Recording | Profile | Outcome | Closed net P&L, USDC | Fees, USDC |
| --- | --- | --- | ---: | ---: |
| 2 | Baseline | Entry expiry | Unavailable | 0 |
| 2 | Lower fee | Entry expiry | Unavailable | 0 |
| 2 | Zero fee | Entry expiry | Unavailable | 0 |
| 2 | Delay stress | Open short; close expiry | Unavailable | 0.03227727195 |
| 2 | Liquidity stress | Entry expiry | Unavailable | 0 |
| 2 | Slippage stress | Entry expiry | Unavailable | 0 |
| 3 | Baseline | Closed | -0.07074739965 | 0.06478949965 |
| 3 | Lower fee | Closed | -0.01891579993 | 0.01295789993 |
| 3 | Zero fee | Closed | -0.0059579 | 0 |
| 3 | Delay stress | Closed | -0.07074739965 | 0.06478949965 |
| 3 | Liquidity stress | Closed | -0.07074739965 | 0.06478949965 |
| 3 | Slippage stress | Closed | -0.0837052993 | 0.0647894993 |
| 4 | Baseline | Closed | -0.0777168 | 0.064764 |
| 4 | Lower fee | Closed | -0.0259056 | 0.0129528 |
| 4 | Zero fee | Closed | -0.0129528 | 0 |
| 4 | Delay stress | Closed | -0.0777168 | 0.064764 |
| 4 | Liquidity stress | Closed | -0.0777168 | 0.064764 |
| 4 | Slippage stress | Closed | -0.0906696 | 0.064764 |
| 5 | Baseline | Entry expiry | Unavailable | 0 |
| 5 | Lower fee | Entry expiry | Unavailable | 0 |
| 5 | Zero fee | Entry expiry | Unavailable | 0 |
| 5 | Delay stress | Closed | -0.07862140005 | 0.06468450005 |
| 5 | Liquidity stress | Entry expiry | Unavailable | 0 |
| 5 | Slippage stress | Entry expiry | Unavailable | 0 |

## Timing interpretation and next step

At request time `t`, baseline arrival is `t + 100 ms`, with opportunity window
`[t + 100 ms, t + 350 ms)`. Delay stress changes it to
`[t + 250 ms, t + 500 ms)`. Both keep a 250-ms quote wait. A later simulated
arrival can therefore encounter a different quote opportunity instead of being
a simple nested degradation of the earlier case. The original financial extraction
omitted actual opportunity times; the later [Mac diagnostic readout](mac-expiry-results.md)
supplies their reported offsets. These window formulas are model semantics.
The additional delay-stress entry on recording 5 does not prove slower delivery
improves a strategy. Recording 2's delay case retains an open short and an entry
fee, not an inferred flat return.

Next is the [read-only quote-opportunity and expiry diagnostic](expiry-review-plan.md).
The diagnostic is now implemented with existing original/derived timestamps and
explicit source references, and its [Mac readout](mac-expiry-results.md) is now
recorded. Original Mac files have not been read independently here. Do not widen
timeouts, replace expired attempts, alter fees or force-close the open case to
improve this completed probe. Any later policy/hypothesis changes are exploratory
on this already exposed archive and need separately frozen data for confirmation.

The source/engine model, original experiment result and all policy parameters
remain unchanged. The 24-hour operational gate and empirical execution
calibration remain open. No additional Mac command or new collection is needed
to accept and record this result.
