# Giethoorn on your Intel Mac

This package runs the collector and research tools on your own Mac, without a
paid VPS. Source is available on the repository's `mac-local-setup` branch.
Docker Desktop supplies the Linux environment required by the fault-test runner.
The user reports a successful build, demo, short recovery rehearsal and local
archive audit. The day run stopped early; its verified recordings do not establish
a completed 24-hour collection window. See [current results](status.md).

## Install Docker Desktop once

Your machine is an Intel MacBook Pro running macOS 26.7.1. Use the Intel installer:

<https://desktop.docker.com/mac/main/amd64/Docker.dmg>

Open the downloaded DMG, drag Docker into Applications, and open Docker. Complete
its normal first-run setup and wait for the engine to report that it is running.
The install guide is <https://docs.docker.com/desktop/setup/install/mac-install/>.
Host Rust, Python, Git and a VPS account are not required for these steps.

For image compilation, allocate at least 2 CPUs and 4 GB RAM to Docker's Linux VM
and keep roughly 15 GB free for images/build cache plus recordings. These are
starting allocations, not measured capacity guarantees for this Mac. The running
collector and monitor each have a 768 MiB container limit and no privileged access.

## Unzip and set up

If the chat's artifact download fails, a reviewed source snapshot can be delivered
through the existing `faizan896/Giethoorn` repository's `mac-local-setup` branch.
That source delivery was uploaded with the user's approval. Select the branch in GitHub,
choose **Code → Download ZIP**, and extract it. Its directory will normally be
`~/Downloads/Giethoorn-mac-local-setup`; run the commands below from that directory
instead. This route does not need Git or developer tools installed on the Mac.

Cloud file preview can return only a prefix of a large text file. Do not infer
that an encoded package was transferred because the visible prefix was copied.
A `heredoc>` prompt means the shell is waiting for the end of incomplete input;
Control+C returns to the normal prompt. Source transfer must complete before
running the setup or recovery rehearsal.

Unzip `Giethoorn-Mac.zip` in Downloads. Open Terminal and run:

```sh
cd ~/Downloads/Giethoorn-Mac
./scripts/mac setup
```

The first build downloads Linux/Rust dependencies, compiles the application and
runs its native and Python tests. Allow several minutes. Setup exits on failure;
keep the Terminal output if it fails. It never starts a live collection by itself.
The container compiles its own Linux executable instead of using a cloud binary.

The optional `preview/` folder contains portable saved Paper Lab and Batch Lab
views. Double-click those HTML files to inspect the earlier saved simulations;
they make no network requests and do not show a running collector.

## First run the offline lab

```sh
./scripts/mac demo
```

This generates and opens an explicitly synthetic Paper Lab. Its output is stored
in a new folder under `~/GiethoornData`, outside Downloads and outside containers.

## Then run the 90-second live rehearsal

Keep the Mac plugged in, its lid open, Docker running and this Terminal open:

```sh
./scripts/mac rehearsal
```

The monitor opens at <http://127.0.0.1:3000>. The experiment must recover from an
injected connection drop and one controlled collector kill, then pass the native
archive audit. A failed rehearsal remains a failure with its diagnostics retained.
Opening a monitor or receiving subscription acknowledgements is not acceptance.

The script uses macOS `caffeinate` while waiting for the finite experiment. The
display can sleep; keep the lid open and charger connected. This does not protect
against shutdown, a Docker restart, forcibly killing Terminal or a host crash.
Closing Terminal or pressing Ctrl+C asks the collector to stop. A stopped or
interrupted attempt cannot be combined with a later one into a passed window.

## Start a fresh 24-hour window after reviewing the rehearsal

```sh
./scripts/mac start
```

This starts a new 86,400-second experiment and opens its own monitor. It does not
resume the rehearsal or either interrupted cloud attempt. The original finite
fault schedule and strict audit criteria remain in force. The direct launcher
uses bounded local CONNECT relays; venue TLS remains end to end. The route is
declared in `run/local-run.json`. This is not a latency benchmark or trading mode.

Recordings and all audit artifacts persist in `~/GiethoornData/start-*/run/`:

- `local-run.json` binds the local launcher and unchanged experiment runner.
- `experiment/` contains configuration, logs, faults and the strict supervision archive.
- `experiment/experiment.json` and `experiment/audit.json` are final evidence.
- `local-result.json` distinguishes a verified requested window from a verified
  24-hour window. Missing or failed final evidence is not a pass.

The experiment admits up to 4 GiB of recording data and keeps a 1 GiB disk reserve;
these do not cover every log, image, build cache or other application on the Mac.
Docker console logs are separately capped. Earlier recordings are never pruned.

## Review a stopped run before starting another

From your existing source directory, with Docker open:

```sh
bash scripts/mac review
```

