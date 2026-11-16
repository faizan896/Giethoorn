# Decision 0006: bounded offline execution sensitivity

## Scope and versions

Batch manifest version 1 and batch report version 1 orchestrate existing paper
model 3. Market-event schemas, paper inputs, accounting and execution semantics
are unchanged. This tests fixed protocol scenarios against declared assumptions;
it is not empirical calibration, strategy selection or a trading return report.

The manifest declares a baseline, 1–8 datasets, 1–8 profiles and at most 32 cases.
Each dataset supplies a finalized segmented recording, fixed scenario, explicit
`captured_public_data` or `synthetic_fixture` origin, and BBO/depth selection.
Each profile supplies the complete five execution assumptions. Unknown fields,
duplicate JSON keys/IDs, ambiguous case IDs, missing baselines, unsupported
origins, non-decimal financial strings and out-of-range limits are rejected.
Paths resolve relative to the manifest. IDs are bounded lowercase ASCII tokens;
`--` is reserved for the case separator.

## Freeze inputs before comparing results

The runner requires a new output directory and pins the supplied native binary
there. Each recording passes the existing native mark-only export into a frozen,
validated source copy. Every case uses that copy. The original base scenario is
retained, including its raw-byte fingerprint. A separate fixed-plan fingerprint
covers every field other than `assumptions`. Profiles replace only that field;
order anchors, prices, quantities, risk settings, collateral and labels stay fixed.

Each case goes through `paper_execution.generate` without its optional HTML.
Source/scenario provenance, independent Decimal cost verification and exact native
ledger replay still run. Subprocesses have finite timeouts. `subprocess.run`
kills and reaps a timed-out direct child; these native offline commands create no
descendant workers. This is a finite foreground command, not a background service.

## Result interpretation

The full dataset × profile matrix always appears in the report. A verified case
contains exact string-valued costs, account values, counts, ending position,
pending IDs, source end reason and provenance. Failed and not-run cases have
`metrics: null`, an explicit reason and no invented zero result. A verified
simulation can use a valid recording whose historical source ended `failed`;
the source end reason remains visible and does not become a passed collector gate.

Comparisons pair each case only with its own recording's declared baseline.
Deltas are exact Decimal differences in net P&L, fees, spread and slippage. They
are unavailable unless both cases verify, and missing valuations remain null.
The execution-path fingerprint covers fill IDs, sides, quantities and original
source-event anchors, plus final order states and pending IDs. It excludes fill
prices and fees. Flags separately identify changed paths, ending inventory and
pending orders. Therefore a fee/slippage-only comparison with the same path is
distinguishable from a delay/liquidity comparison with changed exposure.

Open inventory uses its final historical mark; no closing fill is invented.
Spread/slippage decomposition is already in fill prices, not charged twice.
There is no aggregate portfolio P&L, annualized metric, profit ranking, selected
winning profile or claim of measured venue latency/liquidity. The report sets
`calibrated`, `strategy_enabled` and `full_window_verified` to false.

## Resource limits and incomplete runs

Manifest limits bound output admission (256 MiB–2 GiB), minimum free space
(at least 1 GiB), each native subprocess (1–600 seconds) and suite admission
(1–3,600 seconds). Admission checks reserve 64 MiB per source snapshot, 128 MiB
per execution case and 4 MiB for JSON/HTML. The existing native record and derived
file bounds underpin those conservative allowances. A case's two child timeouts
are capped to half the remaining suite time.

These are checks between bounded operations, not a kernel filesystem quota or
hard wall-clock supervisor for Python/filesystem stalls. The report states this
limit. Exhausted admission budgets leave later rows `not_run`; earlier verified
results and partial diagnostics remain. All attempted cases with failures yield
`completed_with_failures`; any unrun case yields `incomplete`. Only an entirely
verified matrix exits zero. A killed runner or full filesystem may retain only
partial artifacts; the presence of a directory is not completion evidence.

## Review surface

`batch-report.json` retains manifest/binary fingerprints, frozen-source receipts,
case artifacts, profiles, paired deltas, counts and operational timing. The
self-contained `batch-lab.html` uses the shared Giethoorn theme. Filters and case
selection do not recompute accounting. Money stays in exact decimal strings;
the page makes no network requests. Invalid-case browser fixtures are explicitly
synthetic. The monitor optionally serves one configured report at `/batch`; GETs
never execute the runner, and POST/arbitrary file paths remain unavailable.

## Acceptance evidence

Unit tests cover strict manifests, fixed plans, frozen inputs, exact paired
differences, missing baselines/valuations, timeouts, budgets, visible failures,
existing-output refusal and escaped embedded data. The actual matrix runs all
five profiles on four saved BTC sessions, including a network-affected source.
Browser acceptance checks filters, exact figures, keyboard selection, JSON export,
synthetic failure rendering, zero offline requests, mobile layouts and loopback
navigation. See the current [handoff](../status.md) for exact artifacts/results.
