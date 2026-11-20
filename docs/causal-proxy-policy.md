# Test exits from the proxy's own position

The [first supplied Mac result](mac-causal-policy-results.md) is accepted:
24 verified conditional closes, no remaining exposure and all net results
negative, including zero-fee controls. No rerun is needed to accept that result.

Open Docker Desktop, install the causal policy source update, and run:

```sh
bash scripts/mac policy cost-20261120T115202Z-fKjWVP
```

Use the original saved **cost snapshot** ID. The command verifies that bundle
offline and creates a new
`~/GiethoornData/policy-TIMESTAMP-SUFFIX/report/policy.html`. The portable view
opens automatically on macOS. Terminal also prints every selected case, entry/
close quantities, assumed prices/fees, ending exposure and conditional closed
P&L. Paste that output to review the actual Mac result.

The existing Docker image is reused. No new recording, image rebuild, credentials
or host Python/Rust is needed. Original cost/comparison reports and recordings
remain separate. The command does not change collector/monitor or `last-run`.

## Why this is a new policy experiment

The [accepted Mac fixed-plan comparison](mac-model-comparison-results.md) has
ten open hypothetical shorts. Their frozen original plans contain an entry but
no close, because the original model rejected those entries. That comparison
correctly preserves its original requests under a different fill assumption.

This new policy instead derives the close from its **own** native position at
the original exit decision. It keeps the same selected development recordings,
signal, one-second horizon, 0.001-BTC target, limits/risk and six cost profiles.
There is one cycle per child/profile, each starting flat independently. These
already explored recordings cannot serve as a pristine holdout, and six profiles
do not represent six independent markets or a combined portfolio return.

## Read the decision and ending state separately

An entry-only control runs through the unchanged known-book proxy and native
manual ledger. The original source rule selects the first observed usable event
at/after the fixed horizon, with a same-connection BBO no older than 250 ms.
It can use a fresh quote already known at that event. Time and source events
are not interpolated.

The close compiler reads only native state through that exact decision prefix,
including queued arrivals resolved before the request at the same timestamp.
Later source sequences and later fills cannot revise that state. The report
keeps decision-time position separate from final position.

| Close decision | Result |
| --- | --- |
| `close_compiled` | One opposite-side request for the settled native position, using only the decision's known quote. A partial entry gets its own partial quantity. |
| `flat_no_close` | Entry has settled without a position; no close is invented. |
| `unresolved_entry` | Entry is still working at the decision; no close is invented, even if it fills later. |
| `missing_decision` | No eligible observed decision before source end; the entry-only control is retained. |

The compiled plan must reproduce the complete control input/link/update prefix
before the new close request. The receipt binds its position, working orders,
risk, record count and hash; independent checks verify quantity, side, anchor
and limit. Entry and every other scenario field stay fixed.

A requested close can remain pending, fill partly or be rejected by native risk,
including a loss halt. Its exposure stays visible. No retry, halt bypass or
forced closing price makes a case flat. No-fill and unresolved cases have
unavailable closed P&L rather than a fabricated zero return. Conditional closed
P&L requires hypothetical fills, flat inventory and no working order.

## Retained evidence and bounds

Each case retains the original native revalidation, entry-only control,
compiled scenario, close-compilation receipt, causal-prefix audit, source links,
complete manual ledgers and independently checked costs. A final replay is
retained when a close is added; otherwise the control is reused. The report
binds these artifacts and the original input, native executable and producer
assets. Before/after changes invalidate all new policy metrics. Failed or not-run
cases stay in the selected cohort without replacements.

Execution uses read-only input and no network. Bounds include 24 cases/two
requests per case, the existing 16-MiB source/10,000-paper-record limits, 2 GiB
output, 1 GiB free reserve, 900-second suite, 30-second native calls and a
960-second outer timeout. Budget refusal can leave retained diagnostics without
a completed HTML report.

All fills remain **manual simulation** under the unchanged known-book assumption.
Actual venue execution is unknown. This verifies causal policy mechanics and
accounting; it does not calibrate executable liquidity or establish profitability.
The full-day gate, actual execution calibration and later frozen-data economic
confirmation remain open.

## Software acceptance

All 315 Python tests pass, including 19 new native policy tests. Two ordinary-user
Docker trials on a separate saved cloud sample reproduce all 24 policy cases
and 1,228 audit files exactly. That sample has 24 conditionally closed cases,
all negative; its original 19 closed/five unresolved outcomes remain unchanged.
These are cloud software results, not the subsequent Mac policy result.

Offline Chromium verifies exact decision/ending values, JSON export, pending/
partial/missing states, changed-evidence refusal and desktop/390/320-pixel views
without browser errors or network requests. Acceptance receipt:
`data/causal-policy-acceptance-vtgegra5/native-release.json`.
See the [predeclared protocol](causal-proxy-policy-plan.md) and
[version decision 0016](decisions/0016-causal-proxy-policy.md).
