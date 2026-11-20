# Causal known-book proxy policy experiment

Status: protocol specified before implementation; now implemented under
[decision 0016](decisions/0016-causal-proxy-policy.md). See the
[operator guide and software acceptance](causal-proxy-policy.md). This follows
the [accepted fixed-scenario comparison](mac-model-comparison-results.md).
The current comparison remains valid: ten hypothetical positions stay open
because the frozen original scenarios contain no close for their rejected entry.
Do not change those scenarios, add inferred exits or relabel their results.

Policy ID: `r001-known-book-causal-001`, with a new
`causal_proxy_policy_version: 1` output namespace. The signal and the existing
known-book proxy remain separate unchanged versions. The detailed implementation/
version decision and golden fixtures preceded new runtime artifacts. The
original requirements below remain the acceptance contract.

The [first supplied Mac policy readout](mac-causal-policy-results.md) is now
accepted: 24 conditionally closed cases, all negative, with no reported pending
orders or ending position. Prior fixed-plan outcomes remain their own results.

## Fixed cohort and assumptions

Reuse the original frozen cost snapshot's same first four selected development
recordings, features and six profiles. Verify the original source/quality/policy/
producer and native ledger before admission. Preserve missing/unavailable cases
without replacements. These recordings are already explored; this is a new
exploratory policy experiment, not an untouched test or confirmation cohort.

Keep R001 feature selection, five-second warmup, one-second close-decision horizon,
0.001-BTC entry quantity, two-basis-point request limit envelope, collateral/risk
limits and all six fee/slippage/size/latency profiles unchanged. Keep the existing
source BBO freshness and known-book arrival semantics. There is one entry cycle
per child/profile and an independent flat start; no new threshold/fee/delay grid,
signal search, repeated entry or outcome-based selection is introduced.

## Own-position close compilation

1. Reproduce and bind the original feature and entry-only scenario. Run that
   entry through the unchanged proxy compiler/native manual ledger as a control,
   retaining original source links, assumed actions, prefix receipts and costs.
2. Reuse the original `cost_core.close_decision` rule unchanged: the first observed
   source event at/after feature time plus one second with a usable same-connection
   BBO no older than 250 ms. This can use an already known fresh quote at that
   observed event; do not silently require a new BBO message or interpolate time.
3. Read only the control's native state through that decision's source prefix.
   Include earlier queued arrivals, and equal-time arrivals resolved before a
   request at that anchor under the existing tie rules. Exclude later source
   sequences even when timestamps are equal, and any scheduled action beyond the
   decision time. Bind the exact native input/update prefix hashes and state.
4. If entry remains pending at the decision, declare unresolved entry and compile
   no close. If the position is zero, declare flat/no close. If it is nonzero and
   settled, require the same entry direction and at most the target quantity;
   compile the opposite-side close for **that own-position quantity**, using the
   unchanged limit rule and only the decision's known quote. Partial entry size
   must never gain an oversized close from the original model's different path.
5. Run the separately compiled entry/close plan with the unchanged proxy engine.
   Require its complete prefix before the close request to reproduce the control
   prefix exactly. Final source, assumptions, entry and risk configuration must
   match their frozen receipts. Future prices or later control fills cannot alter
   the earlier request, close anchor or chosen close quantity.

No close decision before EOF means no close is manufactured. A pending arrival,
partial close, risk/loss rejection or missing reference retains working orders/
open exposure and unavailable closed P&L. Native risk remains authoritative:
do not bypass a loss halt, invent reduce-only support, resize after rejection,
retry an entry/close or force a closing price to make the result flat.

## Evidence, bounds and acceptance

Use new private output and read-only input with no network, the existing native
image and unchanged manual-ledger compiler/verifier. Retain control and final
plans, source identity, close decision, own-position/prefix receipt, complete
ledgers/links and independently checked costs. Clearly distinguish assumed fills,
unknown actual execution, failed/not-run cases, no fills, pending state and open
exposure. A successful integrity check is not a profitable-trade observation.

Freeze a maximum 24 cases, two requests per case, existing 16-MiB native source/
10,000-paper-record bounds, 2-GiB output admission, 1-GiB free-space reserve,
900-second suite and 30-second native calls, with finite checkpoint/report/HTML
limits. Control/final work must be admitted before starting, and failure cannot
trigger a replacement source or fabricated zero return.

Hand-calculated native tests must cover full/partial/no entry, no close without
position, close quantity from own position, missing/late decision, source-end
pending entry/exit, risk/loss halt and fixed/tied arrival ordering. Changing later
prices or another model's fills must not change the control prefix or compiled
quantity. Verify exact fees, balances, exposure and control/final prefix equality;
test input/producer mutation, budget refusal and offline desktop/mobile views.

Report conditional per-case results, every failed/unresolved state and declared
cost sensitivity, without portfolio aggregation or counting six profiles as
independent markets. Existing closed losses and open fixed-plan cases remain
their original results. Completing policy mechanics cannot by itself establish
an economic edge; later confirmation needs a separately frozen policy and new
data, while the full-day gate and actual execution calibration remain open.
