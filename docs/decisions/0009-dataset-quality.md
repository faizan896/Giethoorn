# Decision 0009: offline dataset quality and candidate manifests

## Scope and versions

Add a stopped-archive quality report before evaluating the first signal study.
The new derived interfaces declare `quality_report_version: 1`,
`quality_manifest_version: 1` and `quality_policy_version: 1`. Engine events,
native normalization, recording containers, audit output and paper schemas are
unchanged. Original release and experiment-runner pins remain unchanged. The
signal study and economic test are not implemented by this report.

## Trust and preservation

The helper holds a shared supervisor lock throughout a fresh native archive
audit, analysis and before/after SHA-256/size/mtime inventories. It uses the
installed trusted auditor without executing the archive's collector snapshot.
Only native-verified inspections and exact normalized quote streams are used.
Original record references, per-feed counts and durations are checked again
while deriving metrics. Changed inputs or executable invalidate all admission
results. A refused audit or failed analysis produces null totals and no admitted
rows, with diagnostics retained rather than repaired evidence or invented zeros.

The dataset manifest binds the source inventory, installed auditor, raw native
audit output, helper code, copied research protocol, view/theme, quality policy,
span artifact, declared visual exposure and candidate partitions. This freezes
references to the original files; it does not duplicate the entire raw archive.
Future consumers must recheck those hashes. Integrity is internal consistency,
not signed venue authenticity or proof of complete delivery.

## Measurements and eligibility

Retained snapshot totals are native-verified two-sided observations across both
feeds, including recovered prefixes. Prefixes stay in the inventory but are not
analyzed or admitted as finalized research inputs. Finalized legacy/depth-only
sources remain visible and are excluded from this schema-2 BBO study.

Each finalized child is a separate monotonic time domain. Native per-feed gap,
count and source-clock-delta diagnostics remain distinct; negative source-clock
deltas are preserved and are not interpreted as network RTT. Process duration,
recorded duration and gaps between original events are separate measurements.

Recorded state durations integrate native observations between original event
times, capped at each fresh state's recorded deadline. A missing transition
beyond that deadline contributes `unobserved_deadline`, not extra fresh time or
a fabricated observed stale event. These are bounded recorded-state spans,
not a guarantee of continuous market delivery.

The fixed study policy admits candidate spans of acknowledged, two-sided BBO
observations with strictly increasing exchange timestamps, gaps no larger than
250 ms and span duration at least 1,250 ms. Equality at 250 ms is accepted. A
connection change, unusable state, repeated exchange timestamp, backward wall
step or wall-minus-monotonic step of at least one second breaks a span. Source
time steps are computed with integers; no interval crosses child boundaries or
extends beyond its last actual BBO observation. Every multi-observation fast
span is retained in a separate bounded JSONL artifact, with its candidate flag.

Five or more candidate children allow whole-child retrospective partitions in
capture/run order: floor(60%) development, floor(20%) validation, remainder test.
Smaller datasets get null partitions and no study admission, even if individual
candidate spans exist. The manifest's admission concerns this retrospective data
partition only. Declared prior visual exposure remains explicit and never creates
a pristine prospective holdout claim. No outcome or P&L selects eligibility.

## Runtime and view

`scripts/mac quality` uses the existing image, source/helper/assets mounted
read-only, no networking and a fresh output directory. The native audit has a
180-second timeout; the whole container command has a 600-second timeout and
10-second forced-stop allowance, plus existing CPU/memory/process limits. No
collector/monitor is started, stopped or replaced. The known run-134 visual
exposure is declared only for its original Mac parent, not later experiments.

Existing inventory bounds are 16 GiB/32,768 files. Analysis limits each stream
to 2 million records and each line to 1 MiB, children to 4,096, span output to
64 MiB, report JSON to 6 MiB and HTML to 8 MiB. Assets are at most 2 MiB each.
Failures retain partial diagnostics without claiming successful completion.

The portable Giethoorn-themed view filters/selects sessions, separates native
freshness from the tighter research cadence and exports the original JSON text.
The raw JSON export preserves integers beyond JavaScript's numeric precision.
Source text is escaped and inserted with text nodes; the page makes no network
requests. Unverified values display as unavailable, never zero.

## Acceptance

Synthetic hand-calculated traces cover boundaries, deadlines, independent feeds,
reconnects, repeated times, clock steps, source mutation and failure paths. Native
acceptance runs on a captured-public-data archive and a separate corrupted copy;
the latter cannot produce quality counts. Browser checks cover filters, selection,
JSON precision, inert hostile strings, mobile layouts and offline operation.
Mac execution and its actual quality totals require local user output.
