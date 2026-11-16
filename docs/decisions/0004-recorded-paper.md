# Decision: recorded-market paper marks, version 2

Status: implemented for offline validation. This does not activate strategies,
fills, live-feed paper execution or authenticated orders. The actual 24-hour
collection gate remains pending; finalized child recordings can independently
support this offline work.

## Compatibility and purpose

Paper schema/model version 1 keeps its input semantics and exact golden output.
Market event schemas 1/2, normalization and recording containers are unchanged.
Version 2 paper records add a `recorded_market` source and permit only session
start/end, market marks, disconnection and timer events. Orders, acknowledgements,
cancels, assumed fills and halts are rejected. A stream cannot change versions;
recorded sources require v2, while synthetic/manual scenarios require v1.
The FIFO ledger and exact decimal arithmetic are unchanged. Version 2 reports
`disabled_market_marks_only` as its fill model.

This first adapter verifies that real recorded prices, independent channel health
and replay ordering can reach the paper ledger. Its fixed 10,000 USDC starting
balance is explicitly assumed. No fills occur, the fee model is inactive and flat
P&L is an integration result, not strategy-performance evidence.

## Input, ownership and provenance

`paper-market-replay` accepts one finalized, complete, segmented schema-2 recording
and an explicitly selected BBO/depth feed. Active writers, crash prefixes, legacy
schema-1 recordings and disabled feeds are rejected. A valid finalized recording
from an interrupted supervisor can be used; its parent window is still incomplete.

The caller must declare `captured-public-data` or `synthetic-fixture`. This origin
is never inferred from a journal's shape. It appears in every paper update and
the source manifest. Checksums establish internal consistency, not exchange
authentication or proof of complete delivery.

The adapter holds the source index's cooperative shared lock, checks all sealed
data and replays all source records before creating output. It copies the bounded
source into a new private output directory and verifies the copy again. Output
inside the original recording and overwriting any existing output are forbidden.
Source files are regular files; names and canonical container structure are
validated by the existing recording reader.

The recording fingerprint is SHA-256 of the byte prefix
`giethoorn-recorded-market-v1` followed by a zero byte, then compact UTF-8 JSON of
the source-file list. Files sort by filename. Each entry has fields in the fixed
order `file`, `bytes`, `sha256`; file hashes cover every original byte, including
the index and market timer records. Both source copies and fingerprints remain
beside the derived paper inputs, updates, source links and reports.

## Time, marks and completeness

Each original market record maps to one paper input at that exact recorded
monotonic time. Inputs are synchronized before applying paper transitions.
Only acknowledged, usable two-sided quotes on the selected feed create marks.
The other feed cannot update the selected mark or extend its freshness deadline.
Timers, empty sides and connection resets preserve conservative eligibility.
Invalid locked/crossed BBOs fail source validation before any paper output is
created; the original source remains unchanged.

Per-update links retain the original sequence, connection, wall/monotonic time,
selected quote and independent feed states. Feed ages advance on recorded time,
not the observer's clock. A final generated paper end event refers to the last
original record; it does not invent another market event or finalize source data.

Replay completion means this one finalized recording was processed. The adapter
always reports `full_window_verified: false` and `strategy_enabled: false`.
It cannot attest a supervisor's 24-hour window. It never repairs an interrupted
root, changes original validation counters or concatenates sessions into a
continuous market timeline.

## Bounds and visible replay

The first version permits at most 16 MiB of source files, 1,024 files, and fewer
than 10,000 original records so the generated paper end fits the existing record
limit. Derived output is capped at 32 MiB; portable HTML at 16 MiB. A failed limit,
recording validation or output write is terminal, retains diagnostics and does
not publish a success view. No sampling or silent record dropping is used.

`ops/paper_market.py` independently replays the persisted paper inputs, requires
exact output/report agreement, rechecks source fingerprints and links, and then
embeds the states in Paper Lab. Real captures and synthetic fixtures have distinct
labels. The viewer displays historical feed states, actual recorded prices, source
sequences and fingerprints, with broken chart segments across unusable periods.
Its event trace shows at most 40 buttons; all events remain accessible through the
slider and portable data files.

## Acceptance and next step

Versioned synthetic market fixtures verify exact repeated output, original-event
links, independent feed selection, deadline/empty/reconnect handling, locked-book
rejection, writer exclusion, corruption, strict provenance/version boundaries,
output preservation, record limits and CLI replay. Original v1 golden tests pass.

Next is a separately specified offline execution-assumption model and controlled
order scenarios using recorded data, with explicit fees and execution uncertainty.
Strategy evaluation and live integration remain gated on their own evidence,
including the outstanding runtime/collection reliability work.
