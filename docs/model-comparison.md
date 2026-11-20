# Compare offline fill assumptions

The [first supplied Mac comparison](mac-model-comparison-results.md) is accepted:
24 verified cases, 14 negative conditionally closed results and ten open
hypothetical positions explained by the unchanged fixed request plans.

After the comparison source update, open Docker Desktop and run:

```sh
bash scripts/mac compare cost-20261120T115202Z-fKjWVP
```

Use the saved **cost snapshot** ID. This comparison needs its frozen requests,
source and historical ledgers. A fresh `feed-check` contains no orders and is
not a cost experiment. The existing image/native executable is reused; no new
capture, image rebuild, host Python/Rust or credentials are required.

The command reads the original bundle without networking and creates
`~/GiethoornData/compare-TIMESTAMP-SUFFIX/report/comparison.html`. It opens that
portable view and prints per-case decisions, exact price/fee strings, conditional
ledger results, pending orders and ending exposure. Paste the Terminal output
for review. Every selected case remains present, including unavailable/not-run
cases. Existing collector/monitor state and `last-run` remain untouched.

## What is compared

The original next-new-quote model must encounter a later usable selected-feed
quote inside its declared arrival/wait window. Its saved native source, scenario,
exact ledger, causal-policy receipts and cost arithmetic are checked again.
Historical outcomes are preserved.

The separate `assumed_known_book_at_arrival_v1` proxy asks which last known BBO
could be referenced at the assumed arrival. It evaluates freshness at that time,
not at a later message, retaining the quote's source sequence, connection, age,
prices and size. Public silence can coexist with a previous displayed quote,
but does not establish that an actual order could obtain that liquidity.
Actual execution remains **unknown** for both models.

Both sides use the same fixed compiled requests, quantities and existing six
assumed fee/slippage/size/delay profiles. The original policy chose its close
quantity from the original entry path. That close is not recomputed or resized
for the proxy. A changed entry fill can therefore leave or reverse hypothetical
exposure. The view exposes this position; this is a fixed-scenario comparison,
not an alternative adaptive-policy backtest or a new R001 performance result.

The order limit and assumed adverse fill price are separate. The limit protects
the submitted request; the existing adverse-slippage assumption shifts a recorded
touch to produce a conditional fill price. This does not measure the venue's
actual slippage, price protection or account-specific fee tier.

## Causality, accounting and provenance

Original source records retain receive order. Queued arrivals strictly before
the next source time use only the already processed prefix. At an equal time,
the first corresponding source record is processed before queued arrivals, then
requests anchored there; zero-delay requests settle immediately after their own
request. Later source records at that same timestamp cannot revise the decision.
Assumed action times have their own labelled comparison links rather than
invented original receive/ACK timestamps.

The compiler creates a native version-1 **manual-simulation** ledger, persisting
every batch before native prefix replay. The unchanged Rust ledger determines
request rejection, reservations, exact FIFO accounting, fees and loss halts.
Earlier pending requests may resolve after a halt while new risk stays blocked.
Final complete replay must reproduce every checkpoint's input/update prefix
hash. A separate Decimal/source checker verifies reference causality, prices,
shared size, costs, positions and balance identities. Source origin remains
separate from the hypothetical ledger kind; none of its fills are venue evidence.

Equal exchange times cannot replenish consumed size. Equal-time price changes
make that identity ambiguous; empty/stale/disconnected transitions invalidate the
reference. New capacity needs a valid new identity. Limit protection, partial
fills, IOC remainder cancellations, pending orders and open exposure remain
explicit. Arrivals beyond actual source EOF are not drained at generated replay
end. No closing price is invented.

Conditional closed P&L appears only after hypothetical fills, flat inventory and
no working orders. No fills means unavailable closed P&L, not a zero-profit trade.
Independent profile starts are never summed into a portfolio return.

## Evidence and bounds

Each case retains original revalidation, alternative scenario/policy, complete
manual ledger inputs/updates, comparison links, decision receipts and independent
cost audit. Checkpoint reports and prefix hashes are retained. Successful temporary
full prefix update streams are removed after their hashes are saved; the final
complete stream must reproduce them. Failed child diagnostics remain available.

Admission binds the full original cost inventory, frozen quality/source,
policy/producer assets and installed executable. Full input/code/binary checks
run before/after; a change invalidates all comparisons. The input is read-only,
output create-new/private, and no input executable is run. Corruption, missing
source, budget failure or an unsupported producer cannot produce success metrics
or a replacement cohort.

Limits are 2 GiB output, 1 GiB free-space reserve, 16 MiB report reservation,
900 seconds total admission, 30 seconds per native call and a 960-second outer
wrapper timeout. Source/native bounds remain 16 MiB source, 10,000 paper records,
64 fixed requests and at most 193 native checkpoints per case. Cases reserve
256 MiB; checkpoints reserve 64 MiB. Limit refusal can leave a partial audit
without final HTML. Sparse/unavailable cases remain explicit in completed reports.

See [decision 0015](decisions/0015-execution-model-comparison.md) and
[the initial assumption review](execution-model-review.md). This tool provides
source/ledger/arithmetic consistency, alongside the outstanding day gate,
actual execution calibration and later frozen-data economic confirmation.
