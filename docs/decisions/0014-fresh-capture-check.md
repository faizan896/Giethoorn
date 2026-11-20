# Decision: fresh recording check version 1

Status: implemented. New namespaces are `feed_check_policy_version: 1`,
`feed_check_request_version: 1`, `feed_check_capture_version: 1` and
`feed_check_report_version: 1`. Existing native recording, normalization, paper,
cadence, cost, expiry and signal versions and their producer assets remain
unchanged. The native executable/image is reused rather than rebuilt.

The [first Mac cadence result](../mac-cadence-results.md) reports selected stored
observations, not current capture health or actual execution behavior. The
[predeclared short check](../fresh-capture-plan.md) requests a separate 120-second
capture and exact replay without deliberately injecting faults or choosing a
replacement sample by its outcome. It introduces no signal or order generation.

## Separate capture and offline verification

Freeze coin/network, combined feed/freshness/timer/storage settings, at most three
native reconnects, code/assets, installed executable and image identity before
connecting. Production CLI exposes no overrides for duration, routing, origin or
these limits. Remove inherited proxy/TLS overrides; use direct verified TLS and
the image trust store. Synthetic test routing uses an explicit ephemeral CA and
a local-only TLS WebSocket peer in the test harness, without changing production
transport or disabling certificate/hostname checks. Label that source synthetic.

The Mac wrapper creates private per-invocation evidence and runs capture once in
a networked, constrained container. After its writer stops, a different container
with no network receives read-only capture evidence and disjoint writable audit
output. The original collector/monitor and `last-run` remain untouched. Capture
and audit errors retain nonzero exit and their own logs/results. Native bounded
reconnects are source events, not replacement capture processes.

Bind regular-file inventories and producer fingerprints before/after. A change
invalidates all admitted checks/metrics. Require capture success, native source
integrity, finalized duration-elapsed recording, at least requested recorded
duration, exact schema/policy/coin/network and observed usable combined data.
Native replay must match original live normalized bytes. A valid incomplete or
failed-session prefix can pass integrity diagnosis without passing the check.

After those gates, run the pinned native BBO mark-only adapter and unchanged
cadence measurements. Preserve distinct raw/native series, connection domains,
unusable/repeated/older source context, zero intervals, censored edges, clock flags,
exact percentiles/bins and all interval receipts. A fresh source has no original
cost/expiry experiment; do not claim to preserve a nonexistent bundle.

## Bounds and visible outcomes

Native subprocess groups have bounded termination/kill, regular file limits,
disk/output monitoring and finite deadlines. Refuse source/event limits rather
than truncating. Reserve final report space; retain partial output on refusal or
interruption. Separate stage statuses distinguish verified checks, failures and
not-run work; source changes make metrics unavailable. A successful inspect exit
or zero observations cannot manufacture a completed capture/replay result.

The wrapper adds container timeouts and a host watchdog. Cleanup addresses only
the exact private container IDs with this invocation's matching label. It holds
macOS `caffeinate` for its own process and retains evidence on exit. The portable
HTML identifies a fresh check, exposes stage outcomes and exact JSON export,
supports sparse/unavailable measurements and works offline on desktop/mobile.

Acceptance exercises native CLI capture against a local CONNECT/TLS/WebSocket
server, exact replay and native cadence, denied/empty feeds, timeout, disk/output
refusal, corruption, producer/image/input changes, no automatic replacement and
original-state preservation. An untrusted test peer remains rejected. Full-duration
synthetic acceptance and actual Mac public-data acceptance are distinct receipts.
This remains an engineering check alongside the outstanding day gate and actual
execution calibration, without an economic or deployment-readiness claim.
