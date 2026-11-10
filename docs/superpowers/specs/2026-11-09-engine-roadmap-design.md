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
| SE-1 | Stateless evaluation from a hand-built snapshot | foundation | OD-3, 10, 13, 14, G-1 | DR-08 to 11, 14, 23, 26 |
| SE-2 | Several independent strategies in one execution | SE-1 | OD-15 | DR-10, 22 |
| SE-3 | Optional strategy state, in memory | SE-2 | OD-17, 19, part of 20 | DR-25, 26, 27 |
| SE-4 | Quasar candle client | SE-1 | none beyond SE-1 | DR-11, 18 |
| SE-5 | Point-in-time candle snapshot | SE-1, SE-4 | OD-6, part of 7, part of 13 | DR-01, 02, 05, 06, 07, 20 |
| SE-6 | Data-quality gate | SE-5 | OD-8 | DR-15, 16, 17 |
| SE-7 | Durable state and signals | SE-3 | OD-11, 18, 20 | DR-27, 28 |
| SE-8 | Historical replay | SE-3, SE-6 | OD-5, 7, 12, 17 | DR-12, 13, 21, 26 |
| SE-9 | One live evaluation pass | SE-6, and SE-7 for stateful strategies | OD-4, 5, 11 | DR-12, 26, 28 |
| SE-10 | Live scan loop | SE-9 | OD-5, 19 | DR-28 |
| SE-11 | Open interest input (when a strategy needs it) | SE-6 | OD-6, 7, 8 for this input | DR-03, 07, 24 |
| SE-12 | Funding input (when a strategy needs it) | SE-6 | OD-6, 7, 8, 16 | DR-03, 04, 07, 24 |

SE-8 does not depend on SE-7: replay runs on in-memory state. SE-9 can precede SE-8 if OD-7 takes longer to settle. SE-4 can proceed while the availability decisions are open.

OD-9 (indicators) blocks no slice here. It blocks the first strategy that wants one.

## 4. Slices

### SE-1 — Stateless evaluation

- **Scope.** Domain types for time, candle, immutable snapshot, parameters, evaluation context, signal and the three-outcome result; a stateless strategy contract with identity and version; an application function that evaluates one strategy on one context.
- **Rules.** DR-08, 09, 10, 11, 12, 14, 23, 26 (stateless form). **Decisions.** OD-3, 10, 13 (identity only), 14, G-1.
- **Acceptance.** A probe yields signal(s), no signal and failure with a machine-readable reason, and these are distinct types. The snapshot cannot be mutated. No engine type enumerates a signal kind.
- **Tests.** Each outcome; deep equality of repeated evaluations (DR-13); `Decimal` exactness with a value `float` cannot represent; mutation attempts fail; shuffled input order gives the same result.
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

### SE-8 — Historical replay

- **Scope.** Run the unchanged pipeline over an `as_of` sequence, on a dataset frozen at the start of the run, with state isolated per run.
- **Rules.** DR-12, 13, 21, 26. **Decisions.** OD-5 (step and range), OD-7, OD-12, OD-17 (replay against live state), G-2, G-3.
- **Acceptance.** Output equals the same contexts evaluated one by one; no mode flag reaches a strategy; holes and pre-history are failures; replay never touches live state.
- **Tests.** Repeated runs identical; a later row added to the source cannot change results at earlier `as_of` values; replay versus step-by-step equivalence.
- **Observable.** A replay over a fixture range produces the OD-12 output, identical across runs.

### SE-9 — One live evaluation pass

- **Scope.** Real clock in `infrastructure` chooses `as_of`; one pass over the universe; results reported per OD-11.
- **Rules.** DR-12, 26, 28. **Decisions.** OD-4, OD-5, OD-11.
- **Acceptance.** Same results as SE-8 for the same inputs under an injected clock; per-instrument failures stay isolated; Quasar down produces failures, never empty results.
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

| Decision | Proposal |
|---|---|
| OD-10 time | Integer UTC milliseconds, matching the contract and avoiding conversion. |
| OD-3 result | Closed union of signals (non-empty tuple), no signal, failure (string code). Several signals allowed. |
| OD-14 signal kind | Strategy-owned string kind plus an immutable payload; the engine neither enumerates nor reads it. |
| OD-13 contract | Id and version strings; separate stateless and stateful protocols mirroring DR-26's two forms; an explicit list passed by the composition root. Input declaration waits for SE-5. |
| G-1 (new) | Is a snapshot per instrument, or can it span several? `docs/domain.md` does not say. DR-27 suggests per instrument, which excludes cross-instrument strategies. **Needs your call.** |

### Gate 2 — availability, the main architectural decision (OD-6, OD-7; SE-5, SE-8)

DR-06 currently makes every Quasar-backed evaluation a failure, because no response says when a row became available. Findings:

- Quasar already **stores** the needed facts but does not expose them: `ingested_at_ms` on candles, open interest and funding, and `recorded_at_ms` on conflict records (migrations 001 to 003). Decision Q5 kept them out of the API as diagnostic.
- `conflicted` is a present-tense flag. It cannot say whether the conflict was known at a past `as_of`.
- The API does not reveal whether a row was backfilled.

| Option | Live | Replay | Cost |
|---|---|---|---|
| **A. Expose ingestion time** (additive `/v1` field); available when also closed and `ingested_at_ms ≤ as_of` | Exact | Exact for what Quasar held at `as_of`, and conflicts can be time-scoped | Changes a Quasar decision (Q5, ADR-0002 P-2). Backfilled rows fail in replay, shortening usable history. Collector and engine clocks must be comparable |
| **B. Engine-applied delay per input** | Workable | Modelled: backfilled and revised rows are indistinguishable, so DR-20 and DR-21 are not met as written | No Quasar change, but replay would need those rules amended |
| **C. Engine records what it saw during live scans** | Exact | Exact, only from when recording began | Needs SE-7 and SE-9 first; no history at the start |

**Recommendation: A.** It is the only option that satisfies DR-20 and DR-21 without amending them on existing history. It does require a Quasar contract change approved in that project. If usable replay over backfilled history matters more, that is a deliberate amendment of DR-21 (G-2), not an implementation detail.

**G-2 (new).** Late collection breaks live/replay equality under B. A candle the Collector stored late is a failure live but present in replay, against the "Historical replay" concept in section 3. A resolves it, B cannot.

### Gate 3 — state (before SE-3 and SE-7)

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
| G-3 (new) | Quasar pages are not a snapshot (contract section 3), and a backfill during a replay could make two runs differ. Proposal: a replay reads its data once and evaluates over that frozen copy. This is required by DR-13, not an optimisation. |

G-1 to G-3 are not yet in `docs/domain.md`; if accepted they are added to section 10 as new OD entries, per its "no assumed rules".

## 6. Left to each slice's plan

Module names, type names, stub-server mechanics, fixture format, the SQLite schema and the exact CLI surface.
