# R001 retrospective prediction results

Status: all three original partitions have been evaluated without changing the
fixed prediction rules. This closes the first retrospective prediction study;
it does not establish economic viability or a completed operational day window.

These values come from the user's Mac Terminal outputs. Source and quality were
reported unchanged for each run. Count identities and displayed rounding were
recomputed here; the original Mac reports/recordings have not been read directly
in this cloud workspace.

| Partition | Children | Hits / labelled signals | Hit rate | Always up / down | Mean signed mid move, bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 79 | 457 / 882 | 51.8141% | 25.5102% / 30.3855% | 0.5113 |
| Validation | 26 | 193 / 340 | 56.7647% | 24.7059% / 36.1765% | 0.4396 |
| Retrospective test | 28 | 247 / 459 | 53.8126% | 29.6296% / 29.4118% | 0.4813 |

Means in this table round the reported 12-decimal aggregate to four places.
Unchanged outcomes count as misses. The constant-direction controls use the
same labelled directional-signal subset as the predictor, not all source events.

| Partition | Directional signals | Available signal labels | Missing signal labels |
| --- | ---: | ---: | ---: |
| Development | 3,392 | 882 (26.0024%) | 2,510 (73.9976%) |
| Validation | 1,143 | 340 (29.7463%) | 803 (70.2537%) |
| Retrospective test | 1,261 | 459 (36.3997%) | 802 (63.6003%) |

The direction-score pattern is present in each available subset, but most signal
attempts lack a label under the fixed data-quality rules. This missingness can
select a different market/data regime. The observations can also be correlated.
These percentages do not establish statistical significance or performance over
all attempts. No execution, fee, fill, position or trading P&L was evaluated.

For a count-consistency check only, the partitions contain 8,029 samples, 5,796
signals, 2,233 abstentions, 1,681 labelled signals and 4,115 missing signal labels.
Their eligible BBO counts sum to 330,784, matching the earlier quality summary.
This is not a pooled validation score or a portfolio return.

## Cost hurdle

The final group's reported mean is 0.481330588510 bps, or 0.00481330588510%,
before any execution costs. The existing synthetic IOC example declares a
`fee_rate` of `0.0005`: five basis points per filled notional. Two equal-notional
filled legs would cost ten basis points in fees alone. This is an illustrative
assumption from the existing model, not a measured venue/account fee quote.

That scale is much larger than the reported midprice movement. Subtracting it
from a selected-subset price metric is not an execution backtest or actual net
P&L: entry/exit times, touch prices, spreads, partial fills, liquidity, latency,
missing outcomes and unresolved exposure still need modeling. Do not assume
only the retrospectively labelled signals were tradable.

## Evidence and next step

Local study directories under `~/GiethoornData/` are:

- `study-20261117T142333Z-iWDe6F`: development.
- `study-20261117T143648Z-Wt5dIy`: validation.
- `study-20261117T150110Z-EitFd9`: retrospective test.

All refer to frozen quality snapshot `quality-20261117T125619Z-mAfC1j`.
Arithmetic receipts and the explicitly non-execution fee-hurdle worksheet are
under `data/mac-final-study-review-20261117T150945Z-2cn_m0xu/` in this workspace.
They retain user-terminal provenance rather than recreating native study reports.

All original partitions are now explored. New rules or economic-policy choices
may use this data for exploratory work, but cannot call it untouched test data.
See [the next cost-study specification](cost-study-plan.md); later confirmatory
testing needs separately frozen recordings after those choices are locked.
