# Quote-opportunity and expiry review

Status: specification only; the diagnostic exporter is not implemented.
This is the next engineering step after the [first Mac cost-probe readout](cost-probe-results.md).
It explains recorded paper execution opportunities without running a new trading
policy, changing completed outcomes or estimating profitability.

## Frozen scope

Use the existing stopped `cost-20261120T115202Z-fKjWVP/report` artifact, policy
`r001-ioc-probe-001`, four selected children and all six profiles. Include all
24 cases; ten entry expiries and one close expiry require explicit explanation,
with closed cases retained for context. Never select only a successful nearby
quote or replace an expired attempt. The original source and derived execution
files remain read-only and the historical open short stays unresolved.

Admission must bind the report's bundle inventory, retained scenario and source
fingerprints, code/policy version and before/after inventory. Reuse the original
native source/trace identity checks and Decimal/ledger verification as needed;
finding a JSON file alone is not a fresh independent integrity attestation.
Source changes, missing/duplicate records or unsupported model versions yield an
unavailable diagnostic with retained reason rather than an invented explanation.

## One timeline per order

Join the stored request, source links, native market and execution trace by
original child/market sequence. For every entry/compiled close, retain:

- Request sequence, connection, monotonic time and the source state known then.
- Declared latency, arrival and exclusive expiry, checked against native trace.
- Observed events and native selected-BBO market opportunities surrounding those
  boundaries, with original event/quote references, freshness, acknowledgement,
  quote age, exchange timestamp and source-record type.
- First new usable native opportunity after the request and at/after arrival,
  if it exists, and the actual observed event that resolved or expired the order.
- Quantity filled/cancelled or rejection reason, known position and any pending
  state, without changing ledger values or turning an incomplete case into flat.

Native `market_observed` eligibility differs from the prediction study's unique
exchange-time/continuous-label rule. Preserve those definitions separately.
Equal timestamps do not replenish native liquidity; quote presence does not
guarantee a fill. A nonmarketable limit, partial fill or risk rejection is not
reclassified as a missing quote merely because it produces no closed position.

At exact expiry the native model rejects before attempting the fresh quote at
that event. A source end before observed resolution keeps the order pending.
No clock interpolation, forward filling, synthetic acknowledgement or hypothetical
post-source liquidation is allowed. Child clocks never cross recordings.

## Explanations and limits

Report separately: no recorded selected-feed opportunity in the eligible window,
unusable/stale/duplicate source states, observed expiry boundary, source end before
resolution, and non-expiry order outcomes. Where a causal component cannot be
established, say unknown. Recorded observation gaps do not by themselves identify
an exchange problem, transport delay, Mac suspension or Internet outage.
Wall-receive minus exchange time is not measured order latency.

Show both arrival windows in paired profiles. A 100-ms arrival plus 250-ms wait
expires at request +350 ms; 250-ms arrival plus the same wait expires at +500 ms.
A different fill count can follow from shifted windows. These declared assumptions
must not be relabelled as measured latency or proof that extra delay helps.

The output should be a compact per-order timeline with source references and a
bounded portable report. Keep the original 16-MiB source and 10,000-event native
bounds; retain an explicit refusal for oversized cases. Use finite output, time
and disk budgets, no networking and an output directory outside original evidence.
Do not alter the original bundle or regenerate its case results in place.

Acceptance needs exact arrival/expiry boundaries, post-window opportunities,
same-time/connection changes, stale quotes, partial/nonmarketable and risk cases,
missing-source/pending state, shifted profile windows, corrupt/mutated inputs,
repeatability and original preservation. The separate cloud integration sample
can validate software first; it must stay distinct from the user's Mac artifact.

## Research after diagnosis

Keep this cost probe as a completed exploratory result, with its losses and
unresolved case intact. Diagnose cadence and source availability before claiming
the current execution assumptions are representative. A later bounded fresh
public-data capture can check recording behavior; it does not itself calibrate
private execution or pass a full-day operational gate.

Any wider development experiment or different signal/horizon/entry policy must
have its own version, fixed scope and cost/missing-exposure rules before results.
The original archive's partitions are already explored. Confirmatory economic
evaluation needs later separately frozen data after those choices, with no
performance claim from these four mechanics-test recordings.
