# Decision: separately versioned bounded additional-close experiment

Status: protocol specified; implementation and evaluation pending. Follow the
[predeclared bounded-exit protocol](../bounded-exit-plan.md), experiment
`r001-bounded-exit-002`, with new policy/report namespaces at version 1.

The supplied development exceptions reconcile with the unchanged model:
six closes fail its price-limit test, six close partly within its assumed
liquidity budget, and one entry fails its price-limit test. Quantity/accounting
arithmetic matches; this evidence does not demonstrate an engine bug. Original
outcomes and all declared cost/limit/size rules remain their own results.

The new experiment permits only one additional close after the original attempt
has terminal native state. Choose the first subsequent eligible native BBO from
information available then and size only from the settled residual position.
Require complete control/new prefix equality before that request and independent
source/Decimal/native checks. Keep risk halt, source EOF and missing/partial
execution states explicit; no limit widening or loop until flat is allowed.

Reuse the full frozen development cohort and six profiles, not only observed
exceptions. Preserve entry/first-close requests, native schemas and old producer
assets. Bound the extra work and retain unavailable cases without replacements.
This is an exposure-management experiment on explored data. It cannot establish
a profitable R001 edge, actual fill calibration or readiness for funded trading.
