# Supplied Mac evaluation exceptions explained

Status: the supplied read-only diagnostic was accepted on 21 November 2026 PKT.
It reports 13 case-receipt hashes verified for
`evaluation-20261120T220630Z-oyufiA`: the previously reported 12 unresolved
cases and one no-fill case. Their identities, filled quantities, remaining
positions and classifications reconcile with the broader evaluation.

## Three groups explain all 13 cases

| Source and profiles | Cases | Reported outcome | Result |
| --- | ---: | --- | --- |
| Child 8, all six profiles | 6 | Close `not_marketable` | Entry sells 0.001 BTC; requested buy close fills zero; -0.001 BTC remains. |
| Child 56, all six profiles | 6 | Close `partial_fill_cancelled` | Entry sells 0.001 BTC; the close fills partly and the IOC remainder is cancelled; short exposure remains. |
| Child 71, slippage stress | 1 | Entry `not_marketable`, then `flat_no_close` | No entry fill, no close request, no position and zero fees. |

In the unchanged proxy, `not_marketable` means the **assumed adverse fill price**
fails the submitted protective limit: buys require price at or below the limit;
sells require price at or above it. This is not an actual venue rejection. The
diagnostic prints no native rejection/reason for any of its 25 orders.

The proxy's partial quantity is the smaller of requested quantity and remaining
assumed top-book capacity. Capacity uses the fixed profile fraction of displayed
size, with shared consumption rules. This identifies a **model liquidity-budget
limit**, not proof that an actual venue lacked enough displayed/executable size.
The IOC remainder is cancelled and the inventory is retained rather than assigned
an invented closing fill.

## Exact remaining inventory on child 56

Each case requested a 0.001-BTC buy close against its known -0.001-BTC position.
All quantities below are reported exact strings in BTC.

| Profile | Close filled | Ending position |
| --- | ---: | ---: |
| Baseline | 0.0002975 | -0.0007025 |
| Lower fee | 0.0002975 | -0.0007025 |
| Zero fee | 0.0002975 | -0.0007025 |
| Delay stress | 0.0002425 | -0.0007575 |
| Liquidity stress | 0.000119 | -0.000881 |
| Slippage stress | 0.0002975 | -0.0007025 |

Signed entry/exit fill sums reproduce every ending position exactly. The 10%
liquidity profile's fill is exactly 0.4 times the baseline 25% profile's fill,
consistent with their declared capacity fractions. Baseline/lower-fee paths have
the same quantities and their fees differ by exactly a factor of five; zero-fee
controls have exact zero fees. Prices and actual available-size receipts were
not printed, so their independent source verification is not claimed here.

All 12 closes were compiled for the correct known position with opposite side
and no over-close. Every decision reports fresh market state, zero working
orders and no halt. All 13 cases end with no pending orders and unavailable
closed P&L. Reported reference ages range from 5.186421 to 163.340615 ms; these
are quote ages at assumed arrival, not measured order-network latency.

## Finding and next step

These reported outcomes match the declared compiler and independent verifier.
No accounting/quantity bug is demonstrated by this evidence. The existing
single-attempt exit policy can legitimately finish with residual inventory;
that is a limitation for later live use. A completed software check does not
resolve that inventory or make a complete profile net return available.

Original cases, protective limits, cost assumptions and all negative results
remain unchanged. No new capture, policy replay or additional Mac command is
needed to accept this diagnostic. R001 still has no demonstrated economic edge.
The next separately declared safety experiment is
[one bounded additional close](bounded-exit-plan.md), sized only from its own
known residual position after the first close settles. Its purpose is exposure
handling, not making the current strategy profitable. Its
[implementation and software acceptance](bounded-exit.md) are now complete;
the actual Mac evaluation is pending. It will not guarantee flat inventory under
missing data, native risk rejection or insufficient assumed capacity.

## Provenance and software check

This workspace read the supplied diagnostic text. Case-hash verification was
reported by the user's Mac reader; original private Mac receipts, raw quote
prices/limits/capacity, native ledgers and source were not independently replayed
here. Count/quantity/position identities, baseline continuity and fee/fraction
ratios were recomputed using exact Decimal arithmetic. All fills remain manual
simulation and actual venue execution stays unknown.

Three existing native contract tests pass for no marketable entry, partial exit
and full/partial short-entry close sizing. A separate labelled synthetic native
example reproduces an unfilled buy close: limit `100.030002`, assumed fill price
`110.021001`, remaining position `-0.001` BTC, no pending order and unavailable
closed P&L. This checks the software rule, not the original Mac market data.
No runtime code or native schema changed and no full test-suite rerun was needed.

Receipt: `data/mac-exception-review-20261121T154057Z-ghgu00f7/`.
