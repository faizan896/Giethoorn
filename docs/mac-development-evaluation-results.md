# First supplied Mac broader development evaluation

Status: the supplied Terminal readout completed on 21 November 2026 PKT.
All 474 cases across 79 development recordings are reported verified. There
are 461 conditionally closed cases, 12 unresolved cases and one no-fill case.
All six complete profile net totals remain unavailable. The baseline's 77
closed cases are all negative; its two other cases retain hypothetical exposure.
This evaluation supplies no positive economic evidence for the current policy.

## Scope and verification

The user supplied output for
`~/GiethoornData/evaluation-20261120T220630Z-oyufiA/report`, following the issued
pinned `c9cd960` update. Source is the original stopped archive selected by
`quality-20261117T125619Z-mAfC1j`. Selected children are exactly 2–80 in frozen
development order, with six unchanged profiles per child. Source, quality and
code are reported unchanged, with no error, unavailable/not-run case or missing
signal. Each of the 79 progress rows reports six verified cases.

The supplied file also contains older comparison/policy Terminal history.
Those older results were not counted as new evaluation cases. Its embedded
24-case policy readout matches the already accepted prior result. The new
baseline values for children 2–5 match that prior policy's net, fees, ending
position and pending-order fields.

This workspace read the supplied text, not the original private Mac source,
full evaluation report, native ledgers, control prefixes or artifact inventory.
Membership, progress, case/profile count identities, baseline signs/states and
printed Decimal arithmetic were checked here. Native integrity, source
preservation and causal checks remain reported by the local runner rather than
independently replayed in this review. Actual venue execution is unknown.

## Every profile retains incomplete economic coverage

All profiles have 79 verified cases. The table counts conditional paper outcomes;
it does not pool their financial returns or treat six assumptions on one
recording as six independent markets.

| Profile | Closed | Unresolved | No fills | Positive closed | Negative closed | Complete profile net |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline | 77 | 2 | 0 | 0 | 77 | Unavailable |
| Lower fee | 77 | 2 | 0 | 0 | 77 | Unavailable |
| Zero fee | 77 | 2 | 0 | 2 | 75 | Unavailable |
| Delay stress | 77 | 2 | 0 | 0 | 77 | Unavailable |
| Liquidity stress | 77 | 2 | 0 | 0 | 77 | Unavailable |
| Slippage stress | 76 | 2 | 1 | 0 | 76 | Unavailable |

The 461 closed cases comprise 459 negative and two positive conditional results;
both positives occur only under the zero-fee assumption. No closed result is
exactly zero. The unresolved and no-fill cases retain unavailable closed P&L,
not fabricated zero-profit trades. There are 474 entry requests and 473 close
requests, with zero known actual executions.

Every profile has unresolved cases, so its complete closed-cycle total is
correctly unavailable despite all software cases verifying. A sum of known closed
cases alone would omit unresolved exposure and cannot replace that total.
Completion here describes processing of the declared cohort, not complete
economic resolution or profitable strategy validation.

## Baseline exposure and limits of this readout

The baseline explicitly reports these two independent hypothetical open cases:

| Case | Ending position, BTC | Assumed fees, USDC | Pending orders | Closed P&L |
| --- | ---: | ---: | --- | --- |
| `run-000008--baseline` | -0.001 | 0.03232776690 | None | Unavailable |
| `run-000056--baseline` | -0.0007025 | 0.042117962024250 | None | Unavailable |

The compact output does not include their close decisions, entry/exit fill
quantities, order rejections or native risk receipts. It therefore does not
establish why exposure remains. Do not infer a partial close, missing decision,
specific rejection or physical network cause from final position/fees alone.
The other profiles' individual unresolved/no-fill IDs are also absent from this
compact readout and must not be inferred from the baseline IDs.

