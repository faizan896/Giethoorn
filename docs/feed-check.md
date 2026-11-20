# One short fresh recording check

The [first supplied Mac public-data result](mac-feed-check-results.md) completes
all four stages with 1,256 BBO messages/native opportunities and exact replay.

Open Docker Desktop, install the feed-check source update, and run:

```sh
bash scripts/mac feed-check
```

The command requests one 120-second public BTC/mainnet recording. Keep the Mac
plugged in with its lid open and this Terminal open. The launcher holds
`caffeinate` for its own foreground process on macOS. It reuses the installed
image and needs no image rebuild, host Rust/Python, credentials or paid server.

After recording, a separate container checks the retained data without networking.
The portable report opens in the browser and the Terminal prints capture/replay/
integrity/cadence outcomes plus raw/native counts, millisecond percentiles and gap
bins. Paste that output for review. A failure has an explicit status rather than
zero measurements or a replacement attempt.

## Saved evidence

Each invocation creates a separate `~/GiethoornData/feed-check-TIMESTAMP-SUFFIX/`:

- `launch-request.txt`, bounded container logs and private container IDs describe
  this invocation.
- `capture/request.json` freezes policy, limits, origin, image identity and native/
  helper/template fingerprints before connecting. `session/` holds the original
  checksummed source, `live.jsonl` its original normalized output, and the capture
  result retains native exit/timeout/budget diagnostics and artifact fingerprints.
- `offline/report/` holds input inventories, inspection/replay/native child
  receipts, mark-only export, `intervals.jsonl`, measurement JSON, the final
  `feed-check-report.json` and portable `feed-check.html`.

Failed preflight, interruption, disk/output refusal or outer timeout can leave
partial evidence without a final report. Container diagnostics remain in the
invocation directory. The launcher preserves the capture's nonzero exit even if
inspection can verify its retained prefix. It never updates `last-run`, stops an
existing collector/monitor, repairs old evidence or automatically repeats a
failed attempt. Each manual invocation is a new attempt with its own identity.

## What passes

The capture process must exit successfully; the source must be finalized with
duration-elapsed end reason, at least the requested recorded duration, schema 2,
the exact requested coin/network/policy and observed usable combined data.
Independent native replay must reproduce the complete original normalized stream
byte for byte. Valid checksums alone do not prove a completed recording.

Only then does the native BBO mark-only adapter supply source-linked events to
the unchanged cadence version-1 rules. Raw messages and native opportunities stay
separate, within each connection. Empty/single-observation series retain
unavailable quantiles; leading/trailing silence remains censored. Repeated/older/
unusable messages, clock-step flags and complete interval receipts are retained.
See [cadence definitions](cadence.md). There is no preceding cost/expiry bundle
for this new recording and none is fabricated.

The full capture inventory, native executable and producer assets are bound
before/after. Any change invalidates admitted metrics. Missing/bad/oversized
source is not truncated or replaced. The offline container has only a read-only
capture mount and a separate writable output mount, without a writable alias
back to capture evidence. The final JSON download preserves exact large integers.

## Fixed configuration and bounds

The [frozen protocol](fresh-capture-plan.md) requests combined feeds, 15,000-ms
depth freshness, 2,000-ms BBO freshness, 250-ms timers and at most three native
reconnects. It injects no faults and launches no replacement capture process.
The native process uses direct verified TLS and the existing image trust store;
inherited proxy and TLS configuration overrides are removed for these children.

Capture has a 16-MiB journal budget, 1-MiB segments, a 64-MiB capture-evidence
bound and 180-second native deadline. Offline work has a 120-second deadline,
30 seconds per native child, 16-MiB native file bounds, 32-MiB interval bounds,
256-MiB total evidence admission and a 1-GiB free-space reserve. Native mark-only
source limits remain 16 MiB and fewer than 10,000 events. Budget exhaustion
retains an explicit failed/not-run stage. The wrapper uses 190/130-second
container limits with bounded termination, and a 360-second host watchdog that
targets only private containers carrying this invocation's label/ID. Signals
also clean up only those owned children. Artifacts are never deleted by cleanup.

The native executable must match the existing Mac runtime fingerprint; a changed
Docker tag/image or producer is refused. Resource and disk limits are admission/
termination controls, not filesystem quotas or real-time guarantees. A killed
stage can retain its bounded prefix without an HTML report.

This short check measures the current recording/replay path. It does not complete
the operational day gate, identify the cause of old gaps, estimate actual order
latency/fill probability or establish profitability. Synthetic local-server
software acceptance stays separate from actual subsequent Mac public-data runs.

See [decision 0014](decisions/0014-fresh-capture-check.md).
