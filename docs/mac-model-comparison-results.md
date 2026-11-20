# First supplied Mac fill-assumption comparison

Status: the supplied Terminal readout completed on 21 November 2026 PKT. All
24 cases are reported verified, with unchanged input/code and no unavailable/
not-run cases or error. All 14 conditionally closed proxy cases lose money;
the other ten retain hypothetical short exposure and unavailable closed P&L.
This small fixed-scenario comparison provides no positive economic evidence.

## Scope and provenance

The user supplied output for
`~/GiethoornData/compare-20261120T192726Z-H1ZPNb/report`, reading original cost
snapshot `cost-20261120T115202Z-fKjWVP` after the issued pinned `3ff61a0` update.
The artifact's UTC identifier corresponds to 21 November in Asia/Karachi.
Selected children remain 2–5, each under the same six profiles: baseline,
lower-fee, zero-fee, delay-stress, liquidity-stress and slippage-stress.

This workspace read the supplied text, not original Mac files or full native
receipts. Cohort membership, lifecycle counts, Decimal fee algebra and consistency
of printed prices/net/fees were recomputed here. This is not an independent
cloud native replay or revalidation of source, order side or reference timing.
Actual execution is explicitly unknown, and alternative strategy evaluation is
explicitly false in the readout.

## What changed under the proxy

| Lifecycle | Original model | Known-book proxy |
| --- | ---: | ---: |
| Entry rejected | 10 | 0 |
| Unresolved original close | 1 | — |
| Open hypothetical exposure | — | 10 |
| Closed under declared assumptions | 13 | 14 |

All 38 frozen requests have eligible references and assumed full fills of
0.001 BTC: 24 entries and 14 closes. Reported reference ages range from
10.473161 to 247.802433 ms, within the declared 2,000-ms source threshold.
These are quote ages at assumed arrival, not measured order-network latency or
proof that displayed size remained executable.

Ten open cases are the five non-delay profiles on each of recordings 2 and 5.
Their original model rejected the entry, so those fixed scenarios contain only
an entry request. The proxy assumes that entry fills, but the comparison does
not invent a close that was absent from the frozen plan. Each retains a reported
**−0.001 BTC hypothetical position**, no pending order and unavailable closed P&L.
These are independent profile starts, not ten simultaneous real positions and
not a combined portfolio exposure. No market close or zero return is inferred.

Recording 2's delay-stress case already contains an entry and close. Its original
close was unresolved; the proxy assumes both fills and reports net
`-0.07046899965` USDC, with `0.06455749965` fees. It cannot be called an improved
return relative to the original unavailable closed P&L.

## Closed results remain negative

For the 13 cases closed in both models, eight net values are unchanged and five
are worse under the proxy. None improves. The five worse cases are recording 4's
baseline, lower-fee, zero-fee, liquidity-stress and slippage-stress profiles.

| Case | Original closed net, USDC | Proxy conditional net, USDC |
| --- | ---: | ---: |
| 3 / baseline | -0.07074739965 | -0.07074739965 |
| 3 / zero fee | -0.0059579 | -0.0059579 |
| 4 / baseline | -0.0777168 | -0.07871620005 |
| 4 / zero fee | -0.0129528 | -0.0139527 |
| 5 / delay stress | -0.07862140005 | -0.07862140005 |

All 14 proxy closed cases remain negative even after adding back their declared
fees. For example, recording 4 baseline's implied pre-fee result is `-0.0139527`
USDC, matching its zero-fee control. This retains spread and assumed slippage;
it does not separate them from price movement or measure actual execution costs.
Changing the fill rule or lowering fees did not create positive evidence in
these selected cases. Four recordings do not establish general strategy quality.

`0E-7` in several fee totals is an exact Decimal representation of zero. All
printed order fees sum to their case totals and match assumed price × quantity ×
the declared profile fee rate. Closed net plus fees has the same absolute value
as the two printed fill-price difference × quantity. Order side was not printed
in this compact readout, so that identity is a consistency check rather than
an independent directional/source audit. No case/profile P&L is pooled.

## Next engineering step

The fixed-request comparison is complete; the ten open cases are consistent
with its declared contract. Next is a separately versioned
[causal proxy policy experiment](causal-proxy-policy-plan.md), where exit quantity
comes from that model's own simulated position at the declared decision prefix.
Its purpose is complete, causal policy mechanics, not improving these already
observed results by tuning deadlines, fees or the signal. That implementation and
its [subsequent supplied Mac result](mac-causal-policy-results.md) are now
accepted: 24 conditional closes, all negative. This fixed-plan comparison remains
unchanged; no new capture or order run is required to accept its readout.

The existing R001 evidence remains exploratory and non-profitable under these
declared assumptions. The operational day gate, actual execution calibration
and later frozen-data economic confirmation remain open.

Receipt: `data/mac-model-compare-review-20261120T194754Z-xsl_rkcv/`.
