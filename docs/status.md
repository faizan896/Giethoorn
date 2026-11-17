# Development handoff

The initial environment was published by the user and its working files and
toolchain were restored in the current Linux machine. No further configuration
changes or publication have been performed. The latest source changes remain
available as a local source snapshot for review and transfer. Original recordings
and validation artifacts are separate from repository source. No live exchange
execution or wallet functionality exists. An offline paper research model is
described below.

## R001 retrospective study closed, 17 November 2026 PKT

The user completed the 28-child retrospective-test partition, reporting completed
status, unchanged source/quality and no error. Local evidence is
`~/GiethoornData/study-20261117T150110Z-EitFd9/report`, using the same frozen quality
snapshot. Original Mac files have not been accessed here; the supplied Terminal
result was checked arithmetically and retained with explicit user-report provenance.

Final-test counts are 1,688 samples, 1,261 directional signals and 427 abstentions.
There are 459 labelled signals (36.3997%), 802 missing signal labels (63.6003%),
247 hits and 188 unchanged outcomes. Hit rate is 53.8126%; the same-subset
always-up/down controls are 29.6296%/29.4118%. Mean signed midprice movement is
0.481330588510 bps (0.00481330588510%) before costs. Across all samples, 574 labels
are available and 1,114 missing: 1,093 gap-rule and 21 unusable-feed cases. There
are 323 sampling bins without an eligible BBO; no missing intervals were filled.

The [three-partition comparison](r001-results.md) records 51.8141%, 56.7647% and
53.8126% hit rates on the respective available directional subsets. Raw signed
means remain only 0.44–0.52 bps, with 64–74% of signal labels unavailable.
Summed eligible BBO observations equal the original quality total, 330,784.
Count totals are integrity checks, not a pooled validation or portfolio return.
All original partitions are now explored; none can be called untouched for new
rules or economic-policy choices. No prediction rule or cohort was tuned.

The existing illustrative IOC fee assumption is five bps per fill. Two equal-
notional filled legs imply ten bps of fees, much larger than the reported raw
movement. An explicit fee-hurdle worksheet is arithmetic only, not an execution
backtest or net P&L; actual fees, spread, fills, latency and missing-exposure paths
are not measured. The [costed-probe specification](cost-study-plan.md) is now
prepared; its policy compiler/runner is not implemented. It requires causal
actual-fill-sized closes and retention of rejects, partial fills and open exposure.

Receipts/comparison/fee worksheet:
`data/mac-final-study-review-20261117T150945Z-2cn_m0xu/`. No Mac runtime update or
new collection was needed for this comparison. Future confirmatory economic
evaluation needs separately frozen later data after its policy is locked. The
24-hour operational gate, execution calibration and profitability remain open.

## Mac validation study accepted, 17 November 2026 PKT

The user completed the unchanged fixed study on the 26 validation children,
reporting `status: completed`, source/quality unchanged and no error. Local
evidence is `~/GiethoornData/study-20261117T143648Z-Wt5dIy/report`, using the same
quality snapshot `quality-20261117T125619Z-mAfC1j`. This is acceptance from supplied
local Terminal output; original Mac files have not been read in this workspace.

There are 1,575 samples: 1,143 directional signals and 432 abstentions. Labels
are available for 340 signals (29.7463%) and missing for 803 (70.2537%). Across all
samples there are 448 available and 1,127 missing labels, with 1,111 gap-rule and
16 unusable-feed exclusions. All count identities and displayed rounding check.

On the same 340 labelled signals, 193 hits give 56.7647%, versus always-up
84/340 (24.7059%) and always-down 123/340 (36.1765%). There are 133 unchanged
outcomes, counted as misses. Mean signed midprice change is 0.439610943767 bps
(0.00439610943767%) before execution costs. The direction-score pattern persists
in this separate group, while mean movement is smaller than development and most
signal outcomes remain unavailable. Selection from missing labels, correlation
and costs still prevent a significance, tradability or profit conclusion.

Rules and cohorts remained unchanged. The subsequent final 28-child retrospective
result is now recorded above, with no tuning or new code/download. Arithmetic receipt:
`data/mac-validation-review-20261117T143905Z-480ed7gd/terminal-observation.json`
(user-terminal provenance, not reconstructed native evidence). Economic testing
and the operational day gate remain outstanding.

## Mac development study accepted, 17 November 2026 PKT

The user completed the fixed development run and supplied `status: completed`,
`source_unchanged: true`, `quality_unchanged: true` and no error. The local evidence
is `~/GiethoornData/study-20261117T142333Z-iWDe6F/report`, using the existing frozen
quality snapshot `quality-20261117T125619Z-mAfC1j`. Original Mac files have not been
read in this cloud workspace; acceptance is based on the supplied local output.

The 79 development children produced 4,766 samples: 3,392 directional signals and
1,374 abstentions. Only 882 signals have labels (26.0024%); 2,510 signal labels
are unavailable (73.9976%). Across all samples, 1,183 labels are available and
3,583 unavailable: 3,533 on the fixed 250-ms gap rule and 50 on unusable feeds.
All count identities and reported rounding were independently recomputed here.

On the 882 labelled signals, 457 hits give 51.8141%, versus always-up 225/882
(25.5102%) and always-down 268/882 (30.3855%). Unchanged outcomes are 389/882
and count as misses. The mean signed midprice change is 0.511285753366 bps
(0.00511285753366%) before any execution costs. These descriptive development
results beat the constant-direction controls on the available subset; the large
missing-label share can select a different market/data regime. They do not
establish significance, tradability or profitability across all signal attempts.

No rule, threshold, horizon or partition changed after viewing this result.
The subsequent 26-child validation and final 28-child test are recorded above.
No update, collection or rebuild was
required for validation. Arithmetic receipt:
`data/mac-development-review-20261117T142816Z-ky2946j0/terminal-observation.json`
(explicitly user-terminal provenance, not a reconstructed native study report).
The operational day gate and economic testing remain outstanding.

## Fixed prediction study and Mac quality acceptance, 17 November 2026 PKT

The user completed the Mac quality command and supplied a successful local result:
134 retained recordings, 133 finalized candidates, one excluded recovered prefix,
334,794 retained observations and 330,784 usable BBO observations. Its 6,523
qualifying spans sum to 14,931.944878902 seconds (4h 8m 51.945s), as separate spans,
not continuous coverage. The frozen child split is 79 development / 26 validation
/ 28 retrospective test. Source is unchanged and no quality error is reported.
Local evidence: `~/GiethoornData/quality-20261117T125619Z-mAfC1j/report`.
These are user-supplied local results; the Mac files have not been read here.

Run 134 reports 1,818.492983278 seconds of process time, 1,818.387945625 seconds of
recorded time and a 1,585.466088153-second maximum event gap (26m 25.466s).
No wall-minus-monotonic discontinuity was detected. This identifies a large gap
excluded from qualifying spans; it does not establish the component/cause of the
stall. The historical watchdog/day failure remains unchanged.

The fixed prediction study is now implemented. `bash scripts/mac study
quality-20261117T125619Z-mAfC1j` selects that frozen snapshot/source and defaults
to development only. It rechecks source/quality fingerprints, native audit,
domain and membership; then records causal version-1 features and labelled or
explicitly missing outcomes. Other partitions stay unrun with null metrics.
The portable report compares the signal against constant-direction controls on
the same labelled-signal subset. No orders or economic returns are evaluated.
See [study instructions](study.md) and [decision 0010](decisions/0010-fixed-signal-study.md).

Validation passes 126 Python tests, shell checks and offline browser checks.
The complete ordinary-user launcher passes twice with identical feature/sample
bytes and unchanged source/quality evidence. Its small separate cloud sample
has 15 development samples, 9 directional signals, only 3 labelled directional
signals and 10 unavailable labels across all samples. Two directional hits and
one unchanged price verify accounting/controls; these few outcomes are integration
evidence, not evidence of a predictive or economic edge. Validation/test outcomes
are not calculated. Browser checks cover unavailable groups, exact exports,
inert hostile strings, large integers and 390/320-pixel layouts without requests.

