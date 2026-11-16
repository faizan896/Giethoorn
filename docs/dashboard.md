# Read-only market monitor

The monitor shows actual normalized collector output, per-feed freshness, price
history, validated recordings, sampled memory and the reliability experiment.
There is no order placement, wallet, fabricated P&L or synthetic fallback data.
It runs alongside collection; it does not require completing the whole product.

## Live view

On the machine holding a reliability experiment:

```sh
python3 ops/dashboard.py --experiment data/reliability-24h-001 --port 3000
```

Open `http://127.0.0.1:3000` on that same machine, or use a supported Cloud browser
preview/forwarding link when offered. Localhost on another computer is a different
machine. This chat currently has no Cloud preview/viewer control, so a portable
saved view and screenshots are provided in the development handoff instead.
No external tunnel, deployment or environment publication was performed.

The monitor, Paper Lab and Batch Lab share a [Giethoorn-inspired visual system](design.md):
forest, moss, warm ivory, cottage brick and thatch. Both renderers embed
`web/theme.css` in the generated page, including portable exports. No external
fonts or image assets are required.

The server binds loopback by default. It serves the monitor, its state API,
a snapshot download, and explicitly configured offline research views:
`--paper-view PATH` adds `/paper`; `--batch-view PATH` adds `/batch`.
Each route serves one bounded regular HTML file. It does not expose filesystem
browsing or run replays on a request. Navigation appears only when configured;
portable monitor snapshots hide those server links. `Pause view` freezes the
display. A running collector continues independently; a stopped collector stays
stopped. `Save view` downloads a self-contained snapshot.

## Portable saved view

```sh
python3 ops/dashboard.py --experiment data/reliability-24h-001 \
  --snapshot /tmp/giethoorn-dashboard.html
```

Use a new output path. Download the HTML and open it in your own browser. CSS,
scripts, icons and captured data are embedded; no dependencies, network connection
or copied recordings are required. Charts and recording filters still work.
The page prominently says `Saved snapshot`, gives its capture time, and does not
poll or pretend to receive live prices. Saving again retains that same captured
view until a new snapshot is taken from the live monitor.

## What the numbers mean

- Market observations and verified bytes count closed, validated child recordings.
  The active child is excluded until its verification event. A recovered crash
  prefix is labeled separately from exact replay.
- Prices remain exact recorded decimal strings. Floating-point conversion is used
  only for chart pixel positions, never financial computation or collection.
- Chart data comes from bounded tails of the two most recent normalized output
  files. The available window is not the entire archive. Run/connection changes
  and gaps beyond channel thresholds break the plotted line.
- Feed ages combine recorded age with observer elapsed wall time. Clock anomalies
  are labeled uncertain. A new child cannot inherit old-child freshness, a stopped
  writer is disconnected, and a lost monitor API marks prices historical. These
  indicators are not trading authorization or proof of complete venue delivery.
- Memory is a sparse child RSS sample, not an absolute peak or proof of leak freedom.
- Progress reaching 100% alone does not pass the reliability gate. A coherent
  completed supervisor/experiment and successful full-window audit are required.

The monitor reads public configuration, control/telemetry and normalized stdout.
It never replays active market segments, changes locks to bypass a writer, starts
new exchange subscriptions, changes the collector binary or writes into evidence.
Complete corrupt monitoring records raise an error; only a writer's unfinished
last fragment is provisional. This view does not itself revalidate checksums;
the supervisor and final archive audit remain the verification authorities.

## Verification

Standard-library backend tests are included in:

```sh
python3 -m unittest discover -s ops -p 'test_*.py'
```

Optional browser acceptance uses the provided Playwright/Chromium installation:

```sh
python3 web/check_browser.py --url http://127.0.0.1:3000 \
  --output-dir /tmp/dashboard-browser-check
```

It checks actual data rendering, source/range controls, navigation, recording
filters, pause/resume, responsive layout, snapshot export/offline interactivity
and lost-connection behavior. The managed browser blocks direct `file://`
navigation; the exact downloaded HTML was therefore rendered with networking
disabled, without changing browser policy. See [status.md](status.md) for evidence.
