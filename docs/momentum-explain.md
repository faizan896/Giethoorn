# Explain the retained R002 result

Use `bash scripts/mac momentum-explain MOMENTUM-ID` on a completed saved R002
snapshot. This diagnoses original close windows, partial fills and the exact
price/cost identity. It preserves the frozen R002 rules and historical results.
No new recording, quality snapshot, Docker build or paid server is needed.

For the accepted Mac result:

```bash
cd "$HOME/Downloads/Giethoorn-mac-local-setup" &&
bash scripts/mac momentum-explain momentum-20261121T221741Z-XgpqRI
```

Open Docker Desktop first and keep the Terminal open until the command finishes.
Progress prints once per recording. The launcher uses the existing image with
networking disabled, ordinary user permissions and a read-only mount of just the
completed R002 report directory. It creates a separate
`~/GiethoornData/momentum-explain-TIMESTAMP-ID/report/` and opens
`momentum-explain.html`. Original recordings, `last-run` and collector containers
are untouched. A completed saved report can be inspected independently of an
unrelated collector. Input/code mutation causes verification failure.

## What the report establishes

The installed executable must match the original R002 producer. The tool never
executes the bundle's copied executable or invokes a strategy producer. It checks
the full bundle inventory, copied frozen quality inputs, original specifications,
producer hashes, cohort and all six case slots per development recording.
It independently replays each selected copied recording and every distinct saved
manual ledger, requiring byte equality and original source/Decimal/prefix audits.
It checks original selection, labels, case results, totals and classification.

The original collection-wide quality audit remains a bound historical receipt;
this tool replays the selected copied recordings and manual ledgers, not the
entire original collection archive. A verified diagnostic does not complete the
24-hour reliability window or any production gate.

Missing close decisions distinguish a source ending before the fixed 30–31-second
window, an incompletely observed window and an observed window without an eligible
native BBO. Real boundary events and source-end reason stay visible. These facts
cannot establish a physical network cause or a hypothetical executable close.

Partial and zero fills expose the original request, known arrival reference,
assumed capacity, marketability, native lifecycle and rejection. Capacity is a
fraction of saved top size under the original manual model. Shared capacity may
also reflect earlier fills, earlier conservative caps or ambiguous repeated
quotes; it is not a measurement of actual exchange liquidity.

For each fully closed case, the exact identity is:

```text
decision-midpoint cashflow
  - signed arrival price change
  - spread cost
  - assumed slippage
  - native assumed fees
  = native conditional closed net
```

The midpoint benchmark uses the original assumed filled quantities and original
decision times. It is not a tradable midpoint strategy, latency calibration or
expected return. A negative arrival-change cost is favourable. Costs are charged
once. Open/pending cases show known fill costs and ending inventory, with closed
P&L/decomposition unavailable. No fill and no signal remain separate outcomes.
Six profiles are never pooled into a financial return.

## Evidence and failure behavior

`momentum-explain-report.json` is the portable report's complete data;
`verification/` contains native source/ledger comparison receipts and prefix
audits. `input-before.json`, `input-after.json` and
`diagnostic-inventory.json` bind the original bundle and new evidence.
Successful temporary native outputs are removed after exact comparison; their
hashes and byte counts remain. Failed checks retain new diagnostic receipts and
suppress admitted financial analysis, without altering the original result.
An initial admission refusal prints its reason before creating the report.

The [version-1 contract](momentum-explain-plan.md) fixes finite input, output,
disk, native-call and total-time bounds. The original six profiles, signal and
entry/close/retry parameters are unchanged. To inspect the output later, open the
saved HTML in Finder. The JSON export retains exact decimal strings and large
timestamps. Share the printed diagnostic summary for the next review; the Mac's
actual failure causes remain unverified until its original bundle passes.

Developer checks:

```bash
python3 -m unittest discover -s ops -p 'test_*.py'
python3 ops/check_momentum_explain_browser.py \
  --fixture-json /path/to/synthetic-native-fixture-report.json \
  --no-signal-json /path/to/verified-no-signal-diagnostic.json \
  --output-dir /path/to/new-browser-check
```

The optional browser check requires Playwright and Chromium. In managed cloud
Chrome, self-contained documents are loaded in memory because file navigation is
blocked. The same portable HTML is exported for the Mac. Synthetic component
fixtures establish software mechanics only; full-bundle admission is exercised
separately on retained source evidence.