The separate 120-second capture provided nine qualifying finalized children but
ended operationally failed on a nonretryable final short-child exit. Its archive
integrity verifies; that failure was retained and never promoted to a completed
capture window. Cloud collection needed its managed session CA mounted read-only
for verified TLS; no TLS verification was disabled and no session trust was put
in the Mac image or source. Evidence is under
`data/study-acceptance-20261117T130645Z-r_nn64p5/` (`native-release.json`,
`release-browser-review/`, capture/quality diagnostics and preservation receipts).
The original release and experiment-runner pins remain unchanged.

Mac development/validation acceptance is now supplied above, independently of this
smaller cloud check. All three original study groups are now evaluated. No new Mac collection or day
attempt has been started; economic testing and the 24-hour gate remain outstanding.

## Dataset-quality report, 17 November 2026 PKT

`bash scripts/mac quality` now produces an offline quality inventory and portable
Giethoorn-themed view for the last stopped archive. It uses the existing image,
fresh native audit, read-only source/helpers/assets and a new derived directory;
there is no image rebuild, source upload or live collection. Original per-child
records and verified normalized observations drive timing/state measurements.
Clock discontinuities, reconnects and repeated exchange times break candidate BBO
spans; recorded fresh time is capped at its actual deadline. See
[the quality guide](quality.md) and [decision 0009](decisions/0009-dataset-quality.md).

The manifest binds source inventories, auditor/helper fingerprints, the copied
research protocol, fixed policy, span artifact and chronological candidate groups.
Fewer than five candidate children cannot admit a retrospective study split.
Known run-134 visual exposure is declared for its original Mac parent only.
The signal runner is now implemented above; actual Mac outcomes and the economic
test remain outstanding.

Validation passes 102 Python tests, shell syntax and whitespace checks. The full
ordinary-user launcher on the saved cloud rehearsal retains 767 verified
observations across two finalized children and one excluded recovered prefix.
Its two finalized children contain 533 usable BBO updates and 11 qualifying spans
totalling 25.979429340 seconds; no study split is admitted from only two children.
These are cloud-rehearsal results, not measurements of the user's Mac archive.
A separate mutation copy is refused with null quality totals and no admitted
rows. An explicitly synthetic failed legacy archive verifies as retained evidence
but has no BBO candidates and no study admission. Original inventories stay equal.

Offline browser checks pass recording filters/search/keyboard selection, prefix
and unavailable states, exact JSON download, inert hostile text, integer precision
and 390/320-pixel layouts, with no JavaScript errors or network requests. Evidence
is under `data/quality-acceptance-20261117T123006Z-zxwuixii/release/` (native
`acceptance.json`, `browser-review/browser-checks.json` and screenshots); the
synthetic legacy fixture is recorded separately under the evidence parent.

The Mac's actual quality totals are now supplied in the acceptance above and
are separate from this smaller cloud sample. The day gate remains pending, no
Mac collector has been restarted, and original release/runner pins are unchanged.

## Research preparation, 17 November 2026 PKT

The user reports the recorded-replay step done and explicitly confirms that the
BTC chart is visible in the browser. This is user-reported local UI acceptance;
no new replay stdout or Mac artifacts have been read here. Local native archive
audit acceptance below remains established from the earlier output.

The [first offline research protocol](research-plan.md) is now specified before
signal outcomes: qualify/fingerprint the finalized source, test one fixed BBO-size
imbalance prediction, separate chronological development/validation/test children,
and require a later explicit costed-execution specification. Run 134 is flagged
as selected for visual inspection rather than claiming an untouched holdout.
The protocol was prepared before outcome analysis. Its first dataset-quality
implementation and fixed signal study are now documented above; costed strategy
evaluation remains ahead. The protocol-only step required no Mac update or
collection-policy change.

## Stopped Mac day attempt, 17 November 2026 PKT

**Local audit accepted:** the user ran the published review update and supplied
its native result: `integrity: verified`, `source_unchanged: true`, audit exit 0,
no timeout and no metadata issues. All 134 child archives were validated:
334,794 observations, 139,614,246 recording bytes, 133 finalized recordings and
one recovered prefix. Evidence is saved locally at
`~/GiethoornData/review-20261117T115403Z-Hus68T/report`. This establishes local
archive integrity according to the supplied native audit output; the original
Mac files have not been transferred to or read in this cloud workspace.

The last child, 134, exited zero with a finalized recording, exact quote
comparison and 2,049 observations. Its reported elapsed time is 1,818 seconds
(30m 18s), despite a nominal five-minute child allowance. A clean child exit does
not undo a parent watchdog deadline violation. VM suspension or a shutdown/stall
is compatible with this delay, but the audit does not identify its cause. The
parent remains failed and `verified_24_hour_window` remains false.

The next local command is `bash scripts/mac replay 134`, after updating only
the launcher. It uses the existing image to validate and copy that one finalized
recording, independently replay the derived paper inputs, and open its portable
Paper Lab. The view shows saved BBO prices/feed health; it is not a whole-archive
analysis, a live quote screen or a strategy-performance test. Original source is
read-only, networking is disabled, output is fresh, and a 180-second job timeout
retains failure diagnostics. Active collectors and unavailable child numbers are
refused. Recovered prefixes remain separate and are not repaired for replay.

Validation: 83 Python tests, shell syntax and whitespace checks pass. The complete
launcher replays a saved cloud child into 525 independently checked paper updates
from 524 source records, with no fills and no full-window claim. A recovered
prefix is refused; original and copied archive inventories remain unchanged.
Evidence: `data/mac-recorded-replay-20261117T115917Z-70o_c6fk/acceptance.json`.
This verifies the existing Linux image and launcher, not execution of the new
command on the Mac. Engine/replay schemas and the old release/runner pins remain
unchanged; an image rebuild is not required.

The user's first Mac day attempt is retained at
`~/GiethoornData/start-20261116T161743Z-8dyq7k`. Its collector has exited with code
1; its read-only monitor remains running. The user reports a power/internet
outage. The supplied supervisor summary records `status: failed` and
`reason: collector exceeded its run deadline; no automatic restart`.
It reports 41,404.564 seconds (11h 30m 4s), 134 started children, 2 restarts,
334,794 validated snapshots and 139,614,246 recording bytes (about 133 MiB).
Peak sampled RSS is 11,624,448 bytes and the sampled FD maximum is 6. These
initially supplied producer counters now agree with the local native audit above.
The outer experiment reports both initial recoveries but fails overall.

The deadline identifies the terminal watchdog condition; it does not establish
whether VM suspension, a network stall or another cause delayed the child.
No retry limit, grace period or fail-closed policy has been relaxed. The full-day
gate remains pending, and no replacement day run has been started here.

