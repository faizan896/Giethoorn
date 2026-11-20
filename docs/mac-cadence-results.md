# First Mac recorded-cadence results

Status: completed Terminal readout accepted on 20 November 2026 PKT. Four unique
recordings contain 12,267 recorded BBO messages and the same 12,267 native
selected-BBO opportunities. The 12,263 within-connection intervals include 954
over 250 ms (7.779499%). This describes observation spacing in this selected
sample; it is not an order-latency or fill-probability measurement.

## Scope and provenance

The user supplied the output for
`~/GiethoornData/cadence-20261120T141248Z-s8S0zp/report`, reading diagnostic
`explain-20261120T131432Z-o7WCIL`. The issued source update was pinned to
`1253daf2b466127178a6643b654dca26ff23b6e2`. The output reports completed status,
unchanged input/code, four verified source groups, no duplicate copies,
unavailable/not-run groups, clock-step flags or error. The Terminal summary does
not include the full producer hashes or interval receipts. This workspace read
the supplied text, not the original private Mac files, and did not independently
rerun their native audit.

Children 2–5 are the same four development recordings behind the earlier cost
and expiry probes, with one connection each. Each spans about 300 seconds; their
summed source span is 1,200.285041125 seconds, about 20 minutes. These are separate
recordings, not one newly verified continuous period or a re-audit of the entire
11.5-hour archive. Six execution profiles do not multiply the observations.

The report lists 16,195 total source records. All four original policies are
combined feed, 15,000-ms depth freshness, 2,000-ms BBO freshness and 250-ms timers.
There are no raw BBO messages without a native opportunity in this readout.
No source clock-step flag means none crossed this detector's rule; it does not
establish synchronized clocks, complete venue delivery or an outage-free host.

## Reported intervals by recording

Raw-message and native-opportunity counts, bins and printed quantiles match
exactly in every recording. Times below are the original decimal milliseconds.

| Child | BBO messages | Intervals | Median | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 3,222 | 3,221 | 62.380058 | 278.634891 | 468.952876 | 1809.48066 |
| 3 | 3,096 | 3,095 | 68.292933 | 283.961471 | 439.327462 | 965.748332 |
| 4 | 2,938 | 2,937 | 72.418918 | 301.664929 | 518.646876 | 944.745926 |
| 5 | 3,011 | 3,010 | 69.031254 | 309.395476 | 472.513129 | 918.981921 |

The printed readout has no zero-time intervals. A new connection starts a new
interval domain; each of these single-connection recordings has exactly one fewer
interval than observations. Leading/trailing silence remains censored in the
full report, outside these complete-interval counts.

## Summed histogram, without joining connection clocks

The following sums existing within-connection histogram counts once per source.
It creates no interval between recordings and does not average percentiles.

| Complete interval, milliseconds | Count |
| --- | ---: |
| [0,50] | 5,172 |
| (50,100] | 2,273 |
| (100,250] | 3,864 |
| (250,350] | 588 |
| (350,500] | 268 |
| (500,1000] | 96 |
| (1000,+infinity) | 2 |
| Total | 12,263 |

There are 954 intervals over 250 ms (7.779499%), 366 over 350 ms (2.984588%)
and 98 over 500 ms (0.799152%). These percentages count intervals, not elapsed
time, independent trials or request-conditioned failures. Pooled exact quantiles
cannot be recovered from these histogram bins. Decimal calculations, bin sums,
cohort/count identities and consistency of printed nearest-rank quantiles with
their bins check here; exact quantiles cannot be recomputed without the receipts.

## Interpretation and next step

In these selected source copies, native usability filtering did not remove BBO
messages. The earlier empty quote windows therefore cannot be explained by such
filtering of an otherwise present BBO arrival in this sample. This does not prove
that the venue emitted or delivered every quote, identify the physical reason for
a recorded gap, or show that standing liquidity was unavailable during silence.

The next-fresh-quote execution model and the source cadence are distinct
assumptions. Neither the median nor these histogram percentages calibrate actual
IOC execution. The 13 earlier closed losses and unresolved short remain the
completed policy's result; no deadline, fee or fill is changed after inspection.

The next bounded engineering check is the separately frozen
[120-second fresh-capture protocol](fresh-capture-plan.md). It checks the current
recording/replay path without deliberate faults and retains the first attempt's
outcome. It cannot determine the old failure's cause or establish an economic
edge. Execution calibration still needs verified venue semantics and actual
order/acknowledgement/fill telemetry; the full-day reliability gate also remains
open. No additional Mac command is required to accept this supplied result.

Receipt and exact arithmetic checks:
`data/mac-cadence-review-20261120T141642Z-x6r49jbn/`.
