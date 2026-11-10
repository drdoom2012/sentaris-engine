# Sentaris Engine — Domain

**Repository:** `sentaris-engine`  
**Status:** Foundation, revision 9 (2026-11-10). Strategy-agnostic: the engine-wide rules (section 5) are established; strategy-specific, state-handling, data-quality and delivery decisions are open (section 10).  
**Scope:** The concepts every strategy shares, the business rules every evaluation must obey, and the decisions still missing. It defines no strategy, signal kind or state machine. Code structure and tooling are in `CLAUDE.md`; market data semantics are in the Quasar Market Data contract (`../quasar-market-data/docs/contracts/api-v1.md`).

This is the **single source of truth for engine-wide business rules**. `CLAUDE.md`, `README.md`, specs, plans and code comments refer to it and do not restate it (section 11). What a particular strategy does is specified separately when that strategy is requested; it must not contradict this document and does not copy it.

## 1. Purpose and boundary

Sentaris Engine is an independent application for **deterministic analysis of cryptocurrency market data**. It hosts independent strategies. Given market data as it was available at one moment, each strategy either produces signals or says why it could not decide.

- Market data comes **exclusively** from the Quasar Market Data REST API. The engine never imports Quasar code, reads its database, or contacts an exchange.
- Strategies are independent of each other and differ in inputs, parameters and signal kinds. The engine fixes none of these (DR-22, DR-23).
- A strategy may keep state between evaluations, as a state machine of its own. The engine carries that state and never interprets it (DR-25).
- The engine has no trading functionality and holds no exchange credentials.

```text
  Quasar Market Data REST API
              |
              v
   +------------------------+
   | Snapshot builder       |   applies the availability rules (section 5.2), once
   +-----------+------------+
               |   evaluation context: snapshot, parameters, as_of (+ previous_state)
               v
   +-----------+  +-----------+
   | Strategy A|  | Strategy B|   independent; each pure: no I/O, no clock, no randomness
   +-----+-----+  +-----+-----+
         |              |
         +------+-------+
                |
                v
      Result: signal(s) | no signal | evaluation failure   (+ next_state)
```

`previous_state` and `next_state` exist only for a strategy that has state (DR-25). The engine loads, passes and persists them as opaque values.

Live scanning and historical replay are the same pipeline with a different `as_of` (section 3).

## 2. Capability status

