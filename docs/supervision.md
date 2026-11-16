# Bounded collector supervision

`supervise` is a Unix public-market-data process supervisor, validated on Linux.
It runs only the bundled `collect` command. It does not execute trades, repair
corrupt data, continue a partial journal in place, or publish environments.

## Run

```sh
./scripts/dev run --locked -- supervise \
  --coin BTC --network mainnet --duration-secs 1800 \
  --run-duration-secs 300 --max-restarts 3 \
  --max-segment-bytes 67108864 --max-run-bytes 268435456 \
  --max-total-recording-bytes 1073741824 \
  --output-dir data/supervision-001
```

Use a **new** output directory. The supervision window includes validation,
handover and backoff, so there are collection gaps between child runs. The last
sub-second remainder elapses without starting another child; actual recording
and supervisor elapsed times are reported separately. This is not a continuous
globally ordered feed.

SIGINT/SIGTERM requests a graceful child stop, followed by a bounded forced-stop
deadline. Unix children monitor their original parent. Parent loss requests a
graceful stop and forces child exit after two seconds if it remains blocked. A
killed supervisor cannot write a final summary: inspect its child data explicitly.
This is not a machine-reboot service manager.

## Artifacts

```text
supervision-001/
  collector.bin               # snapshot of the actual running executable
  configuration.json          # limits and snapshot SHA-256
  supervisor.lock
  events.jsonl                # synchronized control events, not market events
  resources.jsonl             # best-effort child RSS/open-FD samples on Linux
  summary.json                # final report, only after supervisor shutdown
  run-000001/
    session/                  # segmented container v1
    live-quotes.jsonl
    capture.stderr
    inspection.json
  run-000002/
    ...
```

The executable snapshot prevents a development rebuild from changing later child
runs. Its SHA-256 is recorded. Configuration never dumps environment values or
credentials. Each `run-NNNNNN/session` replays independently; the supervision root
is not a segmented recording. Control events, scheduling and telemetry never
enter the deterministic market-state engine.

Resource samples are observations, not a latency benchmark or proof of leak
freedom. Control events are synchronized; resource telemetry is best effort.

`--feed-profile combined` selects schema-2 observations with separate depth/BBO
freshness; profile-specific timing flags are forwarded to the pinned child. The
configuration records the exact event version and policy. Older configurations
without those additive fields retain schema 1. The historical filename
`live-quotes.jsonl` holds schema-1 quotes or schema-2 observations accordingly.
Snapshot counters aggregate market observations, excluding health-only output.
See [feed profiles](feed-profiles.md) and the
[controlled reliability experiment](reliability-experiment.md).

After shutdown, use `audit-supervision --input DIR` to independently recompute
the saved evidence. Keep its output outside the root. See [auditing.md](auditing.md)
for its contract, integrity-versus-health distinction and incomplete-run policy.
The prepared native launcher and systemd candidate are described in
[deployment.md](deployment.md); no service installation is implied.

## Validation and restart policy

The child must exit and release its recording lock before validation. Every
sealed checksum and event must validate. Original quote output is compared with
replay before any restart:

- Finalized recordings require **exact bytes**, even after a network failure.
- An interrupted unfinalized recording may have synchronized an event before
  writing its quote. Original output must be a **byte prefix** of replay. Extra
  or divergent original bytes fail. This is labeled `live_prefix`, not exact or
  finalized; recovery never skips corrupt complete records.

| Collector outcome | Treatment |
| --- | --- |
| 0, normal duration | Validate exact output and schedule a new bounded run |
| 0, interrupted | Validate and stop supervision as interrupted |
| 10 | Exhausted transport/network failure: validate, then bounded retry |
| 11 | Recording/data-validation/output failure: stop, never retry |
| Other nonzero | Fatal by default |
| SIGKILL | Validate readable prefix before a bounded restart |

Retries have a global budget and exponential backoff. HTTP 4xx proxy/upgrade
errors other than 408/429 are permanent and bypass collector and supervisor
retries. TLS verification remains enabled. Zero usable data is fatal by default.
A watchdog bounds stuck collector runs; watchdog failures are not auto-restarted.

Integrity failure, mismatched output, local recording failure or restart-budget
exhaustion stops supervision. Earlier useful data cannot turn a failed final
collector into a successful supervision window. This policy is for public data,
not automatic order-engine recovery.

## Budgets and reports

`--max-total-recording-bytes` caps index/segment lengths across all child attempts,
including failed attempts. Each child receives at most the remaining allowance.
It excludes the executable snapshot, quotes, stderr, control metadata, allocated
filesystem blocks and other sessions. The filesystem reserve is best effort.
Control telemetry has a 64 MiB cap, and there is a 4,096-run cap. No old data is
automatically deleted.

`summary.json` and stdout agree:

- `completed`: validated usable data, successful final run, no restarts.
- `completed_with_restarts`: recovery occurred and a later run succeeded.
- `interrupted`: a requested stop; not a completed time window.
- `failed`: process, watchdog, integrity or restart-policy failure.
- `budget_exhausted`: remaining recording allowance is too small for another run.

Failed/budget-exhausted results have a nonzero exit. `started_runs` counts process
starts; `runs` lists validated attempts only. Events and retained files explain
unvalidated attempts. Recording bytes include failed validation; validated
snapshots exclude corrupt attempts. Missing `summary.json` is not a pass.

## Evidence and remaining work

Offline tests run real collector subprocesses through a local HTTP CONNECT proxy
and verified TLS. They exercise planned handovers, network closure, child SIGKILL,
restart exhaustion, permanent 403, graceful SIGTERM, corrupt seals, stalled TLS,
supervisor death and prefix comparison. No exchange credentials or funds are used.

The supervisor-death test makes its runner a Linux child subreaper and explicitly
waits for the intentionally orphaned collector. Production still needs a proper
init/reaper: stopping execution cannot make an unrelated PID-1 process reap an
already-exited adopted child.

Live evidence and binary fingerprints are recorded in `status.md`. Shorter
baselines are not the 24-hour gate. The full gate, repeated faults under realistic
load, external service/reboot ownership, cross-session archival/retention and the
observed depth/BBO freshness distinction still need validation before production.
