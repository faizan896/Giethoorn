# Review recorded-data quality

Run `bash scripts/mac quality` from your updated Mac source directory, with
Docker open and the collector stopped. This audits the last retained experiment
and opens `~/GiethoornData/quality-*/report/quality.html` in your browser. It uses
the existing image; host Python, an image rebuild and another collection are
not required. Original files are mounted read-only and networking is disabled.

The update consists of `scripts/mac`, `ops/quality_local.py`, `web/quality.html`
and `docs/research-plan.md`. The previously installed `ops/review_local.py` is
also required. Update all four files from one source revision before running.

## Read the result

The report shows all children, finalized versus recovered data, native BBO/depth
counts and gaps, process versus recorded duration, clock discontinuities, recorded
feed-state durations, and BBO spans that meet the fixed research cadence. Select
a row to inspect it, filter candidate/excluded/recovered recordings, or save the
report JSON. The saved page works offline and uses the shared Giethoorn theme.

Native feed freshness follows the source policy. The first study additionally
needs BBO observations no more than 250 ms apart for at least 1.25 seconds.
Repeated exchange times, an unusable feed, reconnects or clock discontinuities
break those spans. A long gap is not filled with extra fresh time. Reported fast
time is a sum of separate spans, not continuous coverage or execution latency.

Candidate does not mean every event in that child is eligible, or that a signal
will be profitable. Recovered prefixes remain preserved but excluded from this
finalized-source study. A valid failed parent can supply finalized candidates;
its full-day reliability gate remains incomplete. Data with no qualifying span
is retained with an explicit exclusion reason, not retuned after outcomes.

With at least five candidate children, their frozen chronological split is
60% development, 20% validation and the remainder retrospective test, rounded
down for the first two groups. Fewer than five yield unavailable partitions and
no study admission. The original run-134 chart inspection is declared for its
original parent; this is not a claim of exhaustive viewing history or a pristine
prospective holdout. Additional exposure can be declared through the helper's
repeatable `--inspected-child` option when using the generic CLI.

## Retained evidence

The new report directory includes:

- `quality-report.json` and `quality.html`: measurements and portable view.
- `dataset-manifest.json`: source/auditor/helper/protocol/policy/view fingerprints,
  declared visual exposure and candidate partition membership.
- `source-before.json` and `source-after.json`: original-file inventories.
- `fast-spans.jsonl`: every derived multi-observation span and its source references.
- `research-protocol.md` and `quality-policy.json`: the exact rules used.
- `audit/`: the fresh native audit, diagnostics and its preservation receipts.

The manifest binds the original files rather than copying the entire archive.
Later research must check those hashes again. A refused native audit, changed
source or failed analysis produces a nonzero exit, null quality totals and no
admission. A diagnostic HTML page may still open; unavailable is not zero. A
process kill or exhausted filesystem can leave only partial artifacts. Keep
those diagnostics and do not repair or replace the original archive.

The report's completion means a quality review finished, not a passed day window
or a strategy result. The next implementation is the fixed prediction study in
[the research plan](research-plan.md), followed by separately specified costed
execution tests. See [decision 0009](decisions/0009-dataset-quality.md).
