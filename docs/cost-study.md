# Costed R001 paper probe

This bounded offline experiment tests execution mechanics and assumed costs on
already explored recordings. It is separate from the completed direction-score
study and from the outstanding full-day reliability gate. It sends no live orders
and needs no wallet, API credentials, new collection or paid server.

## Run on the Mac

After installing the source update, open Docker Desktop and run from your existing
`Giethoorn-mac-local-setup` directory:

```sh
bash scripts/mac cost quality-20261117T125619Z-mAfC1j
```

Use the identifier of your frozen quality snapshot. Its saved source selection
chooses the original recording archive even if `last-run` now names another run.
The collector must be stopped. The launcher reuses `giethoorn-local:0.1.0`; it
does not rebuild the image, resume collection or change any historical run.
The original archive, quality evidence and helper source are mounted read-only;
Docker networking is disabled. Allow about 3 GiB of free disk space for the
bounded report and its reserve. Normal small recordings use much less; a retained
report may be incomplete when its time/storage allowance cannot admit all cases.

The HTML opens automatically and all evidence is retained in a new
`~/GiethoornData/cost-TIMESTAMP-SUFFIX/report/` directory. Reopening `cost.html`
needs no server or connection. A failed/incomplete run retains diagnostics and
opens its report when one could be written. An outer process timeout or abrupt
Docker shutdown may leave only partial evidence, with no completed report.

The required source files are `scripts/mac`, `ops/cost_core.py`,
`ops/cost_local.py`, `ops/paper_execution.py`, `ops/study_core.py`,
`ops/study_local.py`, `ops/review_local.py`, `ops/quality_local.py`,
`web/quality.html` and `web/cost.html`. Keep the quality verifier, template and
theme versions that created the frozen snapshot. Their exact fingerprints and
the native executable must match. The original Mac study setup already contains
those frozen dependencies; install the supplied cost update without rebuilding.

## Read every outcome

The first four development candidates in frozen chronological order are selected
before any outcome is calculated. Each uses the first directional R001 feature
after five seconds. There is one attempt per recording/profile and no replacement
signal after a rejection or no fill. Recordings without a signal, oversized inputs,
failed cases, and cases not admitted by budgets stay visible rather than being
replaced by a later recording or counted as zero-return successes.

Each profile starts independently flat with 10,000 USDC of paper collateral.
The fixed entry target is 0.001 BTC, with the [declared risk and execution
assumptions](cost-study-plan.md). The 100-USDC order cap may reject that target at
high BTC prices; the runner reports the rejection rather than silently resizing
or changing the policy. The close attempts only the actual known entry fill, at
the first usable recorded BBO state at least one second after the feature.
Late close decisions retain their delay. A gap creates no synthetic timer/fill.

- **Closed:** an entry filled and the known inventory was fully closed with no
  pending orders. Net P&L is realized P&L minus fees, in USDC. A partial entry that
  was completely closed can qualify; its smaller quantity remains explicit.
- **Unresolved:** inventory or pending orders remain. Closed-case P&L is
  unavailable. Open exposure and a clearly historical mark/P&L are retained;
  neither is a current or executable valuation. A rejected/partial close or missing
  close decision does not fabricate a flat position.
- **Entry rejected / no entry fill:** the attempt is retained, with status and
  rejection reason. No close is manufactured. Closed-case P&L stays unavailable.
- **No signal / failed / not run:** no admitted execution score. Inspect the
  diagnostic; do not infer zero P&L or choose a replacement recording.

The case inspector shows entry/close quantities and states, risk halt, pending
order IDs, historical exposure, costs and differences from the same recording's
baseline. Spread and slippage are already embedded in fill prices; their
decomposition is not debited again. Fee-only changes need not change the execution
path. Liquidity/delay changes can change entry quantity and thus causal close
quantity; this suite compares a fixed policy rather than a fixed order list.

Counts include every selected case. There is no combined portfolio P&L, return
percentage or annualization across independent starts, and no success rate that
drops unresolved cases. Assumptions remain uncalibrated: public displayed sizes
do not guarantee fills; actual venue increments/minimums, fee tiers, private order
reconciliation and real execution latency are outside this model.

## Evidence and local verification

`cost-policy.json` fixes rules, six profiles and bounds. `input-quality/` retains
the original evidence; `quality-check/` contains a fresh native archive audit and
quality computation. `replay.bin` pins the executable. Selected feature receipts
are written before running their profiles. Each case retains:

- `entry-scenario.json` and independently audited entry-only `control/` replay;
- `causal-prefix.json`, including decision boundary, known position and prefix hash;
- `compiled-scenario.json`, and `compiled/` when an actual close was added;
- native paper inputs, source links, execution trace, independent Decimal cost
  audit, exact ledger replay and `case-result.json`.

An entry-only control is reused when no close was compiled. Final report
provenance identifies that choice. Adding a close must preserve the control's
entire prefix through the decision before requesting the close. Original source,
quality, executable and helper/template hashes are rechecked after the suite;
changes invalidate admitted metrics. `bundle-inventory.json` fingerprints retained
input/case artifacts. It is an integrity receipt, not proof that public data or
execution assumptions came from an authenticated venue.

Run Python checks with `python3 -m unittest discover -s ops -p 'test_*.py'`.
Native synthetic cases use `target/debug/giethoorn` when present, or an explicit
`GIETHOORN_TEST_BINARY`; without either, those native tests are reported skipped.
They check hand-calculated costs, partial long/short entry and exit, no over-close,
expiry, risk rejection/loss halt, unresolved source-end state, late decisions,
future-price independence, exact repetition and source preservation. Browser
checks use `web/check_cost_browser.py` against a completed saved report.

These recordings are already explored. New policy choices require a separately
frozen later sample for confirmatory evaluation. A completed probe establishes
bounded software behavior, not profitability or readiness for funded execution.
