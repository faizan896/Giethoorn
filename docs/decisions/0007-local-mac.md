# Decision 0007: an Intel Mac local collection package

## Scope

Use Docker Desktop to run the existing Linux collector/fault harness on the
user's Intel Mac. No engine, event, ledger or strict supervision schema changes.
No service installation, environment publication, Git push, authenticated orders
or paid infrastructure. The new transfer manifest and local-launch receipts
declare their own version 1. Mac host/VM acceptance remains distinct from a Linux
container test and from the interrupted cloud 24-hour attempts.

## Build and transfer

The image pins Rust 1.91.1 and Debian base manifests by digest and uses the crate
lockfile. A small number of build layers avoids duplicating large toolchains on
copy-based Docker storage drivers. Build steps run native/Python tests. Runtime
code is made readable by an ordinary user before copying it into a slim image;
the final image checks helper readability and exact synthetic ledger replay as
UID 1000. The Mac script passes the Mac user's UID/GID for the shared data folder.

The ZIP exporter uses explicit source roots and normalized file permissions.
It excludes `.git`, target binaries, raw recording archives, environment files,
common private-key/certificate containers, caches and logs. It rejects source
symlinks and oversized exports. An optional rendered public-data Paper/Batch Lab
can be included as a clearly saved preview. Every exported file has a SHA-256
receipt. These are export checks, not a general-purpose secret scanner.

Source delivery includes unpushed workspace files. It does not assume GitHub
contains the latest implementation. The installed Docker Desktop and the Mac's
actual first build/network/rehearsal still require user execution locally.

## Local lifecycle and persistence

The Bash 3.2-compatible `scripts/mac` checks for a working Linux Docker engine and
at least 2 VM CPUs/4 GiB RAM before building. `setup` never launches a live run.
`demo` generates the synthetic offline lab. `rehearsal` requests 90 seconds with
disconnect at 10 seconds and collector kill at 25 seconds. `start` requests a new
24-hour window with the original 30/60-second fault schedule.

Containers have an init process, ordinary user identity, dropped capabilities,
read-only root, bounded tmpfs/memory/processes/CPU/logs and finite stop deadlines.
Only the collector's new host run directory is writable. The monitor mounts that
directory read-only and is published on loopback port 3000. A failed monitor
launch stops the just-created collector. Stop/remove operations check ownership
labels; source directories and recordings are never removed. Console logs from
an earlier stopped collector are retained before its container is replaced.

The foreground watcher binds to the specific container ID, so a later container
with the same name cannot accidentally receive its stop signal. Mac `caffeinate`
holds idle/AC sleep assertions during that watcher. This is not an OS service or
protection against lid closure, Docker restart, host shutdown or forced termination.
Keep the charger connected, lid and Terminal open. Data lives under the Mac's
`~/GiethoornData`, independently of the downloaded source or container lifetime.

## Direct route without editing the old experiment

The cloud experiment runner and release remain byte-identical to their retained
pins. `ops/run_local.py` composes the existing runner with a bounded loopback-only
CONNECT relay that opens only the declared Hyperliquid public host on port 443.
Its relays transport opaque bytes; venue TLS is still verified by the collector.
The existing fault schedule, owned-process checks, failure policy, cleanup and
final native audit are reused. The direct route has two local relay hops; it is
not a latency benchmark. An inherited-proxy mode exists for the cloud test route.

Proxy environment is restored on success/failure; URLs/credentials are omitted
from receipts and error text. `local-run.json` binds both Python source hashes and
declares the route/requested duration. `local-result.json` reports the underlying
experiment result. `verified_24_hour_window` is true only for an actually completed
86,400-second request. A completed rehearsal does not satisfy that field. Missing
final evidence or nonzero process exit is not a successful collection window.

## Verification limits

Unit tests exercise relay payload isolation/target rejection, environment restore,
failed/short-run receipts, invalid schedules, Docker engine/resource preflight,
foreign-container refusal, monitor-launch cleanup, export exclusions/symlinks,
archive permissions and checksums. Container checks run native tests and the
actual non-root runtime. A short public-data rehearsal tests the configured cloud
route; direct relay forwarding has a local synthetic protocol test. The Mac's
direct connection, VM filesystem behavior and 24-hour window remain local gates.

Cloud-only certificate trust may be mounted as a BuildKit secret for testing.
That adaptation and certificate are outside the exported source ZIP and runtime
image. User builds retain normal public-root verification. No verification is
disabled and no proxy credential is exported. See [local instructions](../local-mac.md)
and [current evidence](../status.md).
