# Decision: broader independent-cycle development evaluation, version 1

Status: implementation contract. Freeze
[the evaluation protocol](../development-evaluation-plan.md) before the broader
run. New namespaces are `development_evaluation_version: 1` and
`evaluation_policy_version: 1`, evaluation ID `r001-development-evaluation-001`.

Replicate the unchanged causal proxy cycle across all frozen development
children and six existing profiles. This expands the cohort, without changing
the signal, execution assumptions, native ledger or old producer assets.
Each child/profile remains an independent flat start with one causal feature.
Do not call this a continuous portfolio backtest, a fresh holdout or actual
execution. Preserve the first four probed children as an explicitly visible
subset and retain the rest even when a case cannot run.

An evaluation-specific controller owns the 128-child/768-case, 16-GiB and
3,600-second whole-suite bounds. The unchanged source, native call, per-case
proxy and causal-prefix verifiers retain their existing stricter local bounds.
The new controller must reserve capacity globally before each source/case,
while existing per-case admission remains enabled within that case's directory.
This avoids changing previously bound helper constants or disabling checkpoint
space checks to accommodate a larger suite.

All inputs and producer assets are bound before/after, including the exact
frozen protocol. Require fresh native source/quality verification and persist
selected features before any profile runs. Keep source/quality read-only,
output create-new/private and network disabled. Do not use an evidence-supplied
executable. Missing or changed evidence cannot produce admitted metrics.

Per-profile counts include every selected case and separate no-signal, no-fill,
unresolved, failed and not-run states. A closed-cycle net sum is unavailable
unless all cases are accounted for, none has unresolved exposure/working orders,
and at least one cycle closes. It never pools profiles or fabricates unknown
returns as zero. A positive result remains exploratory and is not a live gate.

Acceptance follows the protocol's numerical, admission, native-repeat and offline
browser requirements. Preserve all prior negative/open economic results and
native schemas. The operational day gate and actual execution calibration remain
independent outstanding requirements.
