# First Mac quote-window diagnostic

Status: the user completed the saved-snapshot diagnostic on 20 November 2026.
Terminal output reports 24 verified cases, 38 original orders, 27 full fills and
11 expiries, with no unavailable/not-run cases and unchanged input/code. These
are order lifecycle counts, not counts of profitable trades or independent market
samples. The prior 13 closed losses and one unresolved paper short remain intact.

## Evidence and count consistency

The uploaded Terminal transcript refers to
`~/GiethoornData/explain-20261120T131432Z-o7WCIL/report`, reviewing cost snapshot
`cost-20261120T115202Z-fKjWVP` with pinned diagnostic release
`04dd2d2a23b130b9edfc27f9f9de99ccd689024a`. This workspace read the supplied text,
not the original Mac report/recordings. Native checks were reported as having
passed on the Mac; this receipt is not a separate cloud audit of those files.

The counts agree with the preceding cost readout:

- 24 requested entries: 14 filled and ten expired.
- 14 requested closes: 13 filled and one expired.
- 38 total requests: 27 filled and 11 expired. No additional close was invented
  for any rejected entry.

All 11 printed expiry rows have zero recorded BBO messages and zero native usable
opportunities inside their declared windows. Their first subsequent native usable
quote is also the event on which expiry was observed. This does not insert a
timer or rejection event at an unobserved deadline.

## Three request timelines explain all 11 expiry rows

Every time below is relative to the original request, in exact milliseconds.
The expiry boundary is exclusive. Beyond-expiry amounts were recomputed with
Decimal from the reported strings.

| Recording / order | Profiles sharing request | Request sequence | Assumed arrival | Exclusive expiry | First usable quote / observed expiry | Beyond expiry |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 / entry | 5 | 67 | 100 | 350 | 457.340925 | 107.340925 |
| 5 / entry | 5 | 66 | 100 | 350 | 399.731028 | 49.731028 |
| 2 / close, delay stress | 1 | 83 | 250 | 500 | 515.613957 | 15.613957 |

The five entry profiles in each group are baseline, lower-fee, zero-fee,
liquidity-stress and slippage-stress. They share the same original request and
arrival/expiry window. Five rows therefore repeat one market timeline; they are
not five independent observations of a connection or venue problem.

Both entry quotes fall inside the delay-stress `[250,500)` ms window, while
missing the baseline `[100,350)` ms window. This is consistent with the earlier
reported delay-stress entry fills and explains the shifted-window effect. The
delay-stress close on recording 2 then misses its own +500-ms boundary. Its
-0.001-BTC paper short remains unresolved; no closing price or return is inferred.

## What the diagnostic establishes

The observed expiry decisions agree with the declared next-fresh-quote IOC
model. A request was still waiting when the first resolving recorded event
crossed its deadline, with no eligible quote inside the window. The observed
quote offset is not measured order-network latency or an exchange acknowledgement.

An empty message window also does not establish that the venue had no executable
liquidity between messages. A public quote stream and an actual order/matching
channel are different measurements. Quiet/event-dependent publishing, transport,
recording behavior and machine suspension remain unproven explanations here.
The supplied diagnostic deliberately reports component cause as unknown.
Three timing groups do not establish a general feed cadence or a safe timeout.

The earlier zero-fee closed controls are still negative with spread and assumed
slippage included. Explaining or widening an expiry window cannot by itself
establish an economic edge. This completed policy's settings and results stay
frozen; any later policy change is a new exploratory version.

Next is the [recorded-feed cadence calibration protocol](feed-cadence-plan.md),
starting from the existing unique source copies. Its exporter is not implemented.
It will measure message/opportunity intervals without changing trade outcomes or
calling those intervals order latency/fill probability. A later bounded fresh
capture may check recording behavior after its settings are fixed; the full-day
reliability gate and execution calibration remain separate outstanding work.

Receipt and exact arithmetic checks are under
`data/mac-expiry-review-20261120T132011Z-6vcr3rr5/`. No new collection, image build,
Mac command or change to the original artifacts was needed to accept this result.
