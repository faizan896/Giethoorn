# Offline supervision audit

Use `audit-supervision` after a supervisor has stopped and written its final
summary. This is a read-only recomputation, not a repair or an execution tool.

```sh
./scripts/dev run --locked -- audit-supervision --input data/supervision-001 \
  > data/supervision-001.audit.json
```

Keep the audit output **outside** the supervision root. Unknown files inside a
root are rejected. Active supervisors are rejected through the shared/exclusive
root lock. A missing or partial final summary is not accepted; inspect individual
`run-NNNNNN/session` directories with explicit recovery instead.

## What is recomputed

- SHA-256 of the retained collector executable, checked against configuration and summary.
- Control version, contiguous sequence, monotonic time, start/stop and child lifecycle.
- Child identity/exit status, validation-before-restart, retry class, counter and backoff.
- Resource sample ownership/timing and RSS/FD maxima, without trusting cached maxima.
- Every recorded segment's checksum, size, record order and market-data validity.
- Recorded market/network/schema/profile policy against supervisor configuration.
- Exact quote bytes for finalized data, or the original byte prefix for crash recovery.
- Cached inspections against freshly derived inspections, not just the stored counters.
- Per-run and aggregate snapshots, bytes, finalization, policy limits and canonical paths.
- Successful exits against actual usable data and event end reason.

Symlinks, noncanonical run names, unexpected artifacts, unsupported versions,
missing records, changed hashes, altered reports and inconsistent evidence fail.
Inputs are bounded and the command neither executes the snapshot nor rewrites files.
The segmented container's advisory locking/immutability expectations still apply.

## Integrity is different from operating success

`integrity: verified` means the saved evidence is internally consistent with the
actual recordings. A correctly reported failed or interrupted run can pass that
integrity check. Always examine `supervisor_status` and `full_window_completed`.

`full_window_completed` requires a completed supervisor status and a measured
window at least as long as requested. This also exposes older producer versions
that rounded off a sub-second scheduling remainder without rejecting otherwise
valid data. It does not establish continuous coverage: handover/backoff gaps are
part of supervision and must be considered separately by research consumers.

The audit is not a signature or a proof of exchange authenticity. A party able to
rewrite all data, checksums and metadata can forge evidence. It also cannot prove
that an exchange sent no missing messages or that a quiet/slow feed was complete.

## Tests

Real local subprocess/TLS scenarios verify healthy, recovered, interrupted and
failed outcomes. Mutations cover aggregate counts, market identity, control
events, inspection caches, resource maxima, snapshot bytes, unexpected directories
and missing summaries. The live-output comparison separately rejects divergent
or extra bytes. A finalized failed run is not relabeled healthy by changing its
exit metadata.
