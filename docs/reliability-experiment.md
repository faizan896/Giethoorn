# Bounded reliability experiment

`ops/run_reliability.py` runs a finite public BTC combined-feed supervisor with two
controlled faults. It uses the existing HTTP CONNECT route through a loopback
byte-forwarder. The collector still verifies venue TLS end to end; the experiment
neither terminates TLS nor installs a service. No credentials enter evidence.

## Run

Build and verify the release first. Use a new experiment directory:

```sh
CARGO_BUILD_JOBS=4 ./scripts/dev build --release --locked
python3 ops/run_reliability.py --binary target/release/giethoorn \
  --output-dir data/reliability-24h-001
```

Defaults: 86,400-second window, 300-second child runs, three reconnects per child,
five supervisor restarts, 8 MiB segments, 256 MiB per child, 4 GiB total recording
budget, 1 GiB free-space reserve and five-second child resource samples. Recording
budgets exclude stdout, executable, metadata and other processes; monitor the
filesystem as well. There is no deletion, resume, daemon installation or reboot
claim. A machine/environment restart interrupts this experiment.

At 30 seconds, after both feeds have become fresh, the forwarder shuts down the
owned live tunnel. The collector must reconnect and produce acknowledged usable
data on a new connection within the same child. At 60 seconds the runner checks
the current collector's parent and retained executable, then sends SIGKILL only
to that collector. The supervisor must validate its crash prefix before restarting.
The next child must produce usable combined data. Each recovery has a bounded
deadline; missing fault/recovery evidence stops the experiment.

The loopback forwarder accepts only the chosen Hyperliquid public host on port
443, and forwards through the inherited HTTP proxy with its existing authentication.
It has bounded headers, sockets, chunks and handler concurrency. It is an experiment
component on the measured route, not evidence of direct-path venue latency. After
the two recoveries, the runner stops parsing active quote files repeatedly.

A shorter rehearsal uses the same code:

```sh
python3 ops/run_reliability.py --binary target/release/giethoorn \
  --output-dir data/reliability-rehearsal-001 \
  --duration-secs 90 --run-duration-secs 45 \
  --disconnect-at-secs 10 --kill-at-secs 25
```

## Evidence and completion

The outer experiment contains:

- `run.json`: exact command and collector/runner hashes, with no environment dump.
- `faults.jsonl`: synchronized experiment/tunnel/fault/recovery events.
- `report.json` and `command.stderr`: the supervisor command outputs.
- `supervision/`: strict supervisor archive with the actual executable snapshot,
  per-child recordings, inspections, control events and resource samples.
- `audit.json`: read-only full-archive audit, written only after a successful window.
- `experiment.json`: final experiment status, written only when the runner finishes.

Keep diagnostics outside `supervision/`. During a run, control/resource logs and
closed children show progress. The newest child is active: inspect/replay/audit
must not be forced through its writer lock. Missing final experiment/audit files
mean completion has not been established.

A successful experiment requires both observed recoveries, a successful complete
supervisor window and a fresh archive audit with `full_window_completed: true`.
Failed, interrupted, incomplete or budget-exhausted work is retained and never
relabeled a pass. Hashes do not authenticate the exchange or prove all messages
were delivered. The injected disconnect is experimental, not a natural outage.

SIGINT/SIGTERM asks the owned supervisor to stop, retaining diagnostics. This
container lacks a proper system init; system-manager ownership, boot/reboot and
cross-session archival remain separate acceptance gates. A completed 90-second
rehearsal is not the actual 24-hour result. See [status.md](status.md) for current
measured results and any running experiment path.

If the entire runner/supervisor disappears, preserve that attempt. A missing final
summary cannot be repaired into a completed window. Inspect/replay each stopped
child with explicit recovery, require exact output for finalized data and a valid
original-output prefix for an unfinalized crash tail. Keep recovery evidence
outside the strict supervision root. Start any replacement experiment in a new
directory with a new full time window; never add interrupted hours to claim a
24-hour pass. A Cloud runtime remaining available for that window is an operational
dependency, not something a collector restart policy can guarantee.
