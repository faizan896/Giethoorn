# Read a saved IOC quote window

The diagnostic explains an existing cost snapshot using original source events,
fresh native normalization, exact saved-ledger replay and the original causal
compiler receipts. It retains every historical outcome, including losses,
rejected entries, pending orders and open positions. It evaluates no new policy
and generates no new order intents, fills or portfolio profit result.

## Run on the Mac

Install the supplied diagnostic source update, open Docker Desktop and run:

```sh
bash scripts/mac explain cost-20261120T115202Z-fKjWVP
```

Use the saved cost snapshot's identifier, rather than a quality or collection ID.
The existing image is reused. The original cost report directory and helper code
are mounted read-only, with Docker networking disabled. No new capture or image
build is needed. This command reads the cost artifact's private source copies;
it does not depend on the current `last-run` or control a collector.

A new `~/GiethoornData/explain-TIMESTAMP-SUFFIX/report/expiry.html` opens in the
browser. It works offline without a server. Terminal output includes case/order
counts and each expired order's assumed arrival, exclusive expiry, first usable
native quote and observed resolution, as exact millisecond strings relative to
its request. Paste that output for review; no separate extraction command is
needed. The JSON report retains nanosecond strings and original source references.

Keep the original artifact unchanged. An unexpected file, changed checksum,
unsupported helper/template version or modified cost policy causes refusal. A
failed/unadmitted case remains visible as unavailable or not-run. An outer timeout
or abrupt Docker shutdown can leave partial audit evidence without a final view.
Allow about 3 GiB free disk space for the output limit and reserve; ordinary small
snapshots use much less. The internal admission deadline is 600 seconds and the
Mac wrapper has a 660-second outer timeout.

## Interpret an order

Select a recording/diagnosis and inspect an entry or close. Arrival and expiry are
declared model boundaries, not recorded clock events. The table shows actual
source sequences and offsets around those boundaries, including the observed
resolution and first native selected-BBO opportunity after arrival. No quote is
inserted into an empty interval.

- **Expired, no opportunity:** the first observed event able to resolve the order
  reached expiry before any usable native opportunity in its eligible window.
- **Expired at quote boundary:** a usable quote arrived at exact expiry. The
  model expires the order before trying that quote; the upper boundary is strict.
- **Filled / partial fill cancelled / no fill cancelled:** the first eligible
  native opportunity was tried. Limit protection or assumed shared capacity can
  leave a remainder; a quote does not guarantee a fill.
- **Request rejected:** the original ledger rejected the request. Inspect its
  risk/state reason; it is not reclassified as a quote expiry.
- **Pending at source end:** the saved timeline ended before an observed
  opportunity or expiry. No hypothetical acknowledgement, expiry or close is added.

Counts of BBO messages, repeated exchange times and unusable states give context;
they do not replace native eligibility. Prediction-label eligibility is a different
rule. Repeated timestamps do not replenish native liquidity. Quotes outside the
window are shown as observations, never as fills the original order received.
Window counts can include events after an order already resolved; they are not
repeated IOC attempts. Only the original first eligible opportunity was tried.

Baseline window is request +100 through +350 ms, with +350 excluded. Delay stress
is +250 through +500 ms, with +500 excluded. A later simulated arrival shifts
both boundaries and can encounter another quote; it is not measured delivery
latency or evidence that waiting longer improves returns. The diagnostic reports
component cause as unknown: a recorded gap alone cannot identify exchange cadence,
network delay, Internet outage or suspension of the recording machine.

## Integrity and bounds

The tool binds every original bundle member by size/SHA-256 and checks the
preserved version-1 policy grid, original verifier/template versions, copied frozen
quality evidence and installed binary. Its own before/after inventory includes
all source files, sizes, hashes and modification times. Changed evidence or code
invalidates all admitted diagnostic rows while retaining audit artifacts.

Fresh native mark-only replay and normalization run once per child. Each saved
control/final execution is checked against those native source outputs. Exact
native ledger replay must reproduce its updates/report, and independent Decimal
cost verification must agree. The feature, entry scenario, close-decision prefix,
compiled scenario and historical metrics are reconstructed only to compare with
the originals. No new scenario is executed and no original result is rewritten.

Admission allows at most the fixed cost suite's four children and 24 cases, 2 GiB
of regular input/output files, 8,192 input files and a 1-GiB free-space reserve.
Source/case audits each require a conservative 128-MiB output reservation. Native
calls are limited to 30 seconds, record streams to 10,000 events and native source
copies to 16 MiB. Output/portable report limits and create-new files remain fixed.
The tool executes the installed matching binary, not a program from the snapshot.

See [decision 0012](decisions/0012-expiry-diagnostics.md) and the
[original diagnostic protocol](expiry-review-plan.md). Software acceptance uses a
separate small saved cloud sample plus synthetic boundary/risk/source-end cases.
The actual Mac diagnostic remains pending until that saved artifact is inspected
on the Mac. It does not complete the operational day gate, calibrate execution or
confirm an economic edge.
