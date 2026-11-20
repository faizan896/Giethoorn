# Evaluate the fixed policy across development recordings

The [first supplied Mac evaluation](mac-development-evaluation-results.md) is
accepted: 474 verified cases, 461 conditional closes, 12 unresolved and one no
fill. All baseline closes are negative; complete profile totals remain
unavailable. No rerun is needed to accept that result.

Open Docker Desktop, install the evaluation source update and run:

```sh
bash scripts/mac evaluate quality-20261117T125619Z-mAfC1j
```

Use the original **quality snapshot**, which identifies the stopped source and
frozen development membership. The supplied Mac manifest has 79 development
children, producing 474 planned cases across the existing six profiles. The
original four cost-probed children stay labelled. No validation/test child or
replacement recording is added.

This is a broader independent-cycle economic evaluation: one first eligible
directional R001 signal after the fixed warmup per recording/profile. It does
not run every intraday signal, fit a new strategy or constitute a continuous
portfolio backtest. Policy, quantity, close rule, risk and execution assumptions
remain unchanged. Entry selection never requires a future label to be available.

## Running and viewing

The command reuses the current image/native executable, needs no new capture,
host Python/Rust, credentials or paid server, and runs with networking disabled.
It reads source/quality without writing them and creates
`~/GiethoornData/evaluation-TIMESTAMP-SUFFIX/report/evaluation.html`.
Keep Terminal open; progress prints for each selected recording, including
no-signal and unavailable children. macOS opens the portable report when finished.
Paste the final Terminal output to review the actual Mac results.

This run is larger than the four-child probe. It admits at most one hour of
work, with a 3,660-second outer timeout, a 16-GiB output cap and 1-GiB free-space
reserve. It does not require 16 GiB up front. Each new source/case must pass
space/time/output admission, including the unchanged stricter per-case checks.
If a limit stops work, remaining cases stay not-run and their profile total
stays unavailable. A hard outer timeout can leave diagnostics without final HTML.
Do not replace failed children or repeat only profitable cases.

Existing collector/monitor and `last-run` stay unchanged. An active collector
is refused before starting. Earlier negative and open cost/comparison/policy
reports remain their original results.

## Reading the result

The report shows each profile separately: planned/verified/no-signal/failed/
not-run counts, closed/open/no-fill states, positive/negative/zero closed counts,
and exact per-case fees, quantities, conditional P&L and exposure. Profile and
recording selectors retain every selected attempt. Zero fills and no signal
remain separate from zero-profit trades.

A **complete closed-cycle net** is available only when all selected cases for
that profile are verified or explicitly no-signal, none retains exposure or
pending orders, and at least one cycle closes. It sums only that profile's
closed cycles, alongside full denominators. Otherwise the total is unavailable.
Profiles are never pooled into portfolio profit, annualized returns or six
independent market samples.

Completion means the declared work was processed, not that a profitable strategy
was found. Baseline at or below zero supplies no positive evidence in the selected
cycles. A positive exploratory total alone would still require separately frozen
new-data confirmation and actual execution calibration. All original partitions
have already been explored; this is not a prospective holdout. All proxy fills
remain manual simulation, with actual venue execution unknown. The full-day
operational gate remains open.

## Evidence and acceptance

The runner binds the exact [predeclared protocol](development-evaluation-plan.md),
quality/source inventory, installed executable and producer assets. A fresh
native archive audit and unchanged quality measurements must reproduce frozen
source identity, candidate membership and span hashes. Each selected source then
gets independent native market replay and normalization before its feature is
persisted. Cases use the unchanged entry control, own-position close compiler,
complete control/final prefix comparison and independent cost verifier.

Original input snapshots, quality recheck, features, complete native ledgers,
source links, plans and receipts remain in the output. `audit-inventory.json`
binds every retained artifact; its hash/count are bound in the portable report,
keeping a large cohort's artifact list outside the HTML. Source/quality/binary/
producer changes before/after invalidate all economic metrics.

All 354 Python tests pass. New checks cover complete chronological membership,
exact per-profile sums/denominators, no-signal/no-fill/open/pending states,
forged candidate membership, input/protocol/producer changes, active source,
budget refusal, retained artifact hashes and read-only/no-network Mac launch.
Native source-to-cycle integration verifies entry without a future label,
no-signal and source-inventory rejection; existing native causal golden tests
remain unchanged and passing.

Two final ordinary-user Docker runs on a separate saved cloud sample complete
five development recordings/30 cases, all conditionally closed and negative.
Case results, financial totals and the original four-child metrics repeat exactly.
Of 1,344 bound audit artifacts, 1,343 repeat byte for byte; the sole difference
is the review receipt's creation timestamp, with every other field exact.
These are software results, not the pending 79-child Mac evaluation.

Offline Chromium verifies exact financial strings, profile/case selection,
desktop and 390/320-pixel layouts, a synthetic 79-child/474-case view, incomplete
totals, inert hostile text and exact large-integer JSON export, without browser
errors or network requests. Receipt:
`data/development-evaluation-acceptance-86c2uuwn/native-release.json`.
See [decision 0017](decisions/0017-development-evaluation.md).
