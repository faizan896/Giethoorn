# Giethoorn on your Intel Mac

This package runs the collector and research tools on your own Mac, without a
paid VPS. It includes the current source files; it does not rely on a GitHub push.
Docker Desktop supplies the Linux environment required by the fault-test runner.
The Mac setup itself still needs acceptance on your machine. A Linux container
test is not evidence that your Mac has completed a 24-hour collection window.

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
That branch must first be uploaded with the user's approval; its existence must
not be inferred from this guide. Once available, select the branch in GitHub,
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
