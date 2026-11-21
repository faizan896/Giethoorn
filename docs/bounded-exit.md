# Test one additional close for residual inventory

The [first supplied Mac result](mac-bounded-exit-results.md) is accepted: 474
verified cases, 12 extra attempts, 463 closes, ten unresolved and one no fill.
Both new closes are negative delay-stress cases; baseline retains two open cases.
No rerun is needed to accept that result.

The [frozen protocol](bounded-exit-plan.md), experiment
`r001-bounded-exit-002`, permits at most one extra close after the original close
has settled. It uses the position already known at the next eligible native BBO.
The signal, entry, first close, protective price limits, execution assumptions and
risk rules stay fixed. This tests exposure handling on explored development data;
it does not establish a profitable strategy or guarantee flat inventory.

Open Docker Desktop, install the bounded-exit source update and run:

```sh
bash scripts/mac bounded-exit quality-20261117T125619Z-mAfC1j
```

Use the original quality snapshot. Its entire frozen development cohort remains
selected: the supplied Mac cohort has 79 recordings and 474 cases under six
profiles. The 13 diagnosed exceptions are not selected in isolation. The existing
image is reused offline; no new capture, image rebuild or credentials are needed.

## Running and viewing

Keep Terminal open. Progress prints per selected recording, followed by summary,
baseline and extra-close case results. macOS opens the portable report at
`~/GiethoornData/bounded-exit-TIMESTAMP-SUFFIX/report/bounded-exit.html`.
The first supplied output is now [accepted](mac-bounded-exit-results.md). The
earlier [single-close result](mac-development-evaluation-results.md) remains
461 closed, 12 unresolved and one no-fill case with negative baseline closes.

The runner reads stopped source/quality without writing them and leaves existing
collector, monitor and `last-run` selection fixed. It refuses an active collector.
Output admission is capped at 16 GiB with a 1-GiB free reserve, one hour of suite
work and a 3,660-second outer timeout. It does not reserve 16 GiB up front.
Existing stricter native/source/case limits remain enabled. Refused, failed and
not-run cases stay in their original denominators without replacement; a hard
timeout may leave diagnostics without final HTML.

## How the optional request is chosen

The original one-close control is replayed first. The first close must be terminal,
with no working order or outstanding cancellation. Scan source in receive order
after its anchor for the first newly accepted, fresh BBO on the acknowledged
connection. Include native actions already known at that moment and exclude later
source/actions, including later events with equal timestamps. A native risk halt
stops the retry. An absent first close does not create a new close decision.

For nonzero inventory, exact signed fills must reproduce the position already
known at that prefix. Its absolute quantity cannot exceed the entry already filled
or the original target. The extra request uses precisely that opposite-side
quantity and the unchanged protective limit formula. Persist the decision before
replay and require the complete native prefix before `close-retry` to equal the
control. An independent Decimal/source check verifies quantity, side, anchor and
limit. There are at most three requests: entry, first close and optional extra.

The extra attempt can still be unmarketable, rejected, partial or pending beyond
recorded source end. Its exposure remains explicit. There is no further retry,
forced price, limit widening, invented liquidity or replay beyond source EOF.
The report distinguishes source-time waiting from assumed order latency.

## Reading the comparison

Each selected case retains the original one-close outcome alongside its new
decision, exact quantities, fees, pending orders and ending exposure. Only cases
closed on both sides have a conditional closed-net difference. Resolving an open
case does not manufacture a return comparison against its previously unavailable
closed P&L. Added fees remain visible.

Profiles stay separate. A complete net total requires every selected case to be
accounted for, no remaining exposure/pending order and at least one closed cycle.
Unknown outcomes do not become zero-return trades. No profile pooling or portfolio
return is computed. All fills remain manual simulation; actual execution is unknown.
R001's previous negative economic result, the full-day reliability gate, execution
calibration and later frozen new-data confirmation remain separate.

## Software acceptance

All 405 Python tests pass, including 28 native bounded-exit checks. The same 28
checks also pass inside the unchanged Mac Docker image. A retained synthetic native
fixture closes 0.00025 BTC first and requests/fills only the remaining 0.00075 BTC;
it finishes flat with conditional net `-0.000140000001` USDC. Other fixtures retain
partial/pending exposure, missing quotes, risk rejection and source-end states.

Two ordinary-user Docker trials on the separate saved cloud sample verify all
five development recordings/30 cases. Its original controls already close, so it
issues zero extra requests. All 30 controls equal the accepted original evaluation;
complete cases/totals repeat exactly. Each trial binds 1,464 audit files; 1,463
repeat byte for byte. Only `reviewed_at_utc` in the quality review receipt differs,
with every other field exact. Source, quality, old producers, native executable,
Docker image and the frozen protocol remain unchanged.

Offline browser checks cover exact original/new values and JSON export, native
partial-fill output, desktop and 390/320-pixel views, and a labelled synthetic
474-case layout. They retain failed/pending/unresolved states and unavailable
totals, with no browser errors or network requests. Desktop fixture and mobile
screenshots were visually reviewed. Receipt:
`data/bounded-exit-acceptance-ecwx2mrn/native-release.json`.
No private Mac recording was accessed and no new public data was captured here.
The subsequent supplied Mac readout is accepted separately above.
See [decision 0018](decisions/0018-bounded-exit-experiment.md).
