# Decision: offline fill-assumption comparison version 1

Status: implemented. The new namespaces are `comparison_report_version:
1`, `comparison_policy_version: 1`, `proxy_model_version: 1` and
`comparison_link_version: 1`. The proxy identifier is
`assumed_known_book_at_arrival_v1`. No native schema, binary, existing paper model,
cost policy, producer asset or historical result changes.

## Frozen requests, separate hypothetical ledger

Read a preserved cost snapshot, recheck its original source/policy/producer and
exact original native ledger, and use the same compiled requests and six assumed
cost profiles. These include the original conditional close quantities. Do not
recompile a strategy, resize a close, add a replacement request or force inventory
flat under the alternative path. A fixed close can therefore leave or reverse
hypothetical exposure when earlier fills differ. Report that exposure explicitly;
this comparison is not an alternative causal-policy backtest or a new R001 result.

The alternative compiler is pure Python with integer time and exact Decimal
arithmetic. It persists version-1 **manual-simulation** paper inputs before passing
them to the unchanged native ledger. Source provenance, original references and
scheduled actions live in the new comparison receipts; a manual assumed ledger
is never presented as observed exchange executions. Native prefix replay decides
request risk, accounting and loss halts. A separate final replay must reproduce
every retained checkpoint prefix, and independent checks bind source, prices,
size consumption, costs and balances. Keep source origin separate from ledger kind.

## Scheduled arrivals and source ordering

Assumed arrival is original request time plus the unchanged profile latency.
Preserve original receive order. Before each original source event, settle queued
arrivals strictly earlier than its time using only already processed source.
Then process that original event, settle previously queued arrivals equal to its
time, and issue requests anchored there. Zero-delay requests settle immediately
after their own request, in declared request order. Later source records sharing
the same timestamp cannot alter a completed decision. Orders tied at one arrival
use original request order and share capacity. Scheduled timestamps are assumed
actions, not interpolated original receive/ACK timestamps.

At arrival, advance the manual ledger with a timer and use only the last native
usable selected BBO known in that prefix, on the same live connection with ACK
and fresh source state. Quote age must be strictly below the original recorded
BBO threshold. Do not refresh that age at arrival. Empty/stale/disconnected states
invalidate the reference; a later quote cannot repair an earlier decision.
Do not drain arrivals beyond actual source EOF, including at a generated replay
end. Pending requests and open positions remain unresolved.

This is a conditional standing-book proxy, not evidence that displayed liquidity
survived until a real order arrived. Actual venue execution remains unknown for
every row. A missing reference creates an explicitly assumed adapter rejection;
it does not diagnose an actual venue rejection. There is no wait for another
quote in this proxy. The existing quote-wait deadline remains solely the old
model's rule and is not tuned after viewing outcomes.

## Liquidity, prices and risk

Use the existing profile's fraction of opposite displayed top size, adverse fill
slippage and fee rate. Share consumed capacity across concurrent orders. Equal
exchange timestamps cannot replenish it; equal-time price changes make that
identity ambiguous/unavailable. Invalid reference transitions cannot replenish
capacity. A valid new exchange-time/connection identity creates a new declared
size budget. Retain limit protection, partial fills and immediate assumed IOC
remainder cancellations. The original limit and the adverse assumed fill price
are distinct; neither is a measured venue execution price.

The native ledger remains authoritative for request risk, reservations, exact
FIFO accounting, fees and loss halts. Already pending requests can resolve after
a halt as in the original model; new requests remain subject to the native gate.
No fill means unavailable closed-case return, not a zero-profit trade. Report
conditional closed P&L only after actual hypothetical fills, flat inventory and
no working orders; never sum independent profiles into a portfolio return.

## Admission and acceptance

Bind the original cost inventory, source quality, policy/producer assets and
installed native executable. Use read-only input, private create-new output,
finite native/prefix/order/source/output/time bounds, before/after fingerprints
and no networking. Unavailable and not-run cases remain in the original cohort
without replacements. Retain original exact ledger validation, alternative final
inputs/outputs, source links, prefix hash receipts and independent cost checks.
Successful intermediate full update streams may be discarded only after their
prefix hashes and native reports are retained; the final stream must reproduce
all those prefixes. Failed child diagnostics remain intact.

Hand-calculated cases must cover a quiet window, new/tied quotes, zero latency,
stale/empty/reconnect transitions, arrival at EOF, arrival after EOF, shared/equal-
time capacity, partial/no fills, limit/risk/loss rejection and open exposure.
Mutating a later price must not change an earlier proxy decision. Test exact
native accounting, original-model byte preservation, source/producer mutation,
budget refusal and portable desktop/mobile views before delivery. Software test
sources stay synthetic; actual subsequent Mac comparisons need their own receipt.