This audits the run selected by `~/GiethoornData/last-run`. It uses the existing
image's native auditor and the downloaded `ops/review_local.py`; updating these
two source files does not require an image rebuild. The source run and helper
are mounted read-only, networking is disabled, and derived reports go into a new
`~/GiethoornData/review-*/report/` directory. It does not start, stop or remove the
collector or its monitor. A running collector is refused.

Read `reported_reason`, `reported_elapsed` and `last_reported_run` for the saved
failure. `integrity: verified` means the native auditor recomputed the retained
archive successfully; a failed run can still have intact, useful recordings.
`source_unchanged` compares SHA-256, size and modification time before and after,
including the local wrapper receipts. Finalized recordings and recovered prefixes
are counted separately. A recovered prefix may have a lost tail; neither result
establishes continuous market coverage or profitable trading.

The command exits zero when the review verifies evidence, even if the collector
failed. `verified_24_hour_window` remains false unless the native full-window
audit and local/experiment completion receipts all establish an actual day pass.
Missing final summaries or corrupt data yield `audit_unverified` and a nonzero
exit, retaining native diagnostics without repairing anything. A separate
per-recording recovery may then be needed. See [the audit guide](auditing.md).

The first Mac day attempt reported a deadline failure after about 11 hours
30 minutes. Preserve it and review its data before deciding on another run;
interrupted hours cannot be combined into a full-day pass. Collection and offline
research are separate milestones, so no immediate repeat day run is necessary.

## Open your recorded prices in Paper Lab

After reviewing the archive, select one finalized child number from that review:

```sh
bash scripts/mac replay 134
```

Child 134 is the last finalized recording from the user's first Mac day attempt.
Its native audit reports 2,049 observations and exact quote replay despite the
parent's watchdog failure. The argument is an explicit child number in the last
retained run, not a count of recordings or a strategy selection. Leading zeros
are accepted. Unavailable/invalid numbers and a running collector are refused.

This command uses the existing image's recorded-market adapter, with source
mounted read-only and networking disabled. It validates and copies that one
session, independently checks the mapped paper ledger, then opens
`~/GiethoornData/replay-*/lab/paper-lab.html` in your browser. The saved HTML is
portable and works offline. `source-selection.txt` records the selected parent,
child, feed and scope. The core adapter's source hashes bind the copied recording.

Use the playback controls to inspect recorded BTC BBO prices, spreads, event times
and historical feed health. It shows one session, not the full 11.5-hour dataset
or current prices. Orders/fills are disabled; its flat assumed balance is not a
strategy result. Recovered prefixes cannot be passed off as finalized inputs.
The parent day gate stays incomplete. The source remains unchanged and each
invocation keeps its own output. A failed replay or 180-second timeout retains
diagnostics instead of opening a successful-looking view. Only the launcher
needs updating for this command; no Docker rebuild or host Python is required.

## Review all recordings for research suitability

After updating the quality files, run:

```sh
bash scripts/mac quality
```

This opens a saved data-quality report for the whole last stopped archive, using
the existing image. It separates native feed freshness from the first study's
tighter BBO cadence, preserves recovered prefixes outside the candidate dataset,
and keeps a hashed source/protocol manifest. No raw archive is uploaded or
changed. See [how to read the quality report](quality.md) for fields and limits.

## Run the first fixed signal study

After the study update, use the identifier printed by your quality run:

```sh
bash scripts/mac study quality-20261117T125619Z-mAfC1j
```

This uses that frozen snapshot and source, defaulting to development only. The
saved browser report shows prediction counts, missing labels and same-sample
directional baselines. Validation/test outcomes stay unrun. Source and quality
evidence are read-only; the existing image is reused. See [study instructions](study.md).

## Test the signal with assumed execution costs

After the cost update, use the same frozen quality identifier:

```sh
bash scripts/mac cost quality-20261117T125619Z-mAfC1j
```

This opens the offline paper execution report for up to four development recordings
and six profiles. Fees, spread/slippage, causal partial-fill-sized closes, risk
rejections and remaining exposure stay explicit. The existing image is reused
without networking; originals remain read-only and no new collector is started.
See [running and reading the cost probe](cost-study.md). These independent cases
do not produce a portfolio return or prove profitability.

## Control and stop

In a second Terminal in the same source directory:

```sh
./scripts/mac status
./scripts/mac logs
./scripts/mac stop
```

The monitor is bound only to your Mac's loopback interface. It is read-only and
can remain available after collector completion. Stopping containers preserves
recordings. Starting another run archives the previous stopped collector's
console log before removing its stopped container; it never resumes that run.

The default data path is `~/GiethoornData`. An absolute `GIETHOORN_DATA_DIR`
override is supported; use the same value for setup, running and stopping. Do not
change Docker's daemon/context during a run. Two local copies sharing the same
Docker engine and user share the collector/monitor names.

This package does not install system services, change macOS power settings,
publish anything, enable a strategy or send exchange orders. Future live or
funded execution requires separate engineering and operational acceptance.
