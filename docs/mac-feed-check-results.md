# First supplied Mac fresh-recording result

Status: the supplied Terminal readout completed successfully on 20 November 2026
PKT. Capture, retained-source integrity, exact live/replay comparison and cadence
all report success. This checks the current recording/replay path for one short
session; it does not complete the operational day gate or establish profitability.

## Scope and provenance

The user supplied the output for
`~/GiethoornData/feed-check-20261120T182132Z-NC9jvd/offline/report`, following the
issued source update pinned to `e8352c6389740ccf492d01985c99e1d4b0c21fd6`.
Origin is explicitly `captured_public_data`. The capture requested 120 seconds,
exited 0 and reported neither timeout nor interruption. The offline readout
reports unchanged input/code, no error, verified integrity/replay/cadence,
1,654 source records and one connection.

The recorded source span is 120.006931974 seconds. The supplied readout lists
1,256 raw BBO messages and exactly matching native opportunities, forming 1,255
complete within-connection intervals. It reports zero source clock-step flags.
That means no discontinuity met the configured detector, not synchronized clocks,
complete venue delivery or a diagnosis of the old power/network/deadline failure.

This workspace received the pasted Terminal message, not the original private
Mac recordings, fingerprints or interval exports. The receipt normalizes the
reported fields and recomputes count/Decimal consistency; it is not an independent
cloud native audit of those files or a recomputation of exact source quantiles.

## Reported timings

Raw-message and native-opportunity counts, printed quantiles and histograms match.
All times below are milliseconds.

| Statistic | Reported value |
| --- | ---: |
| Median | 71.769354 |
| p95 | 290.494621 |
| p99 | 455.770042 |
| Maximum complete interval | 670.114407 |

| Complete interval | Count |
| --- | ---: |
| [0,50] | 533 |
| (50,100] | 216 |
| (100,250] | 414 |
| (250,350] | 55 |
| (350,500] | 30 |
| (500,1000] | 7 |
| (1000,+infinity) | 0 |
| Total | 1,255 |

There are 92 intervals over 250 ms (7.330677%), 37 over 350 ms (2.948207%) and
seven over 500 ms (0.557769%). These are fractions of complete intervals, not
fractions of elapsed time, independent trials or order fill/failure probabilities.
Initial/tail silence remains censored rather than an invented completed interval.
Count/bin identities and printed quantiles' nearest-rank/bin consistency check.

The new median/p95/p99 sit within the per-recording ranges from the
[earlier four-source readout](mac-cadence-results.md). This is a descriptive
comparison between different selected sessions. The fresh maximum is smaller
than the earlier 1,809.48066-ms maximum; a two-minute sample does not prove a
permanent improvement or identify a cause. These samples are not pooled into
statistical confidence or a new economic evaluation cohort.

## Next engineering work

The short capture/replay check is complete. Another capture is not needed to
accept this result. Native usability filtering did not remove a raw BBO arrival
in this sample. The observed gaps still do not establish actual order timing or
the availability of standing venue liquidity between public messages.

The next work is the [offline execution-model assumption review](execution-model-review.md):
separate the existing next-new-quote rule from a proposed arrival-book proxy,
retain explicit uncertainty and version any new behavior before use. No old
timeout, fill, fee, negative closed result or unresolved exposure is rewritten.
The 24-hour reliability gate, real execution calibration and future frozen-data
economic confirmation remain open.

Receipt: `data/mac-feed-check-review-20261120T182656Z-zebs11k4/`.
