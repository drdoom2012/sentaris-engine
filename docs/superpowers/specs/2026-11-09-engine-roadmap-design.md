# Sentaris Engine — Vertical-Slice Roadmap

**Status:** Draft for review. Nothing here is approved or scheduled.
**Inputs:** `CLAUDE.md`, `docs/domain.md` revision 3, Quasar contract `../quasar-market-data/docs/contracts/api-v1.md`, Quasar ADR-0002 to ADR-0004 and storage migrations (read 2026-11-09).
**Priority order (as in Quasar):** Correctness → Data Integrity → Reliability → Simplicity → Performance.

Rules are cited by ID and not restated (`docs/domain.md`, section 11). Every recommendation below is a **proposal**; an open decision stays open until the user decides it and it is recorded as `docs/domain.md` section 10 requires. This roadmap does not count as the explicit request that `docs/domain.md` section 2 asks for: each slice still needs one.

## 1. Intent

Reach a working strategy execution engine through small slices, each ending green and demonstrable. The engine stays strategy-agnostic throughout.

**Goals.** One pipeline for live and replay; stateless and stateful strategies; point-in-time snapshots from Quasar; fail-closed evaluation.

**Non-goals.** Any specific strategy, signal kind or pattern; trading (DR-19); a REST endpoint, notifications or performance measures (OD-11, OD-12) unless separately requested; microservices; concurrency before a measured need.

**Anti-goals (failure even if it works).** Availability that is assumed rather than established (DR-06); a replay that sees data live could not have seen (DR-20, DR-21); an engine that branches on state content (DR-25); an open decision settled by whichever code landed first.

## 2. Constraints every slice obeys

- **No production strategy.** Slices are exercised by probe strategies in `tests/support/`, which exist only to return each outcome on command. A probe carries no market logic.
- **No new runtime dependency is foreseen.** Stdlib `urllib.request` and `sqlite3`, in `infrastructure` only. A slice that wants more must justify it.
- **Layers as enforced today.** Pure availability and validation functions live in `domain`; `application` composes them, so filtering happens once (DR-05). Sources are `Protocol`s that `infrastructure` satisfies structurally.
- **Definition of done.** `make check` passes; tests first; `docs/domain.md` updated in the same commit (section 2 capability, section 9 enforcement status). A rule moves to `ENFORCED` only with a named negative test.
- **Workflow.** Each slice gets one plan, `docs/superpowers/plans/YYYY-MM-DD-se-N-<topic>.md`, written with `superpowers:writing-plans` when it is started. No per-slice specs. Decisions go to `docs/adr/`, known gaps to `docs/follow-ups.md`.

## 3. Slice overview

| Slice | Delivers | Needs slices | Blocked by | Main rules |
|---|---|---|---|---|
| SE-1 | Stateless evaluation from a hand-built snapshot | foundation | nothing (Gate 1 decided) | DR-08 to 11, 13, 14, 23, 26 |
| SE-2 | Several independent strategies in one execution | SE-1 | OD-15 | DR-10, 22 |
| SE-3 | Optional strategy state, in memory | SE-2 | OD-17, 19, part of 20 | DR-25, 26, 27 |
| SE-4 | Quasar candle client | SE-1 | none beyond SE-1 | DR-11, 18 |
| SE-5 | Point-in-time candle snapshot | SE-1, SE-4 | OD-6, part of 7, part of 13 | DR-01, 02, 05, 06, 07, 20 |
| SE-6 | Data-quality gate | SE-5 | OD-8 | DR-15, 16, 17 |
| SE-7 | Durable state and signals | SE-3 | OD-11, 18, 20 | DR-27, 28 |
| SE-8 | Historical replay, stateless strategies | SE-2, SE-6 | OD-5, 7, 12, 23, 24 | DR-12, 13, 21, 26 |
| SE-8b | Historical replay, stateful strategies | SE-3, SE-8 | OD-17, 19, part of 20 | DR-13, 25, 26, 27 |
| SE-9 | One live evaluation pass | SE-2, SE-6, and SE-7 for stateful strategies | OD-4, 5, 11 | DR-12, 26, 28 |
| SE-10 | Live scan loop | SE-9 | OD-5, 19 | DR-28 |
| SE-11 | Open interest input (when a strategy needs it) | SE-6 | OD-6, 7, 8 for this input | DR-03, 07, 24 |
| SE-12 | Funding input (when a strategy needs it) | SE-6 | OD-6, 7, 8, 16 | DR-03, 04, 07, 24 |

