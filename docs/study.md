# Run the fixed signal study

This study asks whether a three-to-one imbalance in displayed BTC bid/ask size
predicts the next second's midprice direction. Rules were specified before
outcomes in [the research plan](research-plan.md). This produces offline
prediction diagnostics, with no orders, fills or economic returns.

## Start with development

Update `scripts/mac`, `ops/study_core.py`, `ops/study_local.py` and `web/study.html`,
then run from your Mac source directory:

```sh
bash scripts/mac study quality-20261117T125619Z-mAfC1j
```

This uses the user's frozen quality snapshot and its original source parent.
It defaults to the 79 development children. The 26 validation and 28 retrospective
test children have no computed signal outcomes in this run. Other snapshots use
their own identifier and counts. Existing quality/review helpers and the quality
template/theme must match the frozen producer/assets. No rebuild or new capture
is needed. The original copied protocol is used, even if workspace docs change.

The helper checks exact source/quality fingerprints, copies evidence privately,
reruns native audit and reproduces qualification/membership. It computes only
the selected partition, with source read-only and networking disabled. Collector
uptime status remains separate and unchanged.

The saved `~/GiethoornData/study-*/report/study.html` opens in your browser. It shows
signals/abstentions, label availability, hits, same-sample always-up/down controls,
signed midprice movement before costs, and every child's state. Filters inspect
existing results without running another group. The horizon uses recorded receive
monotonic time, not measured venue execution time. Missing outcomes remain explicit;
unchanged prices count as directional misses. The JSON export retains full values.

## Preserve other outcomes

Validation/test runs are explicit separate commands:

```sh
bash scripts/mac study QUALITY-ID validation
bash scripts/mac study QUALITY-ID retrospective_test
```

Start with development rather than running these together. No `all` mode exists.
Repeating a fixed study does not create independent observations; using results
to tune rules makes those data explored. This sample, including inspected run
134, is retrospective. Generalization needs later separately frozen recordings.

## Retained evidence

Keep `study-policy.json`, versioned `features.jsonl`, versioned `samples.jsonl`,
`study-report.json`, the portable view, `input-quality/` and fresh `quality-check/`
evidence together. Report provenance binds the source/quality, policy/code,
auditor, feature/sample and view hashes. Features contain no future labels;
samples refer back to features and original future events or a missing reason.

Each sample's signed basis-point move is an exact fraction. Aggregates round each
sample half-even to 12 decimal places before exact fixed-point summing/averaging;
the displayed mean rounds to six places. Prices/sizes never use binary floats.
Those price moves are not fills or trade P&L. Hit-rate controls share the same
available directional-signal labels, with missing labels/abstentions visible.
Small or correlated counts cannot establish an edge or statistical significance.

Failed verification returns nonzero and no admitted scores. Partial diagnostic
files can remain; their existence is not completion. Original evidence is never
repaired or resumed. Economic testing still needs separately specified entry/exit,
size/risk controls and execution costs. See [decision 0010](decisions/0010-fixed-signal-study.md).
