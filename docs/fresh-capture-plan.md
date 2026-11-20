# Short fresh recording check

Status: protocol frozen before a new attempt. A dedicated Mac launcher is not
implemented and no new capture has been started for this protocol. This follows
the [accepted Mac cadence readout](mac-cadence-results.md), which describes four
already explored five-minute recordings.

Check ID: `btc-feed-check-001`. Question: can the current Mac recording path
complete one bounded, fault-free-requested public-data session and reproduce its
retained source exactly? This is an engineering check, not a new signal test or
an experiment identifying the source of the historical gaps. Different date,
market activity and network conditions prevent a causal before/after comparison.

## Fixed attempt

- Use the existing `giethoorn-local:0.1.0` image and installed native executable,
  recording their identities before/after. Require the existing runtime binary
  fingerprint `ed10624d0bc6a660e1aa6f8689ef0f42529b3e3d9dff76c5edcf9be93694ba1e`.
- Run one direct public BTC/mainnet `collect` process for 120 seconds, with an
  explicit combined profile, depth freshness 15,000 ms, BBO freshness 2,000 ms
  and feed timer 250 ms. Retain all channels and native connection transitions.
- Freeze 1-MiB segments, 16-MiB whole-session journal budget and a 1-GiB minimum
  free-disk reserve. Additional stdout, audits and exports need independent
  create-new file/total-output bounds; a journal cap alone does not cover them.
- Use a new `~/GiethoornData/feed-check-TIMESTAMP-SUFFIX/` folder. Record a request
  receipt containing the complete settings, source/tool hashes and limits before
  connecting. Never replace the existing `last-run` pointer or collector/monitor.
- Reuse ordinary-user Docker limits: read-only root, capability drop, isolated
  writable output/tmp, 768-MiB memory, two CPUs and 64 processes. Keep the Mac
  plugged in with its lid open; the eventual foreground launcher should hold
  `caffeinate` for its own process. Do not stop or claim ownership of another run.
- Inject no disconnect, crash or scheduled restart. Native bounded reconnects
  caused by actual events remain recorded. Do not automatically rerun the entire
  capture or substitute a quieter/busier sample after seeing its outcome.

The capture child has a 180-second wall timeout, with bounded termination/kill
and retained logs. Requesting 120 seconds does not guarantee a successful or
usable session. Timeout, failed exit, insufficient disk, source/event-limit
refusal, empty data or an interrupted prefix stays explicit evidence. Any later
attempt gets a new identity while this attempt remains in the inventory.

## Independent offline checks

After the writer stops, run audit children without networking against the saved
source. Bind regular files, native binary and producer assets before/after;
changes invalidate metrics. Apply a 30-second per-native-call bound and a
120-second offline stage bound, plus a 360-second whole-command timeout. Cap
all retained output at 256 MiB with a 1-GiB free-space reserve. Failed stages
retain their artifacts without pretending a final report exists.

For a completed native capture, require `end_reason: completed`, a finalized
checksummed collection, schema 2 and exact requested policy. Replay original
source into a new output and compare the complete live/replay normalized streams
byte for byte. A successful inspect/replay exit alone does not establish that
the original capture succeeded. Recovered prefixes can support an explicit
integrity diagnosis; they cannot pass this completed-session check.

Only after successful source verification, use the unchanged native BBO mark-only
adapter and cadence version-1 measurement rules. Keep its existing 16-MiB source
and 10,000-event limits; a limit failure is not-run/unavailable, never truncation
or a replacement sample. Measure raw messages and native opportunities separately
inside each connection, including unusable/repeated/older observations, source
clock flags, censored edges, nearest-rank quantiles and all interval receipts.
Do not fabricate a preceding cost/expiry experiment for this new source.

The eventual portable view must identify this fresh source and fixed request,
show capture/replay/measurement outcomes independently, and label incomplete or
unavailable measurements. It must not claim to preserve an original expiry
bundle that does not exist. Terminal output should include sufficient counts and
timings for the user to paste one result, without uploading private raw recordings.

## Acceptance and scope

Before delivery, exercise the native wrapper against a deterministic local
WebSocket server for successful capture, failed/empty capture, process timeout,
corrupted source and budget refusal. Verify byte-identical replay, fingerprints,
explicit unavailable outcomes, no automatic rerun and no existing-run mutation.
Test report loading and exact JSON export offline on desktop/mobile. Synthetic
server results stay separate from a subsequent actual Mac attempt.

Completion checks the current path for two minutes, not the outstanding full-day
gate. A changed cadence remains descriptive. Verified venue publishing/order
semantics and actual execution telemetry are separate requirements for a
calibrated fill/latency model; a quiet public stream cannot provide those alone.
The already explored R001/cost datasets and policy remain frozen. No wallet,
live strategy or economic confirmation is introduced by this protocol.