**Replay is split by state.** SE-8 replays stateless strategies through the SE-2 execution, so it waits for neither the state decisions (OD-17, OD-19, OD-20) nor SE-3 and SE-7, and it produces DR-13 and DR-21 evidence early. SE-8b adds state to the same replay runner, exactly as SE-3 adds it to execution; it keeps state in memory per run, so it does not need SE-7 (subject to OD-20). There is still one pipeline: neither slice introduces a replay-only evaluation path, and SE-8b must leave SE-8's output for stateless strategies byte-identical. The risk of the split, a stateless runner shaped in a way state cannot extend, is limited by both requirements. A stateful strategy cannot be replayed before SE-8b.

SE-9 can precede SE-8 if OD-7 takes longer to settle. SE-4 can proceed while the availability decisions are open.

OD-9 (indicators) blocks no slice here. It blocks the first strategy that wants one.

## 4. Slices

### SE-1 — Stateless evaluation

- **Scope.** Domain types for time, candle, immutable snapshot, parameters, evaluation context, signal and the three-outcome result; the canonical form of a signal payload (ADR-0001), which defines payload equality, with a strict decoder for it (ADR-0001: a decoder accepts only canonical bytes; the round-trip tests need one); a stateless strategy contract with identity and version; an application function that evaluates one strategy on one context.
- **Rules.** DR-08, 09, 10, 11, 12, 13, 14, 23, 26 (stateless form). **Decisions.** OD-3 (part), 10, 13 (part), 14, 21 — all decided in ADR-0001, including the Gate 1 clarifications (`docs/domain.md` revision 8).
- **Acceptance.** A probe yields signal(s), no signal and failure with a machine-readable reason, and these are distinct types. The snapshot cannot be mutated. No engine type enumerates a signal kind. A payload's canonical form is the same bytes in every process, and decoding then encoding, or encoding then decoding, reproduces the input exactly.
- **Tests.**
  - *Evaluation.* Each outcome; deep equality of repeated evaluations (DR-13); `Decimal` exactness with a value `float` cannot represent; mutation attempts fail, nested containers included; shuffled input order gives the same result.
  - *Canonical form.* Every ADR-0001 test vector byte for byte; `"1"`, `1`, `True`, `Decimal("1")` and `None` all distinct; `Decimal("1.0")` ≠ `Decimal("1.00")`; null ≠ absent key; mappings built in different key orders give identical bytes; each excluded value rejected at construction, among them ±2^53 (with ±(2^53 − 1) accepted), `IntEnum` and `(str, Enum)` members, subclasses of `str`, `int` and `Decimal`, `set` and `frozenset`, and a duplicate key given as pairs; a `list` or `dict` changed after construction leaves the payload unchanged.
  - *Cross-process stability.* The test vectors and a fixed corpus are encoded in separate interpreter processes (`sys.executable -I`) that differ in `PYTHONHASHSEED` and in the `decimal` context (`capitals = 0`, another precision and rounding, traps enabled); every process yields bytes identical to the in-process result and to the vectors.
  - *Round trips.* For every vector and corpus entry, `encode(decode(b)) == b`, and `decode(encode(p))` reproduces `p` exactly: the same kind at every position (`bool` is not `int`, `Decimal` is not `str`), equal `Decimal.as_tuple()`, null kept apart from an absent key, sequence order kept. The decoder rejects every non-canonical input, each with its own negative test: whitespace, a byte-order mark, a trailing newline, unsorted or duplicate keys, an uppercase or unnecessary escape (`\u001B`, `A`, `\/`), a `Decimal` as a JSON number or with non-canonical text (`1.0E+1`, lowercase `e`), an integer with a leading zero, written `-0` or outside ±(2^53 − 1), an escaped surrogate, invalid UTF-8, and a tag object with an unknown or extra key.