| Status | Capability |
|---|---|
| Built | Project foundation: layers, import contracts, lint and type checks. Signal payload with its canonical form (OD-14, ADR-0001): construction by exact type with freezing by copy, the canonical encoder, and a strict decoder that accepts only canonical forms (`sentaris_engine.domain.payload`). Time checks: instants and durations are exact `int` milliseconds, a duration is greater than zero, an instant is neither required to be non-negative nor aligned to a timeframe (OD-10; `sentaris_engine.domain.timing`). Strategy parameters: a flat immutable mapping from `str` to `str`, `int`, `Decimal` or `bool`, accepted and rejected as a payload is, with null, sequence and mapping values rejected at construction (OD-13, ADR-0001; `sentaris_engine.domain.parameters`). Market data types: a candle (exact finite `Decimal` numbers, `turnover` null when Quasar sent none, `conflicted` carried and not interpreted), a series of one timeframe strictly ascending by open time, and an immutable snapshot of series strictly ascending by timeframe, with no `as_of` and no instrument identity (DR-11, DR-15, OD-4, OD-7; `sentaris_engine.domain.market`). Result, signal, context and the stateless strategy contract: a signal (a non-empty `str` kind and an immutable payload, equal exactly when kind and canonical payload are), signals (a non-empty tuple in the strategy's order, never sorted), no signal, and an evaluation failure (a non-empty `str` code, no further format), as the closed union of the three outcomes of DR-14; the evaluation context (snapshot, parameters and an exact `int` `as_of`); and the stateless strategy `Protocol` with read-only `id` and `version` and `evaluate(context) -> result`. All are frozen, checked by exact type at construction, and name no signal kind (OD-3, OD-13, OD-14, DR-23, DR-26; `sentaris_engine.domain.evaluation`). |
| Planned (named in the architecture, not built, not scheduled; needs an explicit request) | Strategies; building snapshots from Quasar; live scanning; historical replay. |
| Open (not decided whether wanted, OD-11, OD-12, OD-20) | Persistence of results and of strategy state; a REST endpoint; notification or other delivery; evaluation of replay output (backtest). |
| Excluded by design | Trading and order execution; exchange credentials; any exchange access that bypasses Quasar (DR-18, DR-19). |

Nothing in "Planned" or "Open" may be added without an explicit request. Anything not stated in this document is undecided (section 10) and is not to be decided by implementation.

## 3. Concepts

Only what is established is defined here. Open aspects point to their decision.

| Concept | Definition | Open |
|---|---|---|
| Market data input | A series the engine reads from Quasar (section 6). A strategy uses the inputs it needs; the engine does not fix which. | OD-4, OD-13 |
| `as_of` | The evaluation timestamp: an explicit input to every evaluation. Data not available at `as_of` does not exist for that evaluation. Represented as in section 10 (OD-10). | OD-5 |
| Snapshot | The immutable, point-in-time set of market data built for one `as_of` and one primary instrument (OD-21), with availability already filtered. A strategy cannot see past `as_of`. | OD-4, OD-22 |
| Parameters | The values that configure one strategy's evaluation. They are an explicit input, never read from the environment. The strategy validates them; the engine never interprets them (OD-13). | |
| Evaluation context | The complete input of one strategy evaluation: snapshot, parameters, `as_of` and, for a strategy with state, `previous_state`. | |
| Strategy | A pure transition from an evaluation context to a result and, for a strategy with state, a `next_state` (DR-26). It never fetches data and never knows whether it runs live or in replay. Strategies are independent (DR-22). | OD-13 |
| Signal | An output of one strategy for one evaluation context. Its kind is defined by the strategy, not by the engine (DR-23). Represented as in section 10 (OD-14). | OD-18 |
| Strategy state | An opaque value a strategy returns as `next_state` and receives back as `previous_state`. Its content and meaning belong to the strategy; the engine only carries it (DR-25). Absent for a stateless strategy, and when none has been recorded for the scope. | OD-19, OD-20 |
| State machine | The optional, strategy-defined structure of states, transitions, invalidation and lifecycle rules that gives meaning to its state. The engine does not know it (DR-25). | |
| Evaluation scope | What identifies evaluations that are independent of each other for state: at least strategy identity, strategy version and instrument (DR-27). | OD-17 |
| Signal lifecycle | What happens to a signal across successive evaluations, including expiry and invalidation. Defined entirely by the strategy, through its state if it has any; the engine knows no lifecycle state (DR-25). | |
| Result | The outcome of one evaluation: signal(s), **no signal**, or **evaluation failure**. These are distinct outcomes (DR-14). | OD-3 |
| Evaluation failure | Data was missing, stale, inconsistent, or its availability could not be established; or the strategy's parameters are invalid (OD-13). Carries a machine-readable reason. Never "no signal". | OD-3, OD-8 |
| Strategy execution | Building a snapshot for an `as_of`, loading each strategy's state for its scope, evaluating one or more strategies, persisting the returned state when persistence is enabled, and collecting their results. It lives in the application layer. | OD-5, OD-15, OD-18 |
| Live | Execution at the current moment. | OD-5 |
| Historical replay | Execution at past `as_of` values. Same strategy code and transition (DR-12, DR-26), same availability rules (DR-21), same result and `next_state` for the same inputs as the live evaluation at that `as_of` would have produced. | OD-5, OD-12, OD-17, OD-23, OD-24 |
| Available | Obtainable by the engine at `as_of`: for a candle, closed and published; for other inputs, published at or before `as_of` (section 5.2). | OD-6 |

## 4. Out of scope of this document

Strategy definitions and their signal kinds, parameters and thresholds; a strategy's state machine, with its states, transitions, invalidation and lifecycle rules. Each is specified separately when requested (OD-13).

## 5. Rules

Rule IDs are stable and never reused or renumbered. **Enforcement** uses the statuses in section 9.

### 5.1 Strategies, signals and state

| ID | Rule | Enforcement |
|---|---|---|
| DR-22 | Strategies are independent. A strategy's result depends only on its own evaluation context (section 3); it reads no other strategy's result or state, and one strategy's failure does not change another's result. | PLANNED (unscheduled) |
| DR-23 | The engine defines no signal kind. Engine-level types, rules and checks treat signals generically; every kind, and any relation between kinds, belongs to the strategy that defines it. | PLANNED (unscheduled) |
| DR-25 | A strategy may define a state machine; it is optional. Its states, transitions, invalidation and lifecycle rules belong exclusively to the strategy, and the engine is unaware of them. The engine holds a strategy's state as an opaque value: it never inspects, interprets, validates or branches on its content, and is responsible only for loading it, passing it to the strategy as `previous_state`, and persisting the returned `next_state` when persistence is enabled (OD-11, OD-20). A strategy without a state machine is stateless: it receives no `previous_state`, returns no `next_state`, and needs no special handling. | PLANNED (unscheduled) |
| DR-26 | A strategy's evaluation is one pure, deterministic transition: `(snapshot, parameters, as_of, previous_state) → (result, next_state)`, or `(snapshot, parameters, as_of) → result` for a stateless strategy. Result and `next_state` depend only on these inputs (DR-08 to DR-11); `next_state` carries no wall-clock timestamp, generated id or randomness (DR-09). Live and replay use the same transition (DR-12): the same inputs give the same result and `next_state` in both. | PLANNED (unscheduled) |
| DR-27 | State is isolated by evaluation scope: at least strategy identity, strategy version and instrument, plus every other element that makes two evaluations independent (OD-17). State recorded under one scope is never loaded for, passed to, or overwritten by an evaluation of another scope. | PLANNED (unscheduled) |
| DR-28 | Whenever state is persisted or signals are delivered, state transitions and emitted signals are handled consistently. Within one scope the transitions form a single ordered sequence: a `next_state` is recorded together with the signals of its result, or neither is; no two evaluations consume the same `previous_state` to record different `next_state` values; re-processing an evaluation with the same scope, `as_of` and `previous_state` yields the same result and `next_state` (DR-26) and neither emits its signals again nor advances the state again. A transition is never lost and never applied twice. The mechanism is open (OD-18, OD-19). | PLANNED (unscheduled) |

### 5.2 Availability: only data available at `as_of`

Live scanning and historical replay may use only data that was actually available at `as_of`.

| ID | Rule | Enforcement |
|---|---|---|
| DR-01 | A candle is usable only once closed (`open_time + interval ≤ as_of`) **and** published (close time plus the publication delay). The open time is never the availability time. | PLANNED (unscheduled) |
| DR-02 | The forming candle is never used. | PLANNED (unscheduled) |
| DR-03 | Open interest and funding: use the latest value published at or before `as_of`. Never a later value, and never one stamped before `as_of` but published after it. What "latest" means for funding is open (OD-16). | PLANNED (unscheduled) |
| DR-04 | Funding: only settled rates count. A row is usable only if its settlement instant is at or before `as_of` **and** it was published at or before `as_of` (DR-03). No estimated or predicted rate is an input. | PLANNED (unscheduled) |
| DR-05 | Availability filtering happens once, when the snapshot is built (application/infrastructure). Strategies receive an immutable snapshot and never query data themselves. | PLANNED (unscheduled) |
| DR-06 | If the Quasar API cannot say when a value became available, that is an evaluation failure. Availability is never assumed. Check the Quasar contract before relying on any field's timestamp semantics (OD-6). | PLANNED (unscheduled) |
| DR-07 | Every new data input has a test with data stamped after `as_of` that must be ignored. | NOT_APPLICABLE: review convention, no automated mechanism |
| DR-20 | A value the source revised after `as_of` is never used in place of the value known at `as_of`, for any input. If the source cannot show which value was known at `as_of`, that is an evaluation failure (DR-06), not a reason to use the current value. (Revision handling is open, OD-7.) | PLANNED (unscheduled) |
| DR-21 | Replay applies the same availability rules as live (DR-01 to DR-06, DR-20). Stored history is not assumed to be point-in-time: a row existing for a past `as_of` is not proof that it was available then, and an `as_of` before the source's stored history, or inside a hole in it, is an evaluation failure. A source statement about completeness or freshness holds only for the `as_of` it was computed at; for any other `as_of` the engine judges availability itself (DR-05). | PLANNED (unscheduled) |
| DR-24 | Inputs of different kinds are related only through the instants and intervals their source contract defines, never by equal timestamps. | PLANNED (unscheduled) |

### 5.3 Determinism

Identical inputs, parameters and `as_of` produce identical results, live and in replay.

| ID | Rule | Enforcement |
|---|---|---|
| DR-08 | Time, randomness and I/O are passed in and never read in `domain` or `strategies`. | CONFIGURED, partly: the import-linter contract "domain and strategies import only allowlisted pure standard-library modules" (default deny) rejects imports of modules such as `time`, `random`, `os`; ruff TID251 bans `datetime.now/utcnow/today` and `date.today` outside `infrastructure/`. **Not checked:** calls to builtins that do I/O (`open`, `print`, `input`) and imports that are computed at run time |
| DR-09 | Results carry no wall-clock timestamps or generated ids. Anything identifying a result is derived from the inputs. | PLANNED (unscheduled) |
| DR-10 | Results never depend on the iteration order of unordered data. Sort explicitly. | PLANNED (unscheduled) |
| DR-11 | Prices and volumes use `Decimal` or the exact representation Quasar provides. They are never round-tripped through `float`. | PLANNED (SE-4): the Quasar client does not exist yet. Partly covered: signal payloads reject `float` and non-finite `Decimal` (`tests/domain/test_payload.py::test_rejected_sources_raise_payload_error`) and candles reject `float`, `int`, `str` and non-finite `Decimal` numbers (`tests/domain/test_market.py::test_candle_rejects_non_decimal_and_non_finite_values`) |
| DR-12 | The same strategy code serves live and replay. No mode flags inside a strategy. | PLANNED (unscheduled) |
| DR-13 | Replay is tested by asserting identical output for repeated runs on identical input. | NOT_APPLICABLE: test convention, applies to each strategy's tests |

### 5.4 Data quality: fail closed

Missing, stale or inconsistent data is an explicit evaluation failure, never a silent signal.

| ID | Rule | Enforcement |
|---|---|---|
| DR-14 | A strategy's result type distinguishes "no signal" from "could not evaluate" (a failure with a machine-readable reason). Failure is not modelled as "no signal", `None`, or an exception swallowed upstream. | PLANNED (unscheduled) |
| DR-15 | Candles, prices, volumes, open interest, funding and indicator values are never filled, interpolated, forward-filled, defaulted or fabricated. | PLANNED (unscheduled) |
| DR-16 | Before evaluating, validate: required series present, enough history, no gaps, not stale relative to `as_of`, consistent across series. The thresholds are open (OD-8). | PLANNED (unscheduled) |
| DR-17 | Validation is never weakened to make a test or a signal pass. | NOT_APPLICABLE: review convention, no automated mechanism |

### 5.5 Boundary with Quasar

| ID | Rule | Enforcement |
|---|---|---|
| DR-18 | Quasar is reached only through its REST API. Its code is never imported and its database never read. | CONFIGURED: import-linter contract "Quasar Market Data internals are never imported" (`quasar_market_data` only; it does not stop a read of its database file) |
| DR-19 | No trading functionality and no exchange credentials. | NOT_APPLICABLE: review convention, no automated mechanism |

## 6. Data inputs

The inputs the engine may read. Their meaning belongs to the Quasar contract; this table records only what the rules above depend on, as read on 2026-11-09. If it differs from the contract, the contract wins and this table is corrected. A new input is added here, with a DR-07 test, before any strategy uses it. No other input exists.

| Input | What a row is | Availability | Quasar contract (api-v1.md) |
|---|---|---|---|
| Candles (OHLCV, turnover) | Covers `[open_time, open_time + timeframe)`. Exact decimal text. | DR-01, DR-02 | section 5 |
| Open interest | `time_ms` is the **end** of the period it covers (`[T − period, T)`); it is not the candle's open time. | DR-03 | section 6.5 |
| Funding rate | One **settlement**: an instant, covering no interval. The interval to the next settlement is not in the row, varies by symbol and over time, and rows are not on a grid. The rate is signed; `mark_price` can be absent; `Regular` and `Special` rows can coexist in one hour. | DR-03, DR-04 | section 6.7 |

What this means for the engine, beyond the rules:

- **No ingestion time.** Candle, open interest and funding rows carry no ingestion time (Quasar decision Q5), and the API does not know the publication delay the Collector used. The time a value was published is therefore not given; DR-06 applies until OD-6 is decided.
- **Stored history is not point-in-time.** Quasar stores the first value it received and records later disagreement as a conflict; rows that were backfilled were fetched after the fact (DR-21, OD-7).
- **Quasar's clock-dependent answers describe the present.** Coverage and freshness are computed at the server's clock; `as_of` is not a request parameter (contract section 6.1.1). They say nothing reliable about a past `as_of` (DR-21).
- **Funding has no grid.** The spacing of two funding rows is an observation, not a definition, so the absence of a row cannot be detected from the rows alone (OD-16).
- Indicators computed by Quasar (`GET /v1/indicators`) are not an approved input (OD-9).

## 7. Signals

Established: a signal is produced by one strategy; its kind, parameters, meaning and lifecycle, including expiry and invalidation, are defined by that strategy, through its own state machine if it has one (DR-23, DR-25); an evaluation may instead end in no signal or an evaluation failure (DR-14); anything identifying a signal is derived from the inputs (DR-09).

Established since revision 4: one evaluation may carry several signals (OD-3); a strategy-defined kind and payload are represented as recorded for OD-14 in section 10.

Not decided: what identifies a signal so that a repeated evaluation is recognised (OD-18). None of it may be inferred.

## 8. Strategy execution

Established: execution builds a snapshot per `as_of` (DR-05); for a strategy with state it loads the state of the strategy's scope, passes it as `previous_state` and persists the returned `next_state` when persistence is enabled, without ever interpreting it (DR-25, DR-27); it evaluates strategies on their own evaluation contexts (DR-22) and keeps state and emitted signals consistent (DR-28); it reports results; it is the only place that combines strategies with data access; live and replay differ only in how `as_of` is chosen (DR-12, DR-21, DR-26).

Established since revision 4: strategy identity, versioning, the stateless and stateful contracts, explicit registration and parameters (OD-13, section 10); one primary instrument per evaluation context (OD-21).

Not decided: how strategies declare the inputs they need, and where strategy specifications live (rest of OD-13); whether an evaluation may also receive data of other instruments as market context (OD-22); the exact scope of state and its handling across versions (OD-17); the mechanism that keeps state and signals consistent, and signal identity (OD-18); what happens to state on failure, on a missed or out-of-order evaluation, and when state is lost (OD-19); how state is encoded and stored (OD-20); whether strategies share a snapshot, in what order they run and how a failure in one is reported (OD-15); the evaluation schedule and `as_of` selection (OD-5).

## 9. Enforcement statuses

Adopted from the invariant register of Quasar Market Data (`docs/invariants.md`) so that no rule is described as enforced when it is only written down.

- `ENFORCED`: a check runs in `make check` **and** a named negative test exists that fails when the rule is violated. The evidence cell is `path/to/test.py::test_name`. A passing positive test alone does not qualify. *No rule has this status yet.*
- `CONFIGURED`: a check runs in `make check`, but no committed negative test shows it fails on a violation. *Added for this project: Quasar's three statuses cannot describe a check that exists without a negative test.* On 2026-11-09 each `CONFIGURED` check was tried by hand against a scratch copy with a deliberate violation; what it caught and did not catch is stated in the rule's cell.
- `PLANNED`: not enforced yet. The cell names the task that will enforce it; `unscheduled` means no task names it.
- `NOT_APPLICABLE`: decided to be out of scope as an automated mechanism. The cell gives the reason.

Change a rule's status in the same commit as the check or test that changes it.

## 10. Decisions

### Established direction

- Market data only from the Quasar Market Data REST API.
- The engine hosts multiple independent strategies with different inputs, parameters and signal kinds; it defines no signal kind and no strategy (DR-22, DR-23; given by the user, 2026-11-09).
- A strategy may define its own state machine, optional and wholly the strategy's; the engine loads, passes and persists its state as an opaque value and stays unaware of states and transitions; evaluation is a pure transition from `(snapshot, parameters, as_of, previous_state)` to `(result, next_state)`; state is isolated by evaluation scope; state and signals are handled consistently (DR-25 to DR-28; given by the user, 2026-11-09).
- The evaluation rules DR-01 to DR-28 (section 5).
- The result distinguishes signal, no signal and evaluation failure (DR-14).
- Strategies are pure functions of an evaluation context; availability is filtered when the snapshot is built.
- No trading functionality, no exchange credentials.
- **Time (OD-10).** Every instant, `as_of` included, is an integer count of UTC milliseconds since the Unix epoch; every duration is integer milliseconds. No timezone-bearing or floating-point time type (ADR-0001; given by the user, 2026-11-10).
- **Result shape (part of OD-3).** A result is exactly one of: signals (a non-empty, ordered tuple), no signal, or evaluation failure with a machine-readable string code. One evaluation may carry several signals (ADR-0001; given by the user, 2026-11-10).
- **Signal representation (OD-14).** A strategy-owned string kind plus an immutable payload. The payload is a mapping; a payload value is recursively null, a scalar (string, integer within ±(2^53 − 1), finite `Decimal`, boolean), an immutable ordered sequence of payload values, or an immutable mapping from unique string keys to payload values. No other type is a payload value. Null is a strategy-chosen value, distinct from an absent key, and never stands in for missing market data (DR-14, DR-15). Every payload has exactly one canonical form, a byte string that is injective and type-preserving, keeps each `Decimal`'s sign, coefficient and exponent exactly (DR-11), orders mapping keys by code point and keeps sequence order (DR-10), and is identical for the same payload in every process and `decimal` context (DR-13). Kinds are matched by exact Python type, so subclasses and enums are not payload values; containers are frozen by copy; duplicate keys are rejected. Payloads are equal exactly when their canonical forms are. The accepted Python values, the canonical form, the excluded values and the test vectors are specified normatively in ADR-0001 ("Which Python values are payload values", "Canonical form of a payload"); those sections are the only definition. The engine neither enumerates kinds nor reads payloads (ADR-0001; given by the user, 2026-11-10; nesting added in revision 5, null and the byte format in revision 6, the clarifications and the integer range in revision 8).
- **Strategy contract (part of OD-13).** Identity is `id` and `version`, non-empty strings with no imposed format; a change in behavior is a new version. One contract per form in DR-26, stateless and stateful. Strategies are passed to execution as an explicit list from the composition root, without discovery. Parameters are a flat immutable mapping from string keys to the scalar values of OD-14, without null or nesting; the strategy validates them, invalid parameters are an evaluation failure, and the engine never interprets them (ADR-0001; given by the user, 2026-11-10).
- **One primary instrument per evaluation context (OD-21).** The primary instrument is the instrument the evaluation is for and the instrument of its state scope (DR-27). Its snapshot may hold several inputs and timeframes of that instrument and, until OD-22 is decided, data of no other instrument (ADR-0001; given by the user, 2026-11-10; "primary" named in revision 5).

### Resolve before implementation

Nothing here is to be decided by implementation. Each item says what it blocks. When one is decided, move it to "Established direction", record it as a small ADR in `docs/adr/` if it is architectural, and update the rules it touches.

| ID | Open decision | Blocks |
|---|---|---|
| OD-1 | **REMOVED** (2026-11-09). It asked for the definition of one specific strategy; strategy definitions are outside this document (section 4). The ID is not reused. | |
| OD-2 | **RESOLVED** (2026-11-09, given by the user). It asked who owns signal lifecycle, identity and expiry. Lifecycle, expiry and invalidation belong exclusively to the strategy (DR-25). The engine-level remainder, signal identity and repeated evaluation, is OD-18. The ID is not reused. | |
| OD-3 | **Result model.** *Partly resolved 2026-11-10 (ADR-0001): the shape of the result type and several signals per evaluation.* Still open: the taxonomy of machine-readable failure reasons; what evidence, if any, a result carries. | Data-quality gate, any strategy |
| OD-4 | **Universe.** Which venues, symbols and timeframes the engine evaluates, whether this is global or per strategy, how it learns them (own configuration or Quasar's `GET /v1/instruments`), and the instrument identity it uses. | Snapshot builder, scanning |
| OD-5 | **Evaluation schedule and `as_of`.** How a live `as_of` is chosen (for example aligned to a candle boundary), whether it can differ per strategy, and the step and range of a replay. | Live scanning, replay |
| OD-6 | **Availability time.** Candle, open interest and funding rows carry no ingestion time (Quasar decision Q5) and the API does not know the Collector's publication delay (Quasar contract sections 6.1.4, 6.5.1, 6.7.1, read 2026-11-09). DR-01, DR-03 and DR-06 need a decided derivation of "published" for each input (for example a delay applied by the engine, or a field added to the Quasar contract), and the engine's behavior when it cannot be established. | Snapshot builder, every input |
| OD-7 | **Revised, conflicting and backfilled values.** How the engine treats a value Quasar flags as conflicted (Quasar advises treating it as untrusted), how it detects that a row was backfilled rather than collected live, and how replay satisfies DR-03, DR-20 and DR-21 given that Quasar keeps the first stored value and exposes no ingestion time. | Snapshot builder, replay |
| OD-8 | **Data-quality thresholds.** Minimum history per input, how stale is too stale relative to `as_of`, what counts as a gap, and what "consistent across series" means. | DR-16, any strategy |
| OD-9 | **Indicators.** Whether the engine uses Quasar's indicators or computes its own from candles, and the numeric policy (Decimal context, precision, rounding) for any indicator value. | Any strategy |
| OD-10 | **RESOLVED** (2026-11-10, given by the user, ADR-0001). It asked for the type of `as_of` and of timestamps inside the engine; the answer is in "Established direction". The ID is not reused. | |
| OD-11 | **Delivery.** Whether results are persisted, served over REST or notified, and how. | Anything past a result in memory |
| OD-12 | **Replay output.** What a historical replay produces and how it is judged. Trading is excluded (DR-19), so any performance measure needs its own definition. | Replay tooling |
| OD-13 | **Strategy contract.** *Partly resolved 2026-11-10 (ADR-0001): identity and versioning, the stateless and stateful contracts, registration, parameter representation and validation.* Still open: how a strategy declares its required inputs; where strategy specifications live. | Snapshot builder, the first real strategy |
| OD-14 | **RESOLVED** (2026-11-10, given by the user, ADR-0001; amended in revision 5 to allow nested payloads, in revision 6 to allow null and fix the canonical byte form, and in revision 8 to bound integers and fix which Python values are payload values). It asked how engine-level types carry a strategy-defined signal kind and payload; the answer is in "Established direction". The ID is not reused. | |
| OD-15 | **Multi-strategy execution.** Whether strategies share one snapshot or each gets its own, their execution order (it must not change results, DR-10), concurrency, and how one strategy's failure is reported next to others' results (DR-22). | Strategy execution |
| OD-16 | **Funding selection and completeness.** What "latest" means when settlement intervals vary and `Regular` and `Special` rows coexist; how staleness and completeness of funding are judged without a grid; how a missing `mark_price` is treated. | Any strategy using funding |
| OD-17 | **State scope and versioning.** Which elements beyond strategy identity, version and instrument belong to the evaluation scope (for example venue, timeframe, parameter set, live versus a particular replay run); what happens to recorded state when a strategy's version or parameters change (discarded, migrated by the strategy, or refused); how a replay's state is kept apart from live state (DR-27). | Any stateful strategy, state store |
| OD-18 | **Signal identity and delivery consistency.** What identifies a signal, derived from the inputs (DR-09), so that a repeated evaluation can be recognised; the delivery guarantee; the mechanism that makes recording a `next_state` and emitting its signals consistent (DR-28). | State persistence, delivery |
| OD-19 | **State on failure and continuity.** What state an evaluation failure leaves behind (the previous state kept, or a strategy-supplied `next_state`); how a missed `as_of` or an out-of-order evaluation is handled so no transition is lost or applied twice; how lost or unreadable state is told apart from a first evaluation, given that the engine cannot interpret state (DR-14, DR-28). | Any stateful strategy |
| OD-20 | **State persistence.** Whether and how state is stored (part of OD-11); the encoding of opaque state, its size bound, and that identical state is encoded identically (DR-13); whether a stateful strategy may run without persistence, losing its state at restart; retention and deletion of state. | Any stateful strategy beyond one process |
| OD-21 | **RESOLVED** (2026-11-10, given by the user, ADR-0001; "primary instrument" named in revision 5). Added and decided together; it asked whether one evaluation context covers one instrument or several. The answer is in "Established direction". Data of other instruments is OD-22. The ID is not reused. | |
| OD-22 | **Cross-instrument market context.** Whether an evaluation may receive, besides its primary instrument (OD-21), read-only data of other instruments, and if so: how a strategy declares them (OD-13) and how they relate to the universe (OD-4); whether they are subject to exactly the same snapshot building, availability and validation as the primary instrument (DR-05, DR-21, DR-24, DR-16); whether a missing or failing context series fails the evaluation (DR-14, OD-8); whether the state scope must include them (DR-27, OD-17); how it interacts with multi-strategy execution (OD-15). A strategy that relates instruments (for example a spread) falls under this decision. One possible shape is sketched in ADR-0001; it is not decided. | Any strategy that needs another instrument's data |
| OD-23 | **Live/replay equivalence for late-collected data.** "Historical replay" (section 3) requires the result live would have produced at that `as_of`. A row the source stored after `as_of`, collected late or backfilled, was unavailable live but is present in stored history. Open: whether replay must recognise such rows and treat them as unavailable, which needs a source fact (OD-6, OD-7); or whether replay may differ from live for them, which would amend DR-21 and the "Historical replay" concept rather than be an implementation choice; and how a replay's output states which applies. Decided together with OD-6 and OD-7. Recorded from the roadmap (G-2), 2026-11-10. | Replay |
| OD-24 | **Consistent data within one run.** Quasar pages are not a snapshot (contract section 3): between two requests rows may be added, backfilled rows before the cursor included, and conflicts recorded. Open: how a replay reading data for many `as_of` values, and a snapshot read in several pages, obtain one consistent dataset (for example reading once and evaluating over a frozen copy, or detecting a change and failing); whether that dataset is kept so that a later run can repeat on identical input (DR-13); what a change detected during a run produces (DR-14). Quasar's suggested check against `/v1/coverage` describes the present only (DR-21). Recorded from the roadmap (G-3), 2026-11-10. | Replay; affects any snapshot read in several pages |

## 11. Maintaining this document

Conventions adopted from Quasar Market Data:

- **One authoritative place.** Engine-wide domain rules live here and nowhere else. `CLAUDE.md` holds working instructions and points here; `README.md` holds install and run; Quasar's contract stays authoritative for Quasar's data. If a rule must be mentioned elsewhere, cite its ID (`DR-xx`, `OD-xx`) instead of restating it.
- **Stable IDs.** `DR-xx` for rules, `OD-xx` for open decisions. IDs are never reused or renumbered; a removed rule or decision keeps its ID and is marked removed. A change of wording that keeps the meaning keeps the ID; a change of meaning gets a new ID.
- **No assumed rules.** What is not written here is not decided. A gap is added to section 10, not filled by implementation.
- **Approval.** Established rules and decisions are not changed without explicit approval. Record how and when a decision was approved in its ADR or in the commit that moves it to "Established direction".
- **Same commit.** A change in behavior, a new input or a new check updates this document in the same commit.
- **Specs and plans.** Superpowers specs and plans go in `docs/superpowers/specs/` and `docs/superpowers/plans/` (`YYYY-MM-DD-<topic>…md`, as in Quasar). They link to the IDs here and do not copy rule text. Architectural decisions go in `docs/adr/`, known gaps in `docs/follow-ups.md`; the latter does not exist yet and is created by its first entry.

### Revision history

| Revision | Date | Change |
|---|---|---|
| 1 | 2026-11-09 | First version: rules carried over from `CLAUDE.md`; written around one named strategy and two signal kinds. |
| 2 | 2026-11-09 | Strategy-agnostic. Removed all strategy-specific content; **OD-1 removed**; **OD-2** narrowed to a generic signal lifecycle (its strategy-specific part dropped). **DR-03** (revisions moved to DR-20, "latest" for funding to OD-16), **DR-04** (publication condition added, no predicted rate) and **DR-08** (partial enforcement stated) reworded, meaning unchanged. **OD-6** and **OD-7** expanded (history is not point-in-time). Added **DR-20 to DR-24** and **OD-13 to OD-16**. Capability status split into built, planned, open and excluded (section 2); funding semantics recorded (section 6). |
| 3 | 2026-11-09 | Strategy-specific state machines. Evaluation becomes a pure transition with optional `previous_state` and `next_state`. Added **DR-25 to DR-28** (ownership and opacity of state, pure transition, state isolation, consistency of state and signals) and **OD-17 to OD-20**. **OD-2** resolved: signal lifecycle belongs to the strategy; its engine-level remainder moved to OD-18. Concepts, execution and signals sections updated. **DR-22** reworded to refer to the evaluation context instead of listing its parts, meaning unchanged; **OD-13** extended with whether a strategy has state. All other DR and OD IDs unchanged. |
| 4 | 2026-11-10 | Gate 1 of the roadmap decided by the user (ADR-0001). **OD-10** and **OD-14** resolved; **OD-3** and **OD-13** partly resolved, their remainder kept open; **OD-21** added and resolved (one instrument per evaluation context). "Evaluation failure" now also covers invalid parameters (OD-13). Concepts, signals and execution sections updated. No DR changed. |
| 5 | 2026-11-10 | At the user's request (ADR-0001 amended). **OD-14**: payloads may nest (scalars, sequences, mappings), with a canonical serialization whose properties are fixed and whose byte format is left to the first slice that serializes; equality is by canonical form. **OD-13**: parameters stated as flat, so they keep their previous form. **OD-21**: the single instrument is named the primary instrument, meaning unchanged. **OD-22** added (cross-instrument market context), open. No DR changed; OD-6, OD-7 and OD-19 untouched. |
| 6 | 2026-11-10 | At the user's request (ADR-0001 amended). **OD-14**: null added as a payload value (not a scalar, so parameters are unchanged and now stated as excluding it); the canonical byte form is fixed now, normatively in ADR-0001 with test vectors, replacing "chosen by the first slice that serializes". **OD-13**: parameter wording names the exclusion of null, meaning unchanged. OD-22 stays open. No DR changed. |
| 7 | 2026-11-10 | Roadmap gaps G-2 and G-3 recorded as **OD-23** (live/replay equivalence for late-collected data) and **OD-24** (consistent data within one run), both open. "Historical replay" concept now cites them. No decision taken; no DR changed. |
| 8 | 2026-11-10 | At the user's request (ADR-0001 amended), closing the Gate 1 clarifications of the roadmap. **OD-14**: integers in a payload, and hence in parameters (OD-13), are bounded to ±(2^53 − 1), because signals are to reach a database, a frontend and notifications; kinds are matched by exact Python type (subclasses, enums, `set` and `frozenset` rejected); containers are frozen by copy; duplicate keys are rejected; the `Decimal` text is independent of the `decimal` context. Canonical bytes of every previously valid payload are unchanged, except that integers outside the range are no longer payload values. No DR changed. |
| 9 | 2026-11-10 | Slice SE-1 (stateless evaluation), in progress. Built: the signal payload with its canonical form (OD-14, ADR-0001) and a strict decoder that accepts only canonical forms (ADR-0001, "Canonical form of a payload"), time checks for instants and durations (OD-10), strategy parameters as a flat immutable scalar mapping (OD-13), and the candle, series and snapshot types with duplicate open times and timeframes rejected (DR-11, DR-15), and the signal, result, evaluation context and stateless strategy contract types, none of which names a signal kind (OD-3, OD-13, OD-14, DR-23), section 2. **DR-11** scheduled for SE-4 and noted as partly covered by payload construction and candle construction (section 5). No rule or decision changed. |