Adding assumed fees back to the baseline's closed results gives two positive
values: child 20 `0.00101520000` USDC and child 58 `0.00500680000` USDC. Both
baseline net results are negative after their declared fees. This add-back still
contains spread and assumed slippage; it is not a zero-cost return or measured
venue execution. Individual zero-fee case IDs are not printed here, so they
were not independently paired with those baseline values.

## Decision and next step

Accept the broader software/evaluation milestone and preserve R001's negative
economic result under these assumptions. A profitable edge has not been
established. The broader evaluation completes the eighth milestone in the chat's
13-item working checklist; the five remaining stages still include reliability,
strategy confirmation, live-data paper work, exchange/testnet integration and
a separately approved small real-money pilot.

Next inspect the 12 unresolved cases and one no-fill case from retained evidence,
including exact requested/filled quantities, close decisions, risk and rejection
details. A read-only extraction can verify their case receipts against the saved
artifact inventory and report their existing state. It must not rerun the policy,
resize a close, choose a favorable profile or manufacture flattening. No new
capture is needed to accept this result. Any later strategy revision needs its
own declared protocol and separately frozen new-data confirmation.

The operational day gate and actual execution calibration remain open. This
acceptance changes documentation only; runtime/native/helper/producer assets and
all prior negative or open reports remain unchanged.

Receipt: `data/mac-development-evaluation-review-20261120T230136Z-93exwndg/`.

## Read the retained exceptions without running another experiment

This extracts the existing 12 unresolved cases and one no-fill case. It checks
the saved audit-inventory hash and each selected full case receipt, preserving
native order rejection details and exact entry/close quantities. It does not
replay native source, alter the policy or send orders. Keep Docker Desktop open
and paste this block in Terminal, then supply its output:

```sh
docker run --rm --network none --read-only \
  --mount "type=bind,src=$HOME/GiethoornData/evaluation-20261120T220630Z-oyufiA/report,dst=/report,readonly" \
  giethoorn-local:0.1.0 python3 -c '
import hashlib,json,re
from pathlib import Path
root=Path("/report")
r=json.loads((root/"evaluation-report.json").read_bytes())
assert r["status"]=="completed" and all(r[k] for k in ("source_unchanged","quality_unchanged","code_unchanged"))
i=r["provenance"]["audit_inventory"]
raw=(root/i["file"]).read_bytes()
assert hashlib.sha256(raw).hexdigest()==i["sha256"], "Audit inventory changed"
files=json.loads(raw)["files"]
def view_case(c):
    name="cases/"+c["case_id"]+"/policy/policy-case.json"
    assert re.fullmatch("run-[0-9]{6}--(baseline|lower-fee|zero-fee|delay-stress|liquidity-stress|slippage-stress)",c["case_id"]), "Unsafe case ID"
    raw=(root/name).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==files[name], "Case receipt changed"
    p=json.loads(raw)
    assert p["metrics"]==c["policy"]["metrics"], "Case metrics differ"
    close=p["close_compilation"]
    return dict(case=c["case_id"],receipt_hash_verified=True,
        close_decision=close["status"],known_position=close["known_position"],
        risk_at_decision=close["risk_at_decision"],metrics=p["metrics"],
        orders=[dict(id=o["order"]["id"],side=o["order"]["side"],
            requested=o["order"]["quantity"],filled=o["native_final_order"]["filled_quantity"],
            outcome=o["outcome"],reference_age_ns=o.get("reference_age_ns"),
            rejection=o["native_final_order"].get("rejection"),
            reason=o["native_final_order"].get("rejection_detail")) for o in p["orders"]])
rows=[view_case(c) for c in r["cases"] if c["status"]=="verified" and c["policy"]["metrics"]["outcome"]!="closed_under_assumptions"]
assert len(rows)==r["totals"]["unresolved"]+r["totals"]["no_fills"], "Exception counts differ"
print(json.dumps(dict(evaluation_id=r["evaluation_id"],retained_case_hashes_verified=len(rows),exception_cases=rows),indent=2))
'
```