- **Observable.** `make test` shows a probe evaluated end to end from a fixture snapshot.

### SE-2 — Multi-strategy execution

- **Scope.** Evaluate several strategies against one `as_of`, collect per-strategy results.
- **Rules.** DR-10, 22. **Decisions.** OD-15, including how a raised exception is reported.
- **Acceptance.** Registration order does not change output; one strategy failing or raising leaves the others' results identical.
- **Tests.** Permuted strategy order; a raising probe beside a healthy one, compared with the healthy one run alone (negative test for DR-22).
- **Observable.** One execution reports a result for each strategy, including the failed one.

### SE-3 — Optional strategy state, in memory

- **Scope.** Stateful contract; opaque state type; in-memory store keyed by evaluation scope; execution loads, passes and stores state. Stateless strategies are untouched.
- **Rules.** DR-25, 26, 27. **Decisions.** OD-17, OD-19, OD-20 (opaque encoding, and whether running without persistence is allowed).
- **Acceptance.** Sequential evaluations thread state through a probe; the first evaluation has none; state never crosses a scope; a stateless strategy receives none; failure handling follows OD-19.
- **Tests.** Probe whose transition counts evaluations; two scopes interleaved; a state value the engine could not inspect, passed through unchanged; determinism over a sequence.
- **Observable.** A test shows a multi-step transition sequence, reproduced byte for byte on a second run.

### SE-4 — Quasar candle client

