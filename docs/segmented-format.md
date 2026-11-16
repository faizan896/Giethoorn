# Segmented recording container, version 1

Status: implemented and tested. Container version 1 wraps a single declared event
schema, 1 or 2. Schema-1 events and quote serialization are unchanged. Explicit
feed profiles use [event/normalization schema 2](feed-profiles.md) in the same
storage layout. Mixed/unsupported schemas and record/header disagreement fail.

## Layout and CLI

```text
data/example-session/          # fresh, exclusively owned directory
  index.jsonl                 # header, sealed descriptors, finalization footer
  segment-00000001.jsonl       # whole newline-terminated event records
  segment-00000002.jsonl
  ...
```

`collect --output-dir PATH` writes a directory. `capture --output FILE` preserves
the original single-file mode. `replay --input PATH` and `inspect --input PATH`
detect the container by directory versus file. Keep quote output and other
artifacts outside the container: unexpected entries are rejected, not ignored.

Each record retains its global sequence and monotonic origin across rotation.
Rotation does not reconnect the exchange, clear the book, reset a sequence or
insert artificial market events. No record spans segments or exceeds its segment
budget. If one record cannot fit an empty segment, capture stops explicitly.

## Index contract

`index.jsonl` is append-only, with a separate tagged JSON object on each line:

| Kind | Meaning |
| --- | --- |
| `header` | Container/event versions and configured segment/session byte limits |
| `segment` | Canonical number/name, exact byte count, first/last event sequence, SHA-256 over exact file bytes |
| `end` | Final number of sealed segments, record count and total data bytes |

There is exactly one header, contiguous one-based segment numbers, and at most
one terminal footer. Filenames must be `segment-` plus eight decimal digits plus
`.jsonl`, matching their descriptor numbers. Symlinks, nonregular entries, missing
files, path traversal, extra files and malformed complete index lines are rejected.

Implementation bounds: 65,536 segments, 4 KiB per index line, a bounded index
file, and the existing 4 MiB per event. Verification uses bounded record buffers;
replay keeps one data file open at a time plus the index lock. Container version
1 specifies SHA-256; it does not negotiate a different checksum algorithm.

## Write ordering and durability

1. A new directory and index are created exclusively. On Unix their directory
   entries are synchronized. The writer holds an exclusive advisory index lock.
2. Each record is written and synchronized before it is processed or an associated
   outgoing intent is sent, just as in single-file mode.
3. Before rotation, the current file is synchronized; its incremental SHA-256
   descriptor is then appended and synchronized in the index.
4. Only after that seal commit may the next canonical data file be created.
5. The explicit event `session_ended` is recorded before the last segment is
   sealed and the index footer is synchronized. Drop never manufactures completion.

Append/index errors poison the writer. No subsequent events or application intents
are sent through that recorder. Filesystem/hardware durability guarantees still
apply; process-kill tests are not power-failure or storage-controller tests.

## Budgets and retention policy

| Flag | Default | Scope |
| --- | --- | --- |
| `--max-segment-bytes` | 64 MiB | Each data file, including newline bytes |
| `--max-session-bytes` | 1 GiB | Sum of all data files and index lengths |
| `--min-free-disk-bytes` | 1 GiB | Best-effort filesystem reserve, checked before writes |

A 1 KiB reserve is included when accepting data so that the active seal and
footer can fit the session budget. A write that would consume that reserve stops
before it is attempted; the exact final size may be below the nominal budget.
Small invalid budgets are rejected before creating a recording directory.

The policy is **retain and stop**: never overwrite, prune, wrap around, or delete
older segments to keep collecting. All successfully recorded data remains for
diagnosis or explicit archiving. A restart uses a new directory. There is no
restart-in-place or automatic cross-session cleanup.

The byte budget measures logical file lengths, not filesystem block allocation,
directory overhead, redirected stdout, other sessions or external writers. Free
space checks are not a reserved OS quota. An external writer can still exhaust
space and finalization can fail; such a run requires explicit recovery.

## Reader and integrity contract

The reader takes a shared index lock and refuses an active cooperating writer,
including in recovery mode. It verifies every sealed file's size, record
boundaries, sequence range and SHA-256 before emitting any quote. Then it streams
the original records through the same deterministic engine. The index/footer and
the engine's final record count must agree.

Use an unchanged directory while replaying it. Advisory locking coordinates the
product's writer and readers; it does not prevent arbitrary external programs
from editing a file. Hashes detect accidental content changes against the index;
they do not authenticate the index or protect against someone rewriting both
data and hashes. This is not a signed, tamper-proof or replicated archive.

`inspect` adds a `storage` object with format, total bytes, sealed-segment count,
unsealed-tail presence and finalization status. Existing event and quote outputs
are unchanged. A failed but cleanly closed capture can have a finalized container;
always inspect the session end reason as well.

## Crash recovery

Default replay requires the footer and an explicit event end. After stopping a
failed process:

```sh
./scripts/dev run --locked -- replay --input data/example-session --allow-incomplete
./scripts/dev run --locked -- inspect --input data/example-session --allow-incomplete
```

| Interruption point | Recovery behavior |
| --- | --- |
| During a data write | Verify sealed files; accept valid complete records from the one tail; discard only an unterminated final fragment |
| After data sync, before index seal commit | Treat that next canonical file as the unsealed tail |
| During a seal index line | Drop only the unterminated last index fragment, then recover that unsealed file |
| After the final event but before footer commit | Recover records, but report `complete=false` and storage `finalized=false` |
| After a committed footer | Require every sealed file and verify all checksums; trailing data is an error |

There can be at most one unindexed tail because seals commit before another file
is created. Unexpected extra files are errors. A malformed newline-terminated
record or index line is never skipped. A sealed checksum failure is always fatal,
even with `--allow-incomplete`. Recovery tails have no committed checksum; their
JSON, schema, event order and market data are still validated.

A container without its footer remains incomplete even if its last event says
`duration_elapsed`. Recovered quotes are not proof of a complete capture, and
an empty container has no usable event prefix.

## Verification

Tests cover boundary rotation, byte-identical replay, session budgets including
index growth, safe stop, late-segment corruption before output, missing/extra files,
bad metadata, symlinks, advisory locks, torn tails/index entries and footer rules.
The production CLI is exercised over local HTTP CONNECT plus verified TLS, with
both normal rotation and an actual SIGKILL followed by recovery. Those tests use
no exchange, credentials or funds. A separate short real Hyperliquid rotation
check and independent Python SHA-256 verification are recorded in `status.md`.
