# Decision 0008: independently review stopped local experiments

## Scope and version

Add a read-only review helper and Mac launcher command for stopped experiments,
using the installed image's native `audit-supervision` command. The wrapper's
derived report declares `review_version: 1`; the engine, event, recording,
supervision and native audit schemas remain unchanged. This is a derived view,
not a replacement producer summary or a repair of an incomplete archive.

The first user-reported Mac day attempt failed on a per-child deadline after
about 11.5 hours. Neither that deadline message nor an earlier power/network
outage establishes the underlying cause. Retained source, the last child outcome
and fresh native validation should be examined before changing failure policy or
requesting another long experiment.

## Preservation and execution

`scripts/mac review` requires a stopped owned collector if its container exists.
It uses the retained last-run marker and existing image, mounts the entire source
run and the updated helper read-only, disables networking, and writes only to a
fresh review directory. No image rebuild, live capture, container replacement or
service installation is involved. Existing per-container resource limits apply.

The helper holds a nonblocking shared supervisor lock through inventory and
audit. Source inventories bind each file's size, modification time and SHA-256;
local wrapper receipts beside the experiment are included. Inputs reject
symlinks/nonregular files and are limited to 32,768 files/16 GiB in total.
Metadata is limited to 16 MiB; the installed executable is bounded and hashed
before/after. The native subprocess has no stdin, a finite timeout (180 seconds
by default, at most 600) and a 16 MiB bound per diagnostic stream. The auditor
never executes the retained collector snapshot. The helper does not generate
missing summaries, alter source files, or combine interrupted windows.

## Interpretation

An accepted native envelope plus unchanged input yields `integrity: verified`.
Refusal, timeout, malformed output or changed input yields `audit_unverified`,
null audited counts, retained diagnostics and a nonzero review exit. Preflight
refusal is also nonzero. Reported producer metadata is labelled separately from
recomputed audit values. Finalized child recordings and recovered prefixes are
counted separately; prefixes do not promise intact tails or continuous coverage.

The review can succeed for an operationally failed archive. Full-day completion
also requires an 86,400-second request, a native completed window, both injected
recoveries, and successful experiment/local completion receipts. A completed
90-second rehearsal or correctly preserved failure cannot become a day pass.
Archive integrity is internal consistency, not authenticated venue provenance.

## Verification

Unit tests cover failed-versus-completed interpretation, refused/malformed native
results, timeouts, source/receipt mutation, active locks, missing summaries,
symlinks, existing/unsafe output paths, and Mac read-only/offline mounts and
running-collector refusal. Native integration checks use the existing image and
separate evidence directories; synthetic failures and mutations must be labelled
as such. Mac archives remain unverified here until their local review is run.