- **Scope.** `infrastructure` client for `GET /v1/candles`: time-based paging with the echoed `end`, the 1000-row and 10 000-slot limits, exact decimal text, `conflicted` and `coverage` retained, unknown fields ignored.
- **Rules.** DR-11, 15, 18. **Decisions.** None beyond SE-1 (it takes the contract's `venue`, `symbol`, `timeframe` as given).
- **Acceptance.** Every contract error maps to a typed outcome; `503` is never empty data; `404 unknown_series` is distinct from an empty `200`; paging terminates; a page boundary loses and repeats nothing.
- **Tests.** Stub local HTTP server with contract-shaped fixtures; exactly-full last page; `503` with and without `Retry-After`; a numeric JSON price rejected. A `live`-marked test against a running Quasar.
- **Observable.** `pytest -m live` reads real candles as exact decimals.

### SE-5 — Point-in-time candle snapshot

- **Scope.** Pure availability filter in `domain`; snapshot builder in `application` over a source protocol; a strategy declares the candle series it needs.
- **Rules.** DR-01, 02, 05, 06, 07, 20, 21 (live part). **Decisions.** OD-6, OD-7 (conflicted rows), OD-13 (input declaration).
- **Acceptance.** A row unavailable at `as_of` cannot reach a strategy; boundary instants behave exactly per the OD-6 decision; availability that cannot be established yields a failure, not a snapshot.
- **Tests.** Rows stamped after `as_of` plus a forming candle must be ignored (DR-07), compared with the same run without those rows; exact-boundary cases; unknown availability; conflicted rows per OD-7.
- **Observable.** Stub or live Quasar → snapshot → probe → result: the first full vertical path.

### SE-6 — Data-quality gate

- **Scope.** Pure pre-evaluation validation producing machine-readable failures before any strategy runs.
- **Rules.** DR-15, 16, 17. **Decisions.** OD-8, OD-3 (reason taxonomy).
- **Acceptance.** Each OD-8 condition produces its own reason; no value is ever filled; a failure never appears as no signal.
- **Tests.** Missing series, too little history, a gap, stale tail, `as_of` before stored history and inside a hole (DR-21); each with a negative test.
- **Observable.** A gapped fixture yields a named failure and the probe is shown not to have run.

### SE-7 — Durable state and signals

- **Scope.** SQLite store owned by the engine, in `infrastructure`, behind the SE-3 store contract. One transaction records `next_state` with its signals.
- **Rules.** DR-27, 28. **Decisions.** OD-11, OD-18, OD-20; OD-19 (lost versus first state).
- **Acceptance.** State survives restart; state and signals commit together or not at all; re-processing neither re-emits nor advances; concurrent use of one `previous_state` records one transition.
- **Tests.** Fault injected between the writes; duplicate processing; a stale `previous_state` rejected; byte-identical encoding; an unreadable store fails rather than reading as a first evaluation.
- **Observable.** A process-restart test continues the transition sequence exactly.

### SE-8 — Historical replay, stateless strategies

- **Scope.** Run the unchanged SE-2 execution over an `as_of` sequence for stateless strategies, on data that is consistent for the whole run as OD-24 decides.
- **Rules.** DR-12, 13, 21, 26 (stateless form). **Decisions.** OD-5 (step and range), OD-7, OD-12, OD-23 (late-collected rows), OD-24 (consistent data within a run).
- **Acceptance.** Output equals the same contexts evaluated one by one through the same execution as live; no mode flag reaches a strategy; holes and pre-history are failures; late-collected rows are treated as OD-23 decides; nothing reads or writes strategy state; once the stateful contract exists, a stateful strategy given to SE-8 is refused as a whole, never evaluated without its state.
- **Tests.** Repeated runs identical; a later row added to the source cannot change results at earlier `as_of` values; a row backfilled into the source during a run behaves as OD-24 decides; replay versus step-by-step equivalence; a permuted strategy list gives the same output (DR-10).
- **Observable.** A replay over a fixture range produces the OD-12 output, identical across runs.

### SE-8b — Historical replay, stateful strategies

- **Scope.** Extend the SE-8 runner with the SE-3 state handling: state is threaded through the `as_of` sequence and isolated per run.
- **Rules.** DR-13, 25, 26, 27. **Decisions.** OD-17 (a run's initial state and its separation from live state), OD-19 (failure and continuity within a run), OD-20 (in-memory state for a run).
- **Acceptance.** A run's initial state and its separation from live state follow OD-17, and replay never alters live state; state never crosses runs or scopes; the transition sequence equals the same transitions applied step by step; SE-8's output for stateless strategies is byte-identical; a failure mid-run follows OD-19.
- **Tests.** Counting probe over a range, repeated runs identical; two runs interleaved; a run beside a live state store that stays untouched; SE-8's regression fixtures unchanged.
- **Observable.** A stateful probe's transition sequence over a fixture range, identical across runs.

### SE-9 — One live evaluation pass

- **Scope.** Real clock in `infrastructure` chooses `as_of`; one pass over the universe; results reported per OD-11.
- **Rules.** DR-12, 26, 28. **Decisions.** OD-4, OD-5, OD-11.
- **Acceptance.** Same results as SE-8 (stateless strategies) or SE-8b (stateful strategies) for the same inputs under an injected clock; per-instrument failures stay isolated; Quasar down produces failures, never empty results.
- **Tests.** Injected clock; partial universe failure; `live`-marked test.
- **Observable.** One command-driven pass against a running Quasar prints each result.

### SE-10 — Live scan loop

- **Scope.** Repeating SE-9 on the OD-5 schedule, with clean shutdown and restart.
- **Rules.** DR-28. **Decisions.** OD-5, OD-19 (missed and out-of-order `as_of`).
- **Acceptance.** No transition lost or applied twice across restart; a missed `as_of` follows OD-19.
- **Tests.** Fake clock and scheduler; restart mid-cycle; skipped boundary.
- **Observable.** The loop runs against Quasar, stops, resumes and shows no duplicate transition.

### SE-11 and SE-12 — Further inputs (on demand)

Each adds a client method, an availability rule, validation and a `docs/domain.md` section 6 entry, and neither is built before a strategy needs it. **Rules.** DR-03, 07, 15, 24, and DR-04 for funding. **Decisions.** OD-6, 7, 8 for that input, and OD-16 for funding. **Acceptance and tests.** DR-07 after-`as_of` rows ignored; a same-timestamp join across kinds is impossible or fails a test (open interest `time_ms` is a period end; funding is an instant). **Observable.** A probe receives the new series in a snapshot.

## 5. Decisions to resolve

### Gate 1 — before SE-1

**Decided 2026-11-10.** The decisions are in `docs/adr/0001-evaluation-types-and-strategy-contract.md`, with the established direction in `docs/domain.md` section 10. The original proposals are superseded and not repeated here.

| Decision | Status | Where |
|---|---|---|
| OD-10 time | Decided | ADR-0001; `docs/domain.md` section 10, "Time" |
| OD-3 result | Shape decided; failure-code taxonomy and evidence still open (expected with SE-6) | ADR-0001; section 10, "Result shape" and the OD-3 row |
| OD-14 signal | Decided, including null, nesting and the canonical form of a payload | ADR-0001, "Canonical form of a payload" (normative); section 10, "Signal representation" |
| OD-13 contract | Identity, the two contracts, registration and parameters decided; input declaration (SE-5) and the location of strategy specifications still open | ADR-0001; section 10, "Strategy contract" and the OD-13 row |
| OD-21 instrument (was G-1) | Decided: one primary instrument per evaluation context; data of other instruments is OD-22, open | ADR-0001; section 10 |

**Clarifications, decided 2026-11-10.** The review of ADR-0001 found five points it left ambiguous or process-dependent: which Python types count as each payload kind, mutable inputs, duplicate keys, the `Decimal` text under a non-default `decimal` context together with integer size, and the "one-key tag" wording. The user approved them as proposed; they are in ADR-0001 ("Which Python values are payload values", the integer and `Decimal` rows of the canonical form, the added test vectors) and `docs/domain.md` revision 8. The integer range ±(2^53 − 1) follows from signals reaching a database, a frontend and notifications. SE-1 is unblocked.

### Gate 2 — availability, the main architectural decision (OD-6, OD-7; SE-5, SE-8)

DR-06 currently makes every Quasar-backed evaluation a failure, because no response says when a row became available. Three different times are involved, and they must not be conflated:

- **Publication** — when the venue made a value public. DR-01 and DR-04 are phrased in it. Quasar does not record it.
- **Ingestion** — when Quasar's Collector stored the row. Quasar records it, but does not expose it.
- **Revision** — when a different value for the same slot became known. Quasar records only the revisions it observed itself.

Since the engine reads only Quasar (DR-18), what it could have known at `as_of` is bounded by ingestion, not by publication. Whether "published" in DR-01 may be read as "ingested by Quasar" is part of OD-6 and is not decided here.

**Findings** (Quasar repository, read 2026-11-10):

- Candle, open interest and funding rows carry `ingested_at_ms` (migrations 001 to 003). Decision Q5 keeps it out of the API as diagnostic.
- Conflict records carry `first_seen_at_ms`, not `recorded_at_ms`: each one is a differing observation, stamped with the time Quasar first saw it. `recorded_at_ms` exists only on `unavailable_candles`. *(This corrects an earlier version of this roadmap.)*
- Triggers make rows and conflict records immutable (no `UPDATE`, no `DELETE`). The first stored value and its ingestion time therefore never change in place. `funding_rate_verified` is the exception: it may grow, so its past state is not kept.
- `ingested_at_ms` is one wall-clock reading per write batch, taken by the Collector before the write transaction commits (`collector/fetch_once.py`, `collector/candle_writer.py`). No bound on the time from that reading to commit is documented, and the reading is not monotonic.
- `conflicted` is a present-tense flag. It cannot say whether the conflict was known at a past `as_of`.
- The API does not reveal whether a row was backfilled.
- A value the venue revised but Quasar never fetched again leaves no trace in Quasar.

| Option | Live | Replay | Cost |
|---|---|---|---|
| **A. Expose ingestion time and conflict first-seen time** (additive `/v1` fields); a row usable when also closed and `ingested_at_ms ≤ as_of` | Consistent with replay only within the unbounded stamp-to-commit lag and the clock skew between Collector and engine (E-1, E-2) | Approximates what Quasar held at `as_of`: backfilled rows are recognisable as later; observed conflicts are time-scoped by `first_seen_at_ms`; revisions Quasar never observed stay invisible (E-4) | Changes a Quasar decision (Q5, ADR-0002 P-2). Backfilled rows fail in replay, shortening usable history. Depends on Quasar never rebuilding or re-importing its store (E-3) |
| **B. Engine-applied delay per input** | Workable | Modelled: backfilled and revised rows are indistinguishable, so DR-20 and DR-21 are not met as written | No Quasar change, but replay would need those rules amended |
| **C. Engine records what it saw during live scans** | What the engine read, by definition | Equal to what the engine read live, only from when recording began | Needs SE-7 and SE-9 first; no history at the start; only as complete as the engine's own record |

**Evidence needed before A can be called point-in-time:**

- **E-1.** A bound on the lag from `ingested_at_ms` to commit, or a stamp taken at commit. Without one, a row stamped at or before `as_of` may not yet have been readable at `as_of`.
- **E-2.** A bound on the skew between the Collector's and the engine's clocks, and the behavior when wall clocks jump.
- **E-3.** Quasar's operational guarantee that a store is never rebuilt, restored or re-imported in a way that rewrites `ingested_at_ms`.
- **E-4.** Whether DR-20's "the source" means Quasar or the venue. If it means the venue, no option meets DR-20 for revisions Quasar did not observe.

**Assessment, not a decision.** A is the only option that could satisfy DR-20 and DR-21 on existing history without amending them, and only to the extent that E-1 to E-4 are established; until then it is an approximation with known gaps, not an exact reconstruction. It needs a Quasar contract change approved in that project. C is exact only for the engine's own observations. If usable replay over backfilled history matters more, that is a deliberate amendment of DR-21 (OD-23), not an implementation detail. The choice belongs to OD-6 and OD-7.

**OD-23 (was G-2; open in `docs/domain.md`).** Late collection breaks live/replay equality under B. A candle the Collector stored late is a failure live but present in replay, against the "Historical replay" concept in `docs/domain.md` section 3. A resolves it only as far as E-1 to E-3 hold; B cannot. OD-23 is decided together with OD-6 and OD-7, and blocks SE-8.

### Gate 3 — state (before SE-3, SE-7 and SE-8b)

| Decision | Proposal |
|---|---|
| OD-17 scope | Strategy, version, venue, symbol, timeframe, a parameter-set digest, and a run identity (live or a replay id). On version or parameter change: refuse until an explicit operator action. |
| OD-19 continuity | A failure keeps the previous state unchanged. Missing or out-of-order `as_of` is refused. A store records "never evaluated" explicitly so lost state is distinguishable. |
| OD-20 encoding | State is `bytes` the strategy encodes, which makes opacity structural. A stateful strategy may run in memory only in tests and replay. `json` would join the import allowlist if strategies need it. |
| OD-18 identity | Signal identity derived from scope, `as_of` and signal index. Delivery is the transactional outbox implied by SE-7, at-least-once to any future consumer, deduplicated by that identity. |
| OD-11 delivery | Persist locally, print to stdout. No REST and no notifications for now. |

### Gate 4 — operation (before SE-6, SE-8 to SE-10)

| Decision | Note |
|---|---|
| OD-8 | Thresholds need your values. Proposal: strategies declare minimum history; gaps are never tolerated; staleness is one engine-wide rule per input. |
| OD-5 | Proposal: live `as_of` is a timeframe boundary plus a fixed offset; replay steps by the timeframe. |
| OD-12 | Proposal: replay output is the ordered result sequence only, with no performance measure. |
| OD-4 | Proposal: engine-owned configuration. `GET /v1/instruments` is implemented, but contract section 6.4 still reads PROPOSED; confirm before relying on it. Quasar serves only `binance-usdm` and `5m` today. |
| OD-24 (was G-3) | Quasar pages are not a snapshot (contract section 3), and a backfill during a replay could make two runs differ. Proposal: a replay reads its data once and evaluates over that frozen copy; the proposal rests on DR-13. The contract's suggested check against `/v1/coverage` describes only the present (DR-21), so it cannot by itself establish consistency for a past window. |

G-1, G-2 and G-3 are recorded in `docs/domain.md` section 10 as OD-21 (decided), OD-23 and OD-24 (both open). The proposals in this section stay proposals until the user decides them.

## 6. Left to each slice's plan

Module names, type names, stub-server mechanics, fixture format, the SQLite schema and the exact CLI surface.
