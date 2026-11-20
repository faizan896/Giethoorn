# First supplied Mac causal policy result

Status: the supplied Terminal readout completed on 21 November 2026 PKT.
All 24 cases are reported verified and conditionally closed, with no remaining
position or pending order. All 24 net results are negative, including the four
zero-fee controls. The close mechanics work in these reported cases; there is
no positive economic evidence for this policy in this small sample.

## Scope and verification

The user supplied the compact output for
`~/GiethoornData/policy-20261120T205853Z-yJVYPu/report`, following the issued
`099faeb` source update. The artifact's UTC identifier corresponds to
21 November in Asia/Karachi. Policy ID is `r001-known-book-causal-001`, reading
the original cost snapshot `cost-20261120T115202Z-fKjWVP`. Selected children
remain 2–5 under the same six profiles. Input/code are reported unchanged, with
no error, unavailable or not-run case. Actual venue execution remains unknown.

This workspace read the supplied text, not the original private Mac source,
native ledgers, close receipts or control prefixes. Cohort membership, reported
position/quantity identities, order counts, exact Decimal fees and the printed
net arithmetic were independently checked here. Native integrity and causal
prefix verification are reported by the local runner, not independently replayed
in this review. The compact output does not include native order sides; its
reported decision-position sign supplies the directional arithmetic check.

## Lifecycle result

There are 24 entries and 24 own-position closes, all with reported full
0.001-BTC fills. Every requested close equals the absolute decision-time position;
its reported final position is zero and its pending-order list empty. Recordings
2, 3 and 5 report short positions at the decision; recording 4 reports long.
All 24 causal-prefix checks are reported verified.

The [previous fixed-request comparison](mac-model-comparison-results.md) remains
its own completed result: 14 conditionally closed cases and ten open hypothetical
shorts. The new policy compiles the ten closes absent from those original fixed
plans. The 14 common closed cases retain exactly the same printed net, fees,
fill prices and reference ages. All ten additional conditional closes also lose
money. No return improvement is computed against their previous unavailable
closed P&L, and the old reports are not relabelled or overwritten.

Reported reference ages range from 10.473161 to 247.802433 ms. These are ages of
quotes used at assumed arrival, not measurements of actual order latency or
evidence that displayed liquidity was executable. There are four source cycles
with six sensitivity profiles each, not 24 independent market samples, nor
simultaneous funded positions or a pooled portfolio return.

## Costs and results

All amounts below are exact reported USDC values. The zero-fee column matches
baseline net plus fees for each recording. It still includes the spread and
assumed adverse slippage embedded in fill prices; it is not the signal's
midprice return or a zero-cost execution claim.

| Recording | Position at decision, BTC | Baseline conditional net | Baseline fees | Zero-fee conditional net |
| --- | ---: | ---: | ---: | ---: |
| 2 | -0.001 | -0.07046899965 | 0.06455749965 | -0.0059115 |
| 3 | -0.001 | -0.07074739965 | 0.06478949965 | -0.0059579 |
| 4 | 0.001 | -0.07871620005 | 0.06476350005 | -0.0139527 |
| 5 | -0.001 | -0.07862140005 | 0.06468450005 | -0.0139369 |

Every order's fee equals printed assumed price × filled quantity × the unchanged
profile fee rate. The two fees sum exactly to the case total. For every case,
`(close price - entry price) × reported signed position - fees` equals reported
conditional closed P&L. All 24 remain negative after adding fees back. The
lower-fee controls do not make any selected cycle profitable; `0E-7` is exact
Decimal zero. This readout does not separate spread/slippage from price movement
or identify an actual venue execution cost.

Recording 4 delay stress remains `-0.0777168` net with `0.06476400000` fees;
its assumed exit price differs from baseline. That single path is not evidence
that delaying orders improves performance. Existing profiles are retained as
assumptions, without selecting a preferred delay from observed results.

## Decision and next research step

Accept this bounded causal-policy mechanics result and preserve the negative
economic result. No additional Mac command, rerun or capture is needed to accept
it. This evidence does not justify promoting R001 to live trading, claiming an
economic edge or tuning fees, timing or signal thresholds to turn these exposed
cases positive. Four cycles also cannot establish general strategy performance.

The next research stage is a separately specified cost-aware evaluation across
a broader chronological development cohort. Freeze its policy, cohort, outcome
handling, bounds and comparison criteria before running it. Entry selection
must use information available at the feature, preserve missing/unresolved
outcomes and keep the six sensitivity profiles separate. Confirmation of any
later candidate requires new frozen recordings after its policy is locked.
The full-day operational gate and empirical execution calibration remain open.

Receipt: `data/mac-causal-policy-review-20261120T212334Z-w1k7xswr/`.
This acceptance changes documentation only. Runtime helpers, native binaries,
producer assets, recordings and all prior economic artifacts remain unchanged.