`bash scripts/mac review` now audits a stopped run offline with the existing
image's native auditor. The updated launcher and new `ops/review_local.py` are
mounted from source, so this review requires no image rebuild. Original data is
read-only; derived inventories, diagnostics and `review.json` are saved in a new
Mac `review-*` directory. It separately reports producer failure, native archive
integrity, finalized recordings/recovered prefixes and the actual day gate. A
native refusal never manufactures audited totals or repairs a missing summary.
See [decision 0008](decisions/0008-stopped-local-review.md) and
[Mac review instructions](local-mac.md#review-a-stopped-run-before-starting-another).
Mac review acceptance is supplied above. The user now also confirms the recorded
Paper Lab chart opens locally, as noted in the research handoff. No new full-day
run has been requested.

Validation: 79 Python tests and shell syntax checks pass. The existing ordinary-user
image verifies the saved cloud 90-second rehearsal (767 observations, 2 finalized
recordings and 1 recovered prefix), and independently accepts an explicitly
synthetic failed archive without claiming window completion. A mutation copy is
rejected with null audited counts and retained diagnostics. The complete
`scripts/mac review` path also passes on Linux Docker. All source inventories
remain unchanged; every short/failed case keeps the day gate false. Evidence is
under `data/local-review-20261117T113345Z-3dexzxyf/acceptance.json`. These container
checks do not independently establish integrity of the user's Mac archive.

## Intel Mac local setup, 16 November 2026 PKT

**Mac acceptance:** after applying `11a4247`, the user reports that image build
and offline Paper Lab generation completed. Their direct-route Mac rehearsal
also completed its requested 90 seconds, with `network_recovery_observed: true`,
`crash_recovery_observed: true` and `supervisor_exit_code: 0`. Its saved run is
`~/GiethoornData/rehearsal-20261116T161040Z-PXTg2R`. This is evidence from the user's
Terminal output; its underlying archive has not been independently read here.
The runner emits `completed` only after its native audit succeeds. The later
Mac day attempt failed as documented above; the full-day gate remains pending.

The user approved source delivery through GitHub. The `mac-local-setup` branch
was uploaded at `0d49d2e`; its ZIP downloaded successfully over HTTPS, all 119
source files matched the commit, and executable modes were retained. The Mac
then reached the image's native tests and reported a failure in
`whole_supervision_budget_stops_before_starting_a_child_with_insufficient_allowance`.

That budget test previously measured recording size using a separate three-second
supervisor window. Copying/hashing the debug executable counts against that
window. A constrained-CPU reproduction exhausted the window before any collector
started (`supervision collected no usable snapshots`). Calibration now runs one
two-second collector directly and requires a finalized, usable recording with
exact quote replay. The actual supervisor budget case has an ample time window
so the quota must stop it; its existing 15-second test watchdog, one-child count,
byte ceiling and independent `BudgetExhausted` audit assertions remain enforced.
The fixed case passes three constrained-CPU trials and a forced-software-SHA run.
The required `./scripts/check` also passes all 150 Rust and 64 Python tests,
formatting, clippy and shell checks. This changes the test fixture, not collector
behavior, schemas or resource limits.

The user chose their Intel MacBook Pro (2019, i9, 64 GiB, macOS 26.7.1) as the
local host. A paid VPS is not required for current collection/research. See
[the local setup guide](local-mac.md) and [decision 0007](decisions/0007-local-mac.md).
Docker Desktop supplies Linux for the unchanged `/proc`-based fault runner.

`scripts/mac` builds/tests the image, generates an offline demo, runs a 90-second
disconnect/crash rehearsal, or starts a new 24-hour window. Recordings persist in
the Mac's `~/GiethoornData`; containers use ordinary user permissions and bounded
resources, and the read-only monitor is on loopback port 3000. Setup alone never
starts collection. The foreground watcher holds macOS sleep assertions during a
run; keep the Terminal and lid open with the charger connected.

`ops/run_local.py` adds a direct public-host CONNECT relay around the original
experiment without editing it. Local receipts bind both source hashes and
distinguish a passed short window from a passed 24-hour request. The direct relay
has bounded synthetic forwarding/target-rejection tests; the cloud acceptance
uses the declared inherited-proxy route. That does not establish the Mac's direct
network behavior or VM/filesystem acceptance by itself; the separate user-reported
Mac rehearsal above supplies the first local acceptance result.

The source exporter includes the implementation, executable
permissions, file hashes and optional saved Paper/Batch Lab previews. It excludes
the original raw recording archives, native build outputs, environment files,
common private-key files and cloud build certificates/credentials. The download
package and verification artifacts are under
`data/mac-setup-20261116T124540Z-2u9osiuh/` (`Giethoorn-Mac.zip`, `handoff.json`,
container logs and local acceptance evidence).

The pinned container compiles/tests the source and checks runtime readability
and fixture replay as an ordinary user. Native acceptance is 150 Rust tests;
Python acceptance is 64 tests, including setup, failed monitor cleanup, container
ownership, minimum VM resources, export exclusions/checksums, environment restore
and visible short/failed local results. Cloud-specific trust is supplied as a
temporary BuildKit secret; the exported Dockerfile retains standard trust roots.

The ordinary-user, read-only-root image generates a saved synthetic Paper Lab.
Its **90-second public BTC rehearsal passes** on the inherited cloud proxy route:
three validated runs, 767 market observations, observed network/crash recovery,
and final `integrity: verified` / `full_window_completed: true` for that requested
90-second window. `verified_24_hour_window` remains false. A separate loopback
monitor mounts those artifacts read-only and reports the correct 90-second gate.
This verifies the packaged Linux runtime, not the Mac's direct route or a day run.

The Mac's setup/demo/rehearsal now complete according to the user's logs; its
full 24-hour gate remains pending. The old cloud collector remains stopped. No
old attempt is resumed, repaired or combined, and no environment was published,
service installed or authenticated trading enabled.

The user observed a real chat **Could not download artifact** error. A clipboard
fallback was also incomplete: the pasted payload ended around byte 10,752 of a
470,480-byte restore file and left zsh waiting at `heredoc>`. Their local file
search found no restored source. With the user's approval, the Git snapshot was
uploaded as a transfer alternative. Its branch is `mac-local-setup`, containing source/tests/docs only,
with no raw recordings, archive outputs or environment credentials. The Mac's
installation/rehearsal must not be declared successful from these transfer steps.

## Batch execution sensitivity, 16 November 2026 PKT

A bounded offline batch runner and Giethoorn-themed Batch Lab now compare fixed
IOC plans across recorded sessions and execution assumptions. This is sensitivity
testing, not empirical calibration or strategy evaluation. See
[decision 0006](decisions/0006-batch-sensitivity.md) and
[the manifest guide](paper.md#batch-sensitivity-testing).

The first actual matrix is under
`data/batch-sensitivity-20261115T220343Z-nl49fxw0/`:

- `matrix/batch-lab.html`: portable interactive comparison, also served at
  `http://127.0.0.1:3000/batch` on this machine. Download the HTML to view it on
  another computer. The monitor links to both Paper Lab and Batch Lab.
- `matrix/batch-report.json`: **20/20 verified cases**, four saved BTC sessions
  (`000002`, `000040`, `000083`, `000086`) × five declared profiles. The original
  matrix completed in 117.562 seconds, retaining about 347 MiB before reports.
- `matrix.json`, `plans/` and `prepare_inputs.py`: the declared profiles and
  fixed per-recording protocol plans. Prices/limits use the initial quote; probes
  use fixed sequence offsets plus an explicitly selected ending boundary. These
  plans are protocol tests, not alpha signals or chronologically held-out tests.
- `matrix/datasets/`, `matrix/scenarios/`, `matrix/cases/` and `matrix/replay.bin`:
  frozen validated source copies, original/final scenarios, fingerprints, pinned
  debug binary and every case's cost/ledger verification artifacts.
- `browser-handoff/`: desktop/mobile screenshots, exported JSON and browser checks;
  `native-acceptance.json` and `synthetic-*`: explicitly synthetic repeatability,
  hand-calculated fee sensitivity and deliberately invalid-source failure evidence.
- `preservation.json` and `original-inventory-after.json`: all **443 original
  retry files** retain their bytes, modification times and hashes. The collector
  release and original runner retain their earlier pinned hashes.

The baseline assumes a `0.0005` fee rate, 1 bps adverse slippage, `0.25` available
top-size fraction, 100 ms arrival delay and a 1,000 ms fresh-quote window. Each
stress profile changes exactly one assumption: fee to `0.001`, slippage to 3 bps,
delay to 500 ms, or available top-size fraction to `0.05`. Orders, risk settings
and collateral remain fixed within each recording. Nothing was tuned to a winner.

All 20 cases pass source/scenario validation, independent Decimal cost checks and
exact ledger replay. Five cases retain open inventory and fifteen retain pending
orders; these overlapping counts describe simulations, not independent trades.
Lower assumed top size changes ending inventory in session 002. Delay changes
fill source events in all four sessions even where final net P&L is unchanged.
Its spread decomposition can change with the historical midpoint. The UI exposes
these path/exposure differences instead of treating every P&L delta as pure cost.
Session 083 still declares its original capture end `failed`.

The runner has bounded native children and checks output/free-space/time budgets
between operations. Every planned row remains visible; failed/skipped cases have
null metrics and unavailable comparisons. Repeated synthetic native batches have
identical metrics; a doubled fee changes net P&L by exactly `-0.02511250125` with
the same execution path. An invalid synthetic source exits 1 while preserving its
two failed rows alongside two verified rows. No per-case HTML is required for a
batch, but both independent audits still run.

Final report/view metadata is derived from retained verified case artifacts;
initial exports remain beside it. Coin and quote-currency labels come from each
case's native configuration. Financial outcomes and source/plan fingerprints are
unchanged by view refinements.

Python checks pass **52 tests**. Batch browser acceptance covers desktop/mobile
layouts, filters, exact figures, keyboard selection, JSON export, synthetic failure
rendering, zero offline requests, loopback navigation and hidden server links in
saved monitor snapshots. Rust source and all existing golden outputs are unchanged;
the preceding full suite's 150 Rust tests remain the native baseline.

The collector is stopped and the interrupted 24-hour gate is still unverified.
No wallet, live paper feed, strategy execution, order adapter, deployment or
environment publication was added. The next operational requirement is an
always-on process/host and retention plan for a fresh, independently audited
24-hour window. The next research requirement is a predeclared strategy hypothesis,
fixed risk limits and chronologically held-out data. Actual execution calibration
still needs observed execution measurements; this matrix supplies no such evidence.

## Controlled execution scenarios

Paper version 3 now runs fixed IOC order scenarios on finalized recorded data.
Buy/sell prices use the opposite recorded best side plus declared adverse
slippage. Assumed arrival delay, a bounded fresh-quote window and a shared fraction
of recorded top size determine eligibility/quantity. Partial remainders receive
explicit simulated cancellation events; expiry, missing/stale data, price limits,
exposure limits and loss halts are exercised. Pending orders and open inventory
survive replay end instead of being silently cancelled or flattened.

This is offline protocol/cost testing, with all acknowledgements and fills marked
as assumptions. No strategy, authenticated order adapter or live paper feed was
activated. The 24-hour collector gate remains incomplete and its collector stopped.
Version-1 and version-2 golden outputs/restrictions are unchanged. See
[the execution decision](decisions/0005-controlled-execution.md).

The actual-recording scenarios declare a fee rate of `0.0005`, adverse slippage of
1 basis point, a `0.25` top-size fraction, 100 ms assumed arrival delay and a
1,000 ms fresh-quote window. Limits and order anchors are fixed in saved scenario
files; limits use the initial recorded price, not later profitable outcomes.
Some anchors deliberately target known outage/end boundaries for protocol checks.
These are uncalibrated assumptions, not venue fee/latency/execution measurements.

- The healthy BTC scenario processes six requests and two assumed fills. Its
  illustrative fee total is `0.0645959992`, spread decomposition `0.003`, slippage
  decomposition `0.0129192`, and net paper P&L `-0.0615151992`. Inventory ends flat
  with one unconfirmed `last-quote-probe` order still pending.
- The network-affected recording processes nine requests and three assumed fills.
  A short `0.0001` BTC simulated position remains; its source still ends `failed`.
  Its historical-mark paper P&L is `-0.07756339659`. This is not a trading return.
- The synthetic golden has two partial fills, simulated remainder cancellations,
  stale/missing/risk/expiry rejection and a pending ending. Its hand-calculated
  fees/net P&L are `0.02511250125` / `-0.05513500125`. Depth-selected execution
  also passes source-selection and independent cost verification.

Evidence is under `data/controlled-paper-20261115T211847Z-is3k74r4/`:

- `btc-ioc/paper-lab-final.html`: default `/paper` lab, with price/P&L switching,
  cumulative cost receipts, order states and source/scenario fingerprints.
- `btc-network-ioc/paper-lab-final.html`: outage scenario with retained inventory.
- Each lab's `replay/` keeps source copies, raw scenario, derived ledger inputs,
  updates, source links, execution trace and reports. `cost-audit.json` independently
  checks prices, source sizes, timing, shared capacity, costs and account algebra
  with 100-digit Python Decimal. Saved ledger inputs replay to exact output.
- `plans/` contains the predeclared actual-recording scenarios. Financial strings
  with trailing zeros are normalized semantically, while hashes bind original bytes.
- `fixture-ioc/` and `fixture-depth-ioc/` retain explicitly synthetic boundary cases.
- `execution-browser-final/`, `market-regression-final/` and
  `synthetic-regression-final/` contain browser results and screenshots.
- `replay.bin`, `checks.log`, `final-views.json` and `handoff.json` retain the pinned
  debug binary, validation output, final HTML/embedded-data hashes and preservation
  checks. The collector release binary and original runner remain unchanged.

Full checks pass **150 Rust tests and 38 Python tests**. All three lab modes pass
their eight browser acceptance groups, including desktop/mobile, offline use with
zero requests, source provenance, state navigation and scenario-specific costs,
partial/cancel/stale behavior and unresolved exposure. Original retry evidence is
rehashed against its earlier inventory and remains unchanged. No source schema,
historical collector report, environment configuration or publication was changed.

## Recorded-market Paper Lab

The next offline testing slice now connects saved market data to paper marks.
`paper-market-replay` validates and copies a finalized schema-2 recording, persists
each version-2 paper input before processing, and retains an original-event link
for every update. BBO and depth remain independent; recorded timers, stale/empty
states and reconnects affect eligibility without an observer clock. Version 2
disables orders and fills. Version-1 scenarios and all original golden output
remain unchanged. See [the recorded-market decision](decisions/0004-recorded-paper.md).

Two actual BTC recordings from the retained retry were exercised separately:

- `run-000086`: 2,870 source records, **1,887 BBO marks**, 2,871 derived paper
  states, one connection and a normal duration end.
- `run-000083`: 2,128 source records, **1,359 BBO marks**, 2,129 paper states and
  four connections. Its original end reason is `failed`; the replay preserves
  the network/stale periods instead of relabeling that capture healthy. A real
  stale event at paper sequence 1,573 is verified in the browser.

These are independent offline child-recording replays, not a continuous combined
dataset, a live paper strategy, fills or economic-performance evidence. The
assumed 10,000 USDC account remains flat. A complete replay does not pass the
outstanding 24-hour collector gate, and the collector remains stopped.

Evidence is under `data/recorded-paper-20261115T202637Z-hiji0hel/`:

- `btc-bbo/paper-lab-final.html`: the earlier mark-only lab retained for reference;
  `/paper` now links the controlled execution view described above.
- `btc-network-bbo/paper-lab-final.html`: the network-affected recording.
- Each lab's `replay/` retains a private source copy, source manifest, mapped paper
  inputs/updates, event links, paper report and source replay report. The exporter
  independently replays the persisted paper inputs and requires exact output.
- `recorded-browser-final/` contains desktop/mobile captures and eight browser
  acceptance groups; `actual-network-check.json` records the real stale case.
- `synthetic-v1/` and `synthetic-browser/` retain the original synthetic scenario
  and its eight passing browser groups. Fixture market data has an explicit
  `synthetic_fixture` origin and a separate view.
- `replay.bin` pins the tested debug binary; `final-views.json` records the final
  portable-view and embedded-state hashes. `checks.log` and `handoff.json` retain
  test and original-evidence verification results.

Full `./scripts/check` validation passes **135 Rust tests and 31 Python tests**.
New recorded-view checks cover origin labels, exact source-linked price/state,
scrubbing/playback, a bounded event trace, source-gap chart segments, responsive
layout and offline interaction without requests. The Giethoorn visual identity
is shared by both lab modes. The market monitor links the offline lab generically
rather than labeling every lab synthetic.

All original retry files were rehashed against the earlier recovery inventory;
they remain unchanged. The collector release and experiment runner hashes still
match their pinned values. No third collection attempt, service installation,
environment publication, new exchange subscription or strategy was activated.

## Giethoorn-inspired interface

The market monitor and Paper Lab now share a visual identity inspired by the
owner's photograph of Giethoorn: deep forest navigation, warm ivory surfaces,
moss quote lines, dashed brick depth lines and thatch accents. Local serif
headings and a bridge-and-canal mark connect the product to the village. Colours
and shared component treatments live in `web/theme.css`, embedded in both HTML
renderers so exports remain portable. See [the design guide](design.md).

The visual update preserves collector behaviour, market and paper schemas,
freshness calculations, exact financial values and synthetic source labels.
Historical evidence and earlier exports remain untouched. Collection was active
at the design checkpoint; the interruption review below supersedes that running
status. The visual work does not complete the reliability gate.

Current design evidence is under `data/giethoorn-design-20261115T125721Z-gsc7ye8h/`:

- `dashboard-delivery/giethoorn-dashboard.html` is a timestamped portable snapshot;
  that directory also contains desktop/mobile screenshots and browser results.
- `paper-view/paper-lab.html` is the newly rendered synthetic Paper Lab,
  with its Rust-generated frames, report and provenance beside it.
- `paper-view-review/` contains its desktop/mobile screenshots and browser results.
- `design-review.json` records 18 viewport checks from 320 to 1920 pixels, 14
  selected text/background contrast pairs above 4.5:1, visible keyboard focus for
  both primary actions, and matching pinned collector/runner hashes.

All 25 Python operations tests and both existing eight-group browser acceptance
suites pass. Both portable views work offline with zero requests. At the design
checkpoint, the fresh attempt was still active with 18 validated recordings and
38,767 verified observations; its full-window gate remained pending. The monitor
on port 3000 now links the new Paper Lab. No service or environment was published.

## Current collection attempt and interruption recovery

As checked on **2026-11-16 around 00:24 PKT**, environment execution access is
restored, but neither the reliability runner nor its supervisor/collector survived.
The retry's supervisor lock is free, its final summary is absent, and the final
experiment/audit files were never produced. The read-only monitor has been
restarted on port 3000 and reports **Collector stopped / Incomplete**, with both
feeds disconnected. Inactive runs now show no active finish countdown; pausing
the display no longer claims a stopped collector is running.

The retry's last recorded activity is **2026-11-15 at 23:46:02 PKT**, about
**7 hours 8 minutes 36 seconds** after startup. Its earlier planned finish on
16 November at 16:38 PKT is no longer an active completion estimate. The exact
cause of process loss is not established by the retained evidence.

All **87 retry recordings** were independently inspected and replayed read-only:
**208,351 market observations**, including **2,175 depth** and **206,176 BBO**.
Eighty-five finalized recordings match exact replay; two unfinalized crash prefixes
validate (the controlled first-child kill and final interrupted child). All 86
original inspection caches and validation counters agree with the new results.
Recording bytes total **87,388,763**; the recordings contain 17 connection-error
events. Both controlled recoveries were observed. There were two supervisor
restarts: the injected kill and a later exhausted network attempt. These facts
do not establish a completed time window or continuous feed coverage.

The full archive audit correctly rejects the missing final summary. No final
report was manufactured. SHA-256 inventories before and after recovery confirm
every original experiment file is unchanged; pinned collector and runner hashes
still match. Recovery evidence is outside the strict supervision root:

- `data/interruption-review-retry-20261115T192250Z-f0wu8ont/recovery.json`
- `verify_stopped_attempt.py`, `inspections/`, both original-file inventories and
  `full-audit-refusal.stderr` in that same directory.
- `monitor-final/giethoorn-stopped-view.html` and its desktop/mobile screenshots
  provide the current portable view. `monitor-final/browser-checks.json` and
  `check_monitor.py` cover disconnected feeds, frozen elapsed time, inactive
  countdown, historical labels, pause/resume, mobile layout, offline interaction
  without requests, an earlier genuine snapshot and the synthetic lab route.

The monitor continues to display the original supervisor's **86** validated runs
and **207,198** observations. The recovery report includes the final child's
additional **1,153** verified prefix observations; it does not rewrite the
supervisor's historical counters to incorporate them. All 25 Python operations
tests and nine stopped-monitor browser checks pass.

The next reliability window requires an always-on host with explicit process,
shutdown and archival ownership; the prepared service candidate is documented in
[deployment.md](deployment.md). No third collection attempt, service installation,
environment configuration change or publication was performed during this review.
Interrupted hours from either attempt cannot be added together for a 24-hour pass.

The original 24-hour attempt is interrupted, not passed. On environment recovery,
no runner/collector was active and the supervisor writer lock was free. Its last
observed event is **2026-11-15 at 07:53:07 PKT**, roughly 7 hours 48 minutes into
the requested window. No final supervisor summary, experiment result or full-window
audit exists. The evidence does not establish the cause of process loss; the later
Cloud startup error is not itself a root-cause diagnosis.

The retained data was reverified read-only using the original release: **95
recordings, 297,779 usable market observations**, including 2,361 depth and 295,418
BBO observations. Ninety-three recordings are finalized and match exact replay;
two unfinalized crash prefixes validate (the injected first-child kill and final
interrupted child). Original cached inspections/control counters also match where
present. Recording bytes total 119,539,104. The full supervisor audit correctly
refuses the missing summary rather than declaring a pass.

Evidence: `data/interruption-review-20261115T113423Z-J9Y6iY/recovery.json` and
`full-audit-refusal.stderr`. All original files remain retained and were not
rewritten, resumed or pruned. Two additional original supervisor restarts followed
network exhaustion; those collector logs include BBO stalls. Retry/freshness
thresholds were preserved rather than raised to conceal them.

The second bounded 24-hour attempt was retained under
`data/reliability-24h-retry-20261115T113726Z-zXpTBj/experiment/`, beginning around
**2026-11-15 at 16:37 PKT**. Its interruption and recovery results are reported
above. The release, limits, recorded formats and runner remain pinned. The
read-only monitor points at that retained attempt and the optional synthetic
Paper Lab; proper service/reboot/host lifecycle ownership remains an open gate.

## Offline paper foundation and visible Paper Lab

`paper-replay` now implements a separate version-1 paper record stream, exact
bounded financial arithmetic, explicit acknowledgements/assumed fills, pending
new/open/partial/cancel/terminal order states, duplicate protection, FIFO long/short
positions, fees and marked P&L. Risk checks retain unconfirmed exposure, reject
new orders without fresh data, and latch loss/manual halts. Halts and end events
do not invent cancellation ACKs or close positions. Unsupported precision and
invalid transitions leave the previous model state intact.

This is isolated offline research. Scripted assumed fills are not inferred from
quotes. Funding, venue margin/liquidation, queue position and execution latency
are unmodeled; FIFO is declared and does not claim venue-accounting parity.
All scenarios/outputs declare paper mode and synthetic/manual provenance. No
live-feed adapter, strategy, arbitrary-order UI or authenticated order capability
was enabled. The actual collection gate remains pending.

Twenty-two new Rust paper/CLI tests pass, including a synthetic 29-event golden
scenario with five assumed fills and one duplicate fill. Its hand-checked final
realized P&L is `1.6`, fees `0.0592`, and net P&L `1.5408`, with no position. These
are synthetic accounting test vectors, not economic performance. Full Rust
validation now passes 123 tests; subsequent Python operations checks pass 25.

The Paper Lab plays actual Rust-generated frames with order/position/fee/risk state,
previous/next, scrubber, play/pause and an event trace. It is self-contained and
explicitly labeled synthetic. Artifact:
`data/paper-lab-20261114T204639Z-65X7cu/final-view/paper-lab.html`.
That directory retains the source scenario, derived updates/report and exact
debug-binary/input hashes. The local monitor links `/paper` only when configured;
serving the view never invokes a binary or changes the collector.

Eight Paper Lab browser acceptance groups pass on desktop, mobile and offline:
golden balances/provenance, trace navigation, partial/duplicate fills, stale/halt
rejections, playback/scrubber, layout, network-free use and zero JavaScript errors.
The existing monitor's eight groups also passed again after optional lab navigation
was added. Browser evidence is under the artifact parent's `browser-review/` and
`monitor-browser-review/`. `independent-accounting-check.json` verifies the fee
total and account algebra with Python Decimal; it is not an independent fill model.

At the final checkpoint the original runner and pinned release/collector hashes
still matched, 24 child attempts had validated 62,808 market observations, and
the final 24-hour experiment/audit remained uncompleted. No release rebuild,
experiment restart, deployment or environment publication was performed.

The collector's release binary and experiment runner remain pinned/unchanged.
The environment briefly reported `starting`, then returned ready with the same
workspace and the existing collector runner still alive. Retained binary hash
and process identity were checked; no experiment was restarted or relabeled a
completed gate. See [the paper guide](paper.md) and accepted
[model decision](decisions/0003-paper-model.md) for scope and next acceptance.

## Visible monitor and portable dashboard

A read-only dashboard is now implemented and running on port 3000 in this Cloud
machine. It shows actual recorded BTC prices, separate BBO/depth age and status,
real price charts, validated session counts/output comparisons, sampled child RSS,
fault recovery and the pending 24-hour gate. Navigation, recording filters, chart
ranges/source toggles, pause/resume and HTML export work. No collector, Rust source,
record format, environment configuration or running experiment was changed.

The chat has no available Cloud preview/viewer forwarding tool. To make the work
visible immediately, `data/dashboard-final-20261114T200803Z-NlfS6g/` contains
`giethoorn-dashboard.html` (download/open in a browser), desktop/mobile screenshots
and `browser-checks.json`. The HTML embeds actual captured data and all assets,
is labeled `Saved snapshot` with its capture time, remains interactive offline,
and never claims to be a live connection. No external service was published.

Twenty standard-library operations tests pass, including 10 new monitor checks
for stale/absent/new-child data, backwards/concurrent clocks, coherent final audit,
partial versus corrupt records, read-only behavior, safe embedding and HTTP scope.
Eight browser acceptance groups pass on desktop and mobile, with no JavaScript
errors. The exact exported HTML also rendered with networking disabled and zero
requests. Direct file navigation is blocked by managed Chrome policy; that policy
was preserved. An author CSS rule overriding `hidden` was caught and corrected
before delivery, and the mobile chart now uses legible viewport-sized axes.

The monitor's observer clock is captured after file reads, preventing normal
concurrent quote arrival from being mistaken for a backwards clock. Data freshness
is always distinct from whole-window completion. Read-only monitoring continues
alongside the unchanged pinned experiment; see [the dashboard guide](dashboard.md).

## Version-2 feeds and current reliability experiment

Explicit `--feed-profile depth|bbo|combined` is implemented, with schema-2 session
policy and timer records, exact-decimal BBO parsing, independent source timestamp
ordering, subscription ACKs and freshness. Health-only transitions identify stale
or disconnected feeds without manufacturing a new quote. An active BBO cannot
refresh old depth, and missing ACKs/empty updates cannot keep the watchdog alive.
The default schema-1 recorder and golden output remain unchanged.

Capture, replay, inspection, supervision and archive audit support the new profile.
Inspection reports per-channel counts/gaps/ages; audit checks the recorded policy
against supervision configuration. Every sealed record must match the container's
declared schema before any output. Both engines share lifecycle validation.
The deliberate event/normalization version and unpublished Rust callback change
are documented in [feed profiles](feed-profiles.md) and the accepted
[format decision](decisions/0002-feed-profiles.md).

The current release also audited the historical one-hour schema-1 archive without
changing its evidence. Result: `data/supervised-hour-20261114T145931Z-ch5mDi/`
`feed-v2-compatibility-audit.json`. Legacy quote bytes and cached inspections match.

### Combined mainnet acceptance

The two-minute public BTC check completed with 1,730 events, 11 depth snapshots,
1,320 BBO snapshots and zero connection errors/stale ignored snapshots. All 1,331
market observations and freshness transitions matched replay exactly. Nine sealed
segments totaled 534,354 bytes including the index; independent Python SHA-256
checks verified every seal and byte count. Recorded duration was 120.014566 seconds.

The maximum measured depth gap was 12.492 seconds, versus 0.725 seconds for BBO.
ACKs were observed independently for both feeds. Source-clock deltas ranged from
309 to 988 ms across channels; these are not RTT or HFT latency measurements.
Evidence: `data/feed-v2-live-20261114T164452Z-qXQ2oo/`, including live/replayed
observations, capture/replay reports, inspection and independent verification.

### Real fault rehearsal

The 90-second release rehearsal passed with three validated child attempts and
659 usable market observations. The first child reconnected after a deliberately
closed byte tunnel, then was intentionally killed with SIGKILL. The supervisor
verified its unfinalized output as a valid replay prefix before restarting. Both
subsequent finalized children matched exact replay. The root completed with one
supervisor restart, and the final audit verified the full window and recorded policy.

This used real public mainnet data with verified venue TLS through the inherited
HTTP proxy and a loopback byte-forwarder. The injected fault is not a natural venue
outage. Forwarder tests cover opaque bytes, upstream authentication, reconnect,
target restriction, bounded scheduling and refusal to signal unrelated processes.
Maximum sampled child RSS was 10,305,536 bytes; sampled FDs peaked at six.

Evidence: `data/reliability-rehearsal-20261114T185848Z-QI7wLT/` includes the
experiment's fault/recovery timeline, supervisor archive, final audit, current
release re-audit, independent sealed-file/executable hashes and final check log.
Its retained binary SHA-256 is
`254e58b6f0b6d965f6fbc5ba6f25cfb303c1f1311c4cf36fc95e2193e9d94375`.
The final build changes only command-help wording after that rehearsal; the
24-hour experiment records its own exact executable/runner fingerprints.

### Original 24-hour attempt: interrupted, completion unverified

Started **2026-11-15 at approximately 00:04:56 PKT**. Requested full-window end was
approximately **2026-11-16 at 00:04:56 PKT**, but the process ended earlier without
completion evidence. See the recovery and new attempt at the top. Evidence root:
`data/reliability-24h-20261114T190456Z-N1a0JX/experiment/`.

Both initial faults have already been observed and recovered: the tunnel was
closed at 30.222 seconds, a fresh new connection was observed at 32.471 seconds,
the owned collector was killed at 60.093 seconds, and a usable replacement child
was observed at 62.305 seconds. Its crash prefix passed supervisor validation.
This proves those initial recovery steps, not the 24-hour window.

At 361.206 seconds elapsed, the first full post-recovery five-minute child also
finalized and matched exact replay: 2,161 usable market observations and 927,922
recording bytes. The third child then started. The earlier killed child's 426
observations passed prefix validation. These are progress checkpoints, not a
completed window; `progress-at-handoff.json` outside the experiment root retains
the initial checkpoint and exact running binary/runner fingerprints.

The interrupted experiment was finite in the cloud machine. It used five-minute
children, a 4 GiB recording budget and 1 GiB filesystem reserve, retains everything,
and never publishes or installs a service. Its final `experiment.json` and
`audit.json` are produced only after the actual run finishes successfully. An
environment restart or failed budget/recovery check interrupts or fails the gate.
See [the experiment runbook](reliability-experiment.md); do not mark it passed
from the earlier rehearsal or current progress logs.

## Completed foundation

Public Hyperliquid recorder, synchronized per-event JSONL journal, deterministic
book engine, replay CLI, synthetic golden fixture, automated tests, CI and pinned
cloud setup. Real Hyperliquid mainnet BTC capture/replay now passes.

The prior CONNECT 403 blocker is resolved: the current enforced policy includes
`api.hyperliquid.xyz` and `api.hyperliquid-testnet.xyz`. Mainnet WebSocket access
was exercised with verified TLS and inherited proxy settings. A later diagnostic
also exercised testnet public feeds. No credentials or funds were used.

## New operational work

- Capture defaults to a 256 MiB journal budget and 1 GiB free disk reserve.
  Both are configurable; checks happen before writes. Violations stop capture,
  retain the valid prefix and do not trigger reconnects.
- Unix journal creation synchronizes the new file and its parent directory.
- `inspect` validates a log and summarizes recorded duration, bytes, errors,
  one-/two-sided snapshots, snapshot/reconnect gaps and source-clock deltas.
- `scripts/verify-live` creates fresh artifact paths, captures actual data,
  replays, checks byte equality and writes diagnostics. Failed runs retain evidence.
- Existing schema-1 events and quote output are unchanged; the original golden
  fixture still matches. The operational additions do not modify engine decisions.
- `collect` now writes checksummed rotating files in a fresh directory while
  retaining one connection, engine, event sequence and monotonic origin.
- Container version 1 has an append-only index, SHA-256 per sealed file,
  finalization footer, whole-session byte budget including index growth, and
  cooperative writer/read locks. The policy is retain and stop, never prune.
- Directory replay verifies all sealed hashes before emitting quotes. Explicit
  recovery permits one unsealed tail and a torn final index fragment, while
  preserving strict validation of sealed data and complete records.
- `supervise` now snapshots the collector executable, creates bounded child runs
  in fresh directories, validates hashes/events/output before restarting, and
  enforces restart and cross-run recording budgets. Durable control events and
  Linux RSS/FD samples remain outside deterministic engine state.
- Network exhaustion is exit 10; recording/data/output errors are exit 11 and
  fatal by default. Permanent HTTP 4xx (except 408/429) do not retry. Signal-safe
  read interruption, graceful SIGINT/SIGTERM, watchdogs and Unix parent-liveness
  guards stop owned children without pretending interrupted work completed.
- `audit-supervision` now independently recomputes a finalized supervisor archive:
  executable/segment hashes, control lifecycle, replay comparisons, resource
  maxima, cached inspections, market identity, quotas and final report. Integrity
  verification is separate from successful operation and full-window completion.
- A native launcher, service-unit template and strict renderer are prepared for
  review. The launcher preserves failure exit codes and fresh artifact paths;
  the unit owns its process group and deliberately disables whole-service retries.
  No service was installed, enabled or deployed. See [deployment](deployment.md).

See [the collection runbook](operations.md) for flags and metric interpretation.

## Verification in the restored machine

Latest verification: **123 Rust tests and 25 Python operations tests passed**,
zero failed or ignored. Formatting and Clippy with warnings denied pass. Shell
scripts pass `bash -n`. An optimized release binary was also built successfully.
The full Rust/check run passed after the paper additions; Python operations checks
were rerun after the exporter/monitor integration. The existing monitor has eight
browser acceptance groups. No exchange request is required by backend tests.

Coverage includes deterministic output, decimal precision, invalid data, stale
snapshots, empty sides, crash recovery, reconnects, stalled feeds, file-write
failures, size limits, disk-reserve checks and diagnostic reporting. Real local
WebSockets and production CLI/CONNECT/TLS tests remain offline: trusted TLS works;
untrusted and wrong-host certificates are rejected.

New tests cover rotation boundaries, exact replay, index-aware budget exhaustion,
late-segment corruption before output, missing/extra files, invalid names/version/
ranges/footer, symlinks, locks, incomplete data/index commits and finalization.
Production CLI tests rotate through one locally verified TLS connection and kill
a real collecting process with SIGKILL: its lock is released and recovery reads
the sealed prefix plus its live tail. This is a process-crash test, not power loss.

Seventeen supervisor tests cover planned handovers, network drop/restart, killed-child
prefix recovery, permanent 403, restart exhaustion, graceful SIGTERM, checksum
fail-stop, stalled TLS watchdog, supervisor-death orphan prevention and live-prefix
comparison. The shutdown test exposed an interrupted socket read being treated as
a network failure; handling `Interrupted` as a polling interruption fixed it.
Finalized runs compare exact bytes; unfinalized crash output must be a prefix of
replay, reflecting WAL-before-output ordering rather than masking missing data.

Additional checks exercise recording-budget fail-stop, global-budget exhaustion,
audit mutations, active/missing-summary refusal, and overflow rejection before
creating artifacts. A real local WebSocket burst of 1,000 snapshots passes
durable-write backpressure and more than ten rotations with exact replay. This
is a functional load check, not an HFT throughput/latency benchmark.

Process-spawning supervisor scenarios are serialized within their test binary.
A reproduced Linux fork/flock interaction showed that concurrent process creation
can briefly inherit a recording lock until `exec`, despite close-on-exec. The
test harness now avoids that race; product lock rejection and integrity assertions
remain intact. Intentionally orphaned test collectors are explicitly reaped.

## Completed one-hour supervision baseline, 2026-11-14

The public mainnet BTC supervisor completed its full 3,600-second window, from
14:59:31 to 15:59:31 UTC. Each child had a five-minute limit, with a shorter final
child. The stdout report and final summary agree. The new release audit returned
`integrity: verified`, `supervisor_status: completed` and
`full_window_completed: true`.

| Measurement | Result |
| --- | --- |
| Requested / supervisor elapsed | 3,600 seconds / 3,600.000809 seconds |
| Sum of child recorded durations | 3,597.572 seconds; handovers leave gaps |
| Finalized child runs / planned handovers | 12 / 11 |
| Unexpected restarts / connection errors | 0 / 0 |
| Recorded events / usable snapshots | 772 / 304 |
| Successful connections / sealed segments | 12 / 12; one segment per child |
| Index plus segment bytes | 756,397 |
| Full supervisor archive bytes | 39,602,110, including retained executable/metadata |
| Live versus current release replay | Exact bytes for all 12 children |
| Independent executable/segment hashes and counts | Passed |
| Maximum within-connection snapshot gap | 14.805 seconds |
| Source-clock delta range | 346–2,808 ms; not RTT |
| Resource samples | 719, configured at five-second intervals |
| Maximum sampled child RSS / FDs | 13,828,096 bytes / 6 |
| Sampled RSS after each child's first 30 seconds | 13,627,392–13,828,096 bytes |

The executable was pinned at launch before this hour's audit/operations additions:
SHA-256 `5285a7da9f05adf4a9c29808cea9be1e80aaffc90a03c115c5e9760024c668b5`.
The current release independently audited/replayed the completed archive; its
SHA-256 is recorded in `verification.json`. Event/container formats and depth
normalization were unchanged. The hour establishes the pinned collector baseline;
new audit/operations behavior has separate executable checks and acceptance.

Evidence: `data/supervised-hour-20261114T145931Z-ch5mDi/` retains `report.json`,
the supervision root with its snapshot/configuration, `audit.json`, independent
`verification.json` and `verify-hour.py`, plus `final-check.log`. Python independently
recomputed SHA-256, sizes, sequences, counts and resource maxima; quote comparison
used the production replay engine, not a second implementation of that engine.

No fault was injected into the live hour. The run used planned fresh child
processes and a low-rate depth feed; sampled memory is not an absolute peak or
proof of leak freedom. The 15-second threshold was preserved despite the close
14.805-second gap. This is not continuous coverage or the unrun 24-hour gate.
All owned live collectors stopped after completion; no service was activated.

## Operations candidate acceptance, 2026-11-14

The native service launcher completed a real 60-second public mainnet BTC run
using an optimized release binary: three finalized child recordings, seven usable
snapshots, 23,971 recording bytes and exact replay for every child. Sampled child
RSS peaked at 10,227,712 bytes and FDs at six. The retained binary SHA-256 is
`76e1371b4f1064c53d6d788083228401aad15bc755026df71329d35af00bbc83`.

Evidence is under `data/service-review-20261114T152600Z-43nMdw/`, including the
launcher report, retained supervisor snapshot/configuration and rendered unit.
An offline user-scope `systemd-analyze verify` passed after fixing scalar
`WorkingDirectory` rendering. System-scope verification could not create
`/run/systemd` on its read-only filesystem. PID 1 here is not systemd, so account,
cgroup enforcement, boot startup and reboot behavior have not been validated.

## Real supervision acceptance, 2026-11-14

Two bounded public mainnet BTC supervision checks passed:

- Initial 120-second window: three finalized runs, 13 usable snapshots, zero
  restarts and 38,557 recording bytes. All comparisons were exact. This preceded
  the parent-liveness guard and final sub-second scheduling adjustment.
- Latest 60-second window: 60.0001 seconds supervisor elapsed, three finalized
  runs, eight usable snapshots, zero restarts and 26,352 recording bytes. Every
  run compared exactly. Peak sampled child RSS was 13,754,368 bytes; sampled FDs
  peaked at six. This exercised the final parent-guard/scheduling build.

Evidence: `data/supervised-live-20261114T142056Z-QBRU19/` and
`data/supervised-final-20261114T142742Z-4QjaY7/`. Each supervisor root retains its
exact executable snapshot, SHA-256, configuration, per-run inspections, control
events, resource samples and final summary. The latest collector snapshot SHA-256
is `5285a7da9f05adf4a9c29808cea9be1e80aaffc90a03c115c5e9760024c668b5`.
These checks exercise normal handovers. Fault/restart behavior was injected in
the offline local TLS/process tests, not claimed as a natural live outage.

## Completed 30-minute live baseline, 2026-11-14

A bounded collector ran throughout the supervision development work. It used the
pre-supervisor collector binary, with its exact binary SHA-256 and Rust source
fingerprints recorded at launch. The event/container formats did not change;
the final current build replayed and inspected it successfully. This validates
a half-hour collector baseline, not a half-hour soak of the new supervisor.

| Measurement | Result |
| --- | --- |
| Requested / recorded duration | 1,800 seconds / 1,800.053 seconds |
| Process return code | 0 |
| Events / usable snapshots | 336 / 147 |
| Connections / connection errors | 1 / 0 |
| Sealed segments | 6 |
| Index plus segment bytes | 356,324 |
| Live versus replay | Exact byte match |
| Independent SHA-256 verification | All six segment hashes and sizes passed |
| Maximum observed snapshot gap | 13.03 seconds |
| Source clock delta range | 353–872 ms; not network RTT |
| Resource samples | 360, sampled every five seconds |
| Maximum sampled RSS / sampled FDs | 13,410,304 bytes / 6 |
| Sampled RSS range after first 30 seconds | 13,402,112–13,410,304 bytes |
| OS child-rusage peak RSS | 48,627,712 bytes |
| Child user/system CPU time | 4.079 / 0.678 seconds |

The sparse `/proc` samples and OS child-rusage peak are different measurements;
both are retained. Do not call sampled RSS the process's absolute peak or infer
leak freedom or high-load readiness from this low-rate half-hour recording.
There was no injected outage in this live run. The 15-second freshness threshold
was preserved and the slow cadence remains an unresolved venue/network question.

Evidence: `data/soak-30m-20261114T140048Z-p136a7e1/` includes `run.json`, the exact
launch command/fingerprints, `process-result.json`, 360 resource samples, the
finalized container, live/replayed quote files, capture/replay summaries,
`inspection.json` and independent `verification.json`. No keys or funds were used.

## Real exchange acceptance, 2026-11-14

Both sessions used mainnet BTC, completed normally, and matched live versus replay
quote output byte for byte. Capture and replay commands exited successfully.

| Measurement | Initial capture | Longer short check |
| --- | --- | --- |
| Requested duration | 30 seconds | 180 seconds |
| Recorded duration | 30.13 seconds | 180.08 seconds |
| Records | 16 | 43 |
| Accepted two-sided snapshots | 3 | 16 |
| Connections | 1 | 1 |
| Connection errors | 0 | 0 |
| Journal bytes | 9,376 | 40,266 |
| Maximum within-connection snapshot gap | 12.42 seconds | 12.50 seconds |

Local evidence, under ignored `data/` (filenames use UTC):

- Initial capture: `live-acceptance-20261114T130544Z-692.*`.
- Three-minute verification artifacts: `live-check-20261114T131230Z-XOS9y2/`,
  including `inspection.json` and both quote files.

These are short collection acceptance checks, not throughput, completeness or
HFT latency benchmarks. Observed source-clock delta during the three-minute run
was 332–559 ms; this includes clock offset/batching and is not network RTT.

## Real rotating collection acceptance, 2026-11-14

`./scripts/verify-collect 60 BTC mainnet 8192` passed against the real public
Hyperliquid endpoint: 60.20 seconds recorded, 21 records, six two-sided snapshots,
one connection, zero connection errors and three sealed segments. Live and replay
quotes matched byte for byte. The 8 KiB segment limit forced rotation without
reconnecting or resetting event order.

Segment sizes were 6,666, 6,921 and 2,726 bytes; index plus data totaled 17,063
bytes. An independent Python `hashlib.sha256` pass verified each recorded digest,
its byte count and quote equality. The container was finalized with no unsealed
tail. Maximum within-connection snapshot gap remained about 12.47 seconds.

Evidence: `data/collect-check-20261114T135002Z-jKisQI/` includes the container,
live/replayed quotes, capture/replay summaries, inspection and
`checksum-verification.json`. Generated captures remain ignored by Git. See
[the format/recovery contract](segmented-format.md) for operational details.

## Feed cadence diagnosis

The largest snapshot gaps were close to the 15-second stall threshold, so an
independent client was compared rather than assuming the Rust adapter was correct.
Three read-only REST samples about 1–2 seconds apart returned changing exchange
timestamps and best prices.

Two concurrent 30-second WebSocket runs then used the same public subscription:
the production Rust CLI and Python `websocket-client==1.9.0` in a temporary virtual
environment. Both used the inherited cloud proxy and verified TLS.

- Rust: four snapshots, maximum gap 12.508 seconds, zero connection errors,
  successful live/replay comparison.
- Independent Python client: four snapshots, maximum gap 12.497 seconds.
- The three post-initial exchange timestamps matched across clients. Each initial
  snapshot was taken at its own subscription time, as expected.

The slow cadence is therefore not unique to the Rust implementation. These
observations do not separate exchange-side behavior from the shared cloud network
path. Do not claim normal full-rate delivery or HFT suitability from this check.
The freshness threshold was not relaxed to mask the observed gaps.

Evidence: `data/live-check-20261114T132008Z-GVDPys/` and
`data/cadence-python-20261114.json`; the independent probe source is retained under
`data/cadence-probe-python-20261114.py`. The Python dependency is diagnostic-only,
not a dependency of the Rust product or its tests.

## Remaining acceptance gates

Fault-test cleanup exposed an environment lifecycle limitation: PID 1 is `tail`
and did not reap two already-exited collectors from earlier supervisor-death
test invocations (PIDs 19804 and 21658). They are inert zombie entries, not running
collectors. The test runner now adopts/reaps its intentional orphan using Linux
child-subreaper support, avoiding new entries. Existing adopted zombies cannot be
reaped by an unrelated process; no signals were sent to infrastructure processes.
Proper init/reaper ownership remains part of the service lifecycle gate.

- Complete the running 24-hour combined-feed experiment and review its actual
  final fault/recovery, replay, gap and resource evidence. New profile acceptance
  and the short fault rehearsal pass; full-window completion is still unverified.
  Complete venue delivery and the source of sparse depth updates remain unproven.
- Extend the implemented per-session retain-and-stop policy with a cross-session
  archive/retention plan. No automatic deletion or restart-in-place exists.
- Extend load and external service/reboot ownership checks. The actual 24-hour
  experiment is underway; shorter completed checks cannot validate that window.
- Paper order lifecycle and risk controls follow collection reliability.

## Combined feed diagnosis, 2026-11-14

Two concurrent five-minute diagnostic probes subscribed to BTC `l2Book`, `bbo`
and `trades`, using one verified-TLS socket per network and the independent Python
client. Mainnet delivered 25 depth messages (maximum gap 12.565 seconds), 3,445
BBO messages (maximum gap 0.563 seconds), and 1,259 trade messages containing 4,900
trades (maximum message gap 1.780 seconds). Fourteen pongs were received. The raw
diagnostic data totaled 2,650,609 bytes; the byte cap was not reached.

Testnet delivered 59 depth messages (maximum gap 5.736 seconds), 286 BBO messages
(maximum gap 10.247 seconds) and 86 trade messages containing 270 trades (maximum
gap 17.669 seconds), plus 14 pongs and 298,748 raw bytes. Neither probe failed.

Fast BBO/trade traffic on the same mainnet socket excludes a general receive-loop,
TLS or connection pause as the whole explanation for sparse depth. These samples
do not separate exchange publication policy from channel-specific path shaping,
prove complete delivery, or establish normal market cadence. Testnet's different
activity/cadence cannot calibrate mainnet latency. Source-clock deltas are not RTT.

Evidence: `data/feed-cadence-mainnet-20261114T151449Z-cn7t_bx_/` and
`data/feed-cadence-testnet-20261114T151449Z-u2o82cfa/` retain raw messages, diagnostic
source and summaries. They are not schema-1 production journals. Existing event
schema, depth normalization and freshness thresholds remain unchanged.

[The accepted feed-profile decision](decisions/0002-feed-profiles.md) defines
separate BBO/depth freshness, explicit observation kinds, recorded timer inputs
and legacy replay compatibility. The schema-2 implementation and its measured
acceptance are documented at the top of this handoff. Strategy development still
follows collection reliability and explicit risk-consumer requirements.
