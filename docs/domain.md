# Sentaris Engine — Domain

**Repository:** `sentaris-engine`  
**Status:** Specification for a fresh implementation (2026-11-11). Nothing is built. The engine-wide rules (section 4) and the design decisions already taken (section 6) are established; the decisions still missing are listed in section 7.  
**Scope:** What the engine does, the concepts every strategy shares, the business rules every evaluation must obey, and the decisions still missing. It defines no strategy, signal kind or state machine. Market data semantics are in the Quasar Market Data contract (`../quasar-market-data/docs/contracts/api-v1.md`).

This is the **single source of truth for engine-wide business rules**. Other documents and code comments refer to it by ID and do not restate it (section 8). What a particular strategy does is specified separately when that strategy is requested; it must not contradict this document and does not copy it.

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
   | Snapshot builder       |   applies the availability rules (section 4.2), once
   +-----------+------------+
               |   evaluation context: snapshot, parameters, as_of
               |   (+ previous_state beside it, for a strategy with state)
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

## 2. Capabilities

| Status | Capability |
|---|---|
| To build | The evaluation types (time, snapshot, parameters, signal, result, evaluation context, strategy contract; section 6); evaluation of one strategy and execution of several; reading market data from Quasar; building snapshots under the availability rules; the data-quality gate; state handling for stateful strategies; live scanning; historical replay; strategies, each on its own request. |
| Open (not decided whether wanted; OD-11, OD-12, OD-20) | Persistence of results and of strategy state; a REST endpoint; notification or other delivery; evaluation of replay output (backtest). |
| Excluded by design | Trading and order execution; exchange credentials; any exchange access that bypasses Quasar (DR-18, DR-19). |

Nothing in "Open" may be added without an explicit request. Anything not stated in this document is undecided (section 7) and is not to be decided by implementation.

## 3. Concepts

Only what is established is defined here. Open aspects point to their decision.

| Concept | Definition | Open |
|---|---|---|
| Market data input | A series the engine reads from Quasar (section 5). A strategy uses the inputs it needs; the engine does not fix which. | OD-4, OD-13 |
| `as_of` | The evaluation timestamp: an explicit input to every evaluation. Data not available at `as_of` does not exist for that evaluation. An integer of UTC milliseconds (section 6.1). | OD-5 |
| Snapshot | The immutable, point-in-time set of market data built for one `as_of` and one primary instrument (section 6.6), with availability already filtered, holding what the evaluated strategy declared (section 6.9). A strategy cannot see past `as_of`. | OD-4, OD-22 |
| Parameters | The values that configure one strategy's evaluation. They are an explicit input, never read from the environment. The strategy validates them; the engine never interprets them (section 6.5). | |
| Evaluation context | Snapshot, parameters and `as_of`: the complete input of a stateless evaluation. It contains neither state nor the instrument key (section 6.8). A strategy with state receives its `previous_state` beside the context, as a separate input (section 6.4). | |
| Strategy | A pure transition from an evaluation context to a result or, for a strategy with state, from an evaluation context and a `previous_state` to a result and a `next_state` (DR-26). It never fetches data and never knows whether it runs live or in replay. Strategies are independent (DR-22). | OD-13 |
| Signal | An output of one strategy for one evaluation context. Its kind is defined by the strategy, not by the engine (DR-23). Represented as in section 6.3. | OD-18 |
| Strategy state | An opaque value a strategy returns as `next_state` and receives back as `previous_state`. Its content and meaning belong to the strategy; the engine only carries it (DR-25). Absent for a stateless strategy, and when none has been recorded for the scope. | OD-19, OD-20 |
| State machine | The optional, strategy-defined structure of states, transitions, invalidation and lifecycle rules that gives meaning to its state. The engine does not know it (DR-25). | |
| Evaluation scope | What identifies evaluations that are independent of each other for state: at least strategy identity, strategy version and instrument (DR-27). | OD-17 |
| Signal lifecycle | What happens to a signal across successive evaluations, including expiry and invalidation. Defined entirely by the strategy, through its state if it has any; the engine knows no lifecycle state (DR-25). | |
| Result | The outcome of one evaluation: signal(s), **no signal**, or **evaluation failure**. These are distinct outcomes (DR-14, section 6.2). | OD-3 |
| Evaluation failure | Data was missing, stale, inconsistent, or its availability could not be established; or the strategy's parameters are invalid (section 6.5). Carries a machine-readable reason. Never "no signal". | OD-3, OD-8 |
| Strategy execution | One run for one `as_of` over an explicit list of (strategy, primary instrument) pairs: building one snapshot per instrument, loading each pair's state for its scope, evaluating each pair, persisting the returned state when persistence is enabled, and collecting one report entry per pair (section 6.7). | OD-5, OD-18 |
| Live | Execution at the current moment. | OD-5 |
| Historical replay | Execution at past `as_of` values. Same strategy code and transition (DR-12, DR-26), same availability rules (DR-21), same result and `next_state` for the same inputs as the live evaluation at that `as_of` would have produced, with the exceptions of section 6.10 (a conflict or a readability violation recorded after `as_of`). | OD-5, OD-12, OD-17, OD-24 |
| Available | Obtainable by the engine at `as_of`: for a candle, closed and published; for other inputs, published at or before `as_of` (section 4.2). "Published" is derived as in section 6.10. | OD-6 |

**Out of scope of this document:** strategy definitions and their signal kinds, parameters and thresholds; a strategy's state machine, with its states, transitions, invalidation and lifecycle rules. Each is specified separately when requested (OD-13).

## 4. Rules

Rule IDs are stable and never reused or renumbered. Every rule is unimplemented; how each is checked is recorded when the code that enforces it is written (section 8).

### 4.1 Strategies, signals and state

| ID | Rule |
|---|---|
| DR-22 | Strategies are independent. A strategy's result depends only on its own evaluation context (section 3) and, for a strategy with state, its own `previous_state` (DR-26); it reads no other strategy's result or state, and one strategy's failure does not change another's result. |
| DR-23 | The engine defines no signal kind. Engine-level types, rules and checks treat signals generically; every kind, and any relation between kinds, belongs to the strategy that defines it. |
| DR-25 | A strategy may define a state machine; it is optional. Its states, transitions, invalidation and lifecycle rules belong exclusively to the strategy, and the engine is unaware of them. The engine holds a strategy's state as an opaque value: it never inspects, interprets, validates or branches on its content, and is responsible only for loading it, passing it to the strategy as `previous_state`, and persisting the returned `next_state` when persistence is enabled (OD-11, OD-20). A strategy without a state machine is stateless: it receives no `previous_state`, returns no `next_state`, and needs no special handling. |
| DR-26 | A strategy's evaluation is one pure, deterministic transition: `(snapshot, parameters, as_of, previous_state) → (result, next_state)`, or `(snapshot, parameters, as_of) → result` for a stateless strategy. Result and `next_state` depend only on these inputs (DR-08 to DR-11); `next_state` carries no wall-clock timestamp, generated id or randomness (DR-09). Live and replay use the same transition (DR-12): the same inputs give the same result and `next_state` in both. |
| DR-27 | State is isolated by evaluation scope: at least strategy identity, strategy version and instrument, plus every other element that makes two evaluations independent (OD-17). State recorded under one scope is never loaded for, passed to, or overwritten by an evaluation of another scope. |
| DR-28 | Evaluating and committing are separate. **Evaluating** is the pure transition of DR-26: it records no state and delivers no signal, so it may be repeated freely and always gives the same result and `next_state`. **Committing** is recording a `next_state` and emitting the signals of its result. Whenever state is persisted or signals are delivered, committing is consistent. Within one scope the committed transitions form a single ordered sequence: a `next_state` is recorded together with the signals of its result, or neither is; no two evaluations consume the same `previous_state` to record different `next_state` values; re-processing an evaluation with the same scope, `as_of` and `previous_state` neither emits its signals again nor advances the state again. A transition is never lost and never applied twice. The mechanism is open (OD-18, OD-19). |

DR-28 is a requirement on any commit mechanism that is built. It does not decide that state is persisted or that signals are delivered (OD-11, OD-20), which delivery guarantee holds, or how "never applied twice" is achieved (OD-18).

### 4.2 Availability: only data available at `as_of`

Live scanning and historical replay may use only data that was actually available at `as_of`.

| ID | Rule |
|---|---|
| DR-01 | A candle is usable only once closed (`open_time + interval ≤ as_of`) **and** published (close time plus the publication delay). The open time is never the availability time. |
| DR-02 | The forming candle is never used. |
| DR-03 | Open interest and funding: use the latest value published at or before `as_of`. Never a later value, and never one stamped before `as_of` but published after it. What "latest" means for funding is open (OD-16). |
| DR-04 | Funding: only settled rates count. A row is usable only if its settlement instant is at or before `as_of` **and** it was published at or before `as_of` (DR-03). No estimated or predicted rate is an input. |
| DR-05 | Availability filtering happens once, when the snapshot is built. Strategies receive an immutable snapshot and never query data themselves. |
| DR-06 | If the Quasar API cannot say when a value became available, that is an evaluation failure. Availability is never assumed. Check the Quasar contract before relying on any field's timestamp semantics (OD-6). |
| DR-07 | Every new data input has a test with data stamped after `as_of` that must be ignored. |
| DR-20 | A value the source revised after `as_of` is never used in place of the value known at `as_of`, for any input. If the source cannot show which value was known at `as_of`, that is an evaluation failure (DR-06), not a reason to use the current value. (Revision handling: section 6.10.) |
| DR-21 | Replay applies the same availability rules as live (DR-01 to DR-06, DR-20). Stored history is not assumed to be point-in-time: a row existing for a past `as_of` is not proof that it was available then, and an `as_of` before the source's stored history, or inside a hole in it, is an evaluation failure. A source statement about completeness or freshness holds only for the `as_of` it was computed at; for any other `as_of` the engine judges availability itself (DR-05). |
| DR-24 | Inputs of different kinds are related only through the instants and intervals their source contract defines, never by equal timestamps. |

### 4.3 Determinism

Identical inputs, parameters and `as_of` produce identical results, live and in replay.

| ID | Rule |
|---|---|
| DR-08 | Time, randomness and I/O are passed in and never read by domain code or by strategies. |
| DR-09 | Results carry no wall-clock timestamps or generated ids. Anything identifying a result is derived from the inputs. |
| DR-10 | Results never depend on the iteration order of unordered data. Sort explicitly. |
| DR-11 | Prices and volumes use `Decimal` or the exact representation Quasar provides. They are never round-tripped through `float`. |
| DR-12 | The same strategy code serves live and replay. No mode flags inside a strategy. |
| DR-13 | Replay is tested by asserting identical output for repeated runs on identical input. |

### 4.4 Data quality: fail closed

Missing, stale or inconsistent data is an explicit evaluation failure, never a silent signal.

| ID | Rule |
|---|---|
| DR-14 | A strategy's result type distinguishes "no signal" from "could not evaluate" (a failure with a machine-readable reason). Failure is not modelled as "no signal", `None`, or an exception swallowed upstream. |
| DR-15 | Candles, prices, volumes, open interest, funding and indicator values are never filled, interpolated, forward-filled, defaulted or fabricated. |
| DR-16 | Before evaluating, validate: required series present, enough history, no gaps, not stale relative to `as_of`, consistent across series. The thresholds, and what "consistent" means, are open (OD-8). |
| DR-17 | Validation is never weakened to make a test or a signal pass. |

### 4.5 Boundary with Quasar

| ID | Rule |
|---|---|
| DR-18 | Quasar is reached only through its REST API. Its code is never imported and its database never read. |
| DR-19 | No trading functionality and no exchange credentials. |

## 5. Data inputs

The inputs the engine may read. Their meaning belongs to the Quasar contract; this table records only what the rules above depend on, as read on 2026-11-10. If it differs from the contract, the contract wins and this table is corrected. A new input is added here, with a DR-07 test, before any strategy uses it. No other input exists.

| Input | What a row is | Availability | Quasar contract (api-v1.md) |
|---|---|---|---|
| Candles (OHLCV, turnover) | Covers `[open_time, open_time + timeframe)`. Exact decimal text. `turnover` can be null. | DR-01, DR-02 | section 5 |
| Open interest | `time_ms` is the **end** of the period it covers (`[T − period, T)`); it is not the candle's open time. | DR-03 | section 6.5 |
| Funding rate | One **settlement**: an instant, covering no interval. The interval to the next settlement is not in the row, varies by symbol and over time, and rows are not on a grid. The rate is signed; `mark_price` can be absent; `Regular` and `Special` rows can coexist in one hour. | DR-03, DR-04 | section 6.7 |

What this means for the engine, beyond the rules:

- **No ingestion time.** Candle, open interest and funding rows carry no ingestion time in the API (Quasar decision Q5), although Quasar records it, and the API does not know the publication delay the Collector used. Section 6.10 makes the exposed ingestion time the basis of availability; until Quasar exposes it for an input, DR-06 applies to that input.
- **Stored history is not point-in-time.** Quasar stores the first value it received and records later disagreement as a conflict (`conflicted`); rows that were backfilled were fetched after the fact (DR-21, section 6.10).
- **Quasar's clock-dependent answers describe the present.** Coverage and freshness are computed at the server's clock; `as_of` is not a request parameter (contract section 6.1.1). They say nothing reliable about a past `as_of` (DR-21).
- **Funding has no grid.** The spacing of two funding rows is an observation, not a definition, so the absence of a row cannot be detected from the rows alone (OD-16).
- **Pages are not a snapshot.** Quasar pages are separate reads at separate moments (contract section 3). Reading a window successfully is not a statement of consistency, availability or completeness (DR-06, DR-21, OD-24).
- Indicators computed by Quasar (`GET /v1/indicators`) are not an approved input (OD-9).

**Consequence for trust.** OD-6 and OD-7 are decided in section 6.10 except for the remainder of OD-6. Until Quasar exposes the ingestion time for an input and the remainder of OD-6 is decided, the engine cannot establish when a value of that input became available, so under DR-06 no evaluation over real Quasar data that reads that input, live or replay, may produce a signal. Until OD-24 is decided as well, a historical replay must not be described as reproducing what a live evaluation would have produced: the equivalence in the "Historical replay" concept (section 3) is a requirement on the finished engine, not a property anything has today. None of these is to be settled by implementation.

## 6. Decided design

Decisions already taken, each given by the user on the date shown. They are not reopened by implementation. The label in brackets is the decision's stable ID.

### 6.1 Time (OD-10, 2026-11-10; amended 2026-11-13)

Every instant, `as_of` included, is an integer count of UTC milliseconds since the Unix epoch; every duration, such as a timeframe, is integer milliseconds and greater than zero. No timezone-bearing or floating-point time type. This matches the Quasar contract exactly.

An instant lies in `0 … 2^53 − 1` and a duration in `1 … 2^53 − 1`; any other value is refused.

### 6.2 Result shape (part of OD-3, 2026-11-10)

A result is exactly one of:

- **signals**: a non-empty tuple of signals, in the strategy's order, never sorted by the engine;
- **no signal**;
- **evaluation failure**, carrying a machine-readable string code.

One evaluation may carry several signals. The taxonomy of failure codes and whether a result carries evidence are open (OD-3).

### 6.3 Signal representation (OD-14, 2026-11-10)

A signal is a strategy-owned string `kind` plus an immutable payload. The engine neither enumerates kinds nor reads payloads (DR-23).

- The payload is a mapping. A payload value is recursively one of: **null**; a **scalar** (string, integer within ±(2^53 − 1), finite `Decimal`, boolean); an immutable ordered **sequence** of payload values; an immutable **mapping** from unique string keys to payload values. No other type is a payload value.
- Null is a value the strategy chooses to emit, distinct from an absent key. It never stands in for missing market data; that is an evaluation failure (DR-14, DR-15).
- Every payload has exactly one **canonical form**, a byte string. Two payloads are equal exactly when their canonical forms are equal, and two signals are equal exactly when their kind and canonical payload are.
- The accepted values and the canonical form are specified normatively in Appendix A.

Integers are bounded so that every consumer, a JavaScript frontend included, reads them exactly: signals are expected to reach a database, a frontend and notifications (delivery itself is OD-11). No depth or size bound on a payload is decided; whether one is needed is OD-25.

### 6.4 Strategy contract (part of OD-13, 2026-11-10; amended 2026-11-13)

- A strategy is identified by `id` and `version`, both non-empty strings with no imposed format. A change in behavior is a new version.
- There are two contracts, one per form in DR-26: stateless (`context → result`) and stateful (`context, previous_state → result, next_state`). The evaluation context is the same type in both and holds no state; `previous_state` is a separate input and `next_state` a separate output.
- In the stateful contract, absent state is a dedicated value, distinct from every state value, null included. `previous_state` is absent when no state has been recorded for the scope; a strategy may return absent as its `next_state` to supply no state. What an absent `next_state` leaves behind is open (OD-19).
- Strategies are passed to execution as an explicit list from the composition root. There is no discovery.

How a strategy declares the inputs it needs is decided in section 6.9. Where strategy specifications live is open (OD-13).

### 6.5 Parameters (part of OD-13, 2026-11-10; amended 2026-11-12)

Parameters are a **flat** immutable mapping from string keys to the scalar values of section 6.3 (string, integer, `Decimal`, boolean): no null, no sequence, no nested mapping. Scalars are accepted and rejected exactly as payload scalars are (Appendix A). Each strategy validates its own parameters; invalid parameters are an evaluation failure, not an exception. The engine never interprets them.

Malformed parameters, that is, parameters outside the shape of this section, give an evaluation failure for that pair alone, produced by execution without calling the strategy; the other pairs of the execution are unaffected (section 6.7). Its code is open (OD-3).

### 6.6 One primary instrument per evaluation context (OD-21, 2026-11-10)

One evaluation context has exactly one **primary instrument**: the instrument it is evaluated for and the instrument of its state scope (DR-27). Its snapshot may hold several inputs and timeframes of that instrument and, until OD-22 is decided, data of no other instrument. A strategy that needs another instrument's data (a reference index, a spread) cannot be expressed until then. The instrument is named by its key (section 6.8); what the key consists of is open (OD-4).

### 6.7 Execution over several strategies and instruments (OD-15 and OD-26, 2026-11-11; amended 2026-11-13)

OD-15 was decided for several strategies; OD-26 extended it to several primary instruments on the same day and amended its snapshot, order, duplicate, raise and report rules. This section is the result.

- **Unit of work.** One execution evaluates an explicit list of pairs of a strategy and a primary instrument, each pair with its own evaluation context. The list comes from the composition root, as the strategies do (section 6.4). The engine forms no pairs itself: it does not run every strategy on every instrument. The same strategy may be paired with several instruments. The list may be empty; the report then has no entries.
- **One `as_of`.** All pairs of one execution have the same `as_of`. A different `as_of` is a different execution.
- **Snapshot.** Each primary instrument has its own immutable data of that `as_of`, read once for the union of what its pairs declare (sections 6.6, 6.9). Pairs of the same instrument share that data; pairs of different instruments share nothing. Each pair's snapshot is the part of its instrument's data that its own declaration names, and nothing more (section 6.9). Execution neither changes nor copies a snapshot.
- **Order.** Pairs run in ascending `(instrument, id, version)` order, each element compared as a string by Unicode code point. The report lists them in that order, so the order of the input changes neither the results nor their order (DR-10).
- **Refused input.** A duplicate `(instrument, id, version)`, or an instrument key, `id` or `version` that is not a non-empty string, is refused for the whole execution before anything runs. A strategy's identity is read once per execution; a strategy whose identity cannot be read, or does not consist of an `id` and a `version` as section 6.4 requires, is refused for the whole execution before anything runs.
- **Concurrency.** None. Pairs are evaluated one after another.
- **A strategy that raises.** An exception raised by a strategy, or a result that is not one of the three outcomes of section 6.2, is caught for that one pair alone and reported as its own entry; the same strategy on another instrument is still evaluated. That entry is a separate result type, distinct from the three outcomes of DR-14: it is never "no signal" and never an evaluation failure. It carries the instrument key, the strategy's `id` and `version`, and the exception's type name, never its message, because a message may carry data of the strategy's context. For a result that is not one of the three outcomes, the type name is that of the returned value, and the value itself is never reported. Only ordinary exceptions are caught, that is, instances of the language's ordinary exception class (in Python, `Exception`); every other exception, an interrupt or exit request included, propagates. A type name is prefixed by the name of the module the type records, when it records the name of one as a non-empty string, so two types of the same name in different modules are told apart; no module name is invented. The entry states whether the strategy raised or returned a value that is not one of the three outcomes.
- **Report.** There is one entry for every pair, the failed one included. Every entry carries the instrument key and the strategy's `id` and `version`, and is the same whether the pair runs alone or with others (DR-22).

Because a duplicate `(instrument, id, version)` is refused, no two evaluations of one execution belong to the same minimum evaluation scope (DR-27).

Left open: what the pairs of an instrument report when its data cannot be read (OD-3); state handling (OD-17 to OD-20).

### 6.8 Instrument key (part of OD-4, 2026-11-11)

- A primary instrument is named by its **instrument key**: a non-empty string that the engine treats as opaque. The engine only compares keys for equality and orders them by Unicode code point (section 6.7). What a key consists of (venue, symbol, contract type) and which instruments exist are open (OD-4).
- The key travels **beside** the evaluation context, not in it. A strategy does not receive it, so the inputs of DR-26 are unchanged and a strategy cannot branch on the instrument. A difference between instruments reaches a strategy only through its parameters or its snapshot.
- Strategies do not declare which instruments they apply to; pairing is the composition root's (section 6.7).

### 6.9 Input declaration and shared reading (part of OD-13, 2026-11-13; amended 2026-11-14)

- **Declaration.** A strategy declares the inputs it needs. The declaration is a function of the strategy's `id` and `version` and of the pair's parameters (section 6.5), and of nothing else: the same strategy, version and parameters always give the same declaration, or the same evaluation failure (DR-08). A strategy declares no instrument (section 6.8) and, until OD-22 is decided, no data of another instrument.
- **Need.** A declaration is a set of needs. A need names one input of section 5 of the primary instrument; the series of that input, where the instrument has several (for candles, the timeframe); and a **lookback**, a duration (section 6.1) of history ending at `as_of`. Which rows a lookback holds at its boundaries is open (OD-13).
- **One lookback per series.** A declaration names each series at most once; one that names a series twice is malformed. A declaration with no need is valid.
- **Declaration failure.** Instead of a declaration, a strategy may return an evaluation failure with a code it chooses, for example for parameters it judges invalid (section 6.5). That failure is then the pair's result: its strategy is not evaluated, its pair adds nothing to the shared reading, and the other pairs are unaffected (DR-22).
- **Shared reading.** For one execution and one primary instrument, the data read is the union of the needs of every pair of that instrument. A series that several pairs need is read once, over the longest lookback any of them declares.
- **Narrowed view.** Each pair's snapshot holds only the series its own declaration names, each over its own lookback, taken from the data read for its instrument. A pair never sees a series or history it did not declare, so its evaluation context, and with it its result, is the same whether it runs alone or with others (DR-22, section 6.7).
- **Sufficiency per pair.** Whether a pair's data is sufficient is judged against that pair's own declaration. A problem in a series, or in history, that only other pairs declared does not change its result (DR-22). Who produces the resulting failure and its code are open (OD-3, OD-8).

### 6.10 Availability time, conflicts and late-collected rows (part of OD-6, OD-7 and OD-23, 2026-11-14)

This section gives DR-01, DR-03, DR-06, DR-20 and DR-21 a derivation of "published" for every input of section 5. It applies to live and replay alike (DR-21).

- **Source fact.** Availability rests on a row's **ingestion time**: the instant from which, by Quasar's contract, Quasar serves the row at the latest, so that a read started at or after it sees the row. Quasar records a time for every candle, open interest and funding row but does not expose it (Quasar decision Q5), and the time it records today is taken before the row is stored, so it does not have this meaning. The engine needs Quasar's contract to expose an instant with this meaning per row, as an additive field, for each input it reads. This is a dependency on the Quasar contract, not something the engine derives.
- **Availability instant.** A row's availability instant is the later of two instants: its **completion instant** plus the engine's **publication delay** for that input, and its ingestion time. The completion instant is the one the Quasar contract defines for the row (DR-24): for a candle the end of its interval (`open_time + timeframe`, DR-01); for open interest the end of its period; for funding its settlement instant. A row is available at `as_of` exactly when its availability instant is at or before `as_of`. The value of the publication delay, and whether it differs by input, are open (OD-6).
- **No source fact, no availability.** A row whose ingestion time the source does not give is not available, and an evaluation that needs it is an evaluation failure (DR-06). Until Quasar exposes the ingestion time for an input, every evaluation that reads that input therefore fails; no delay applied by the engine replaces the source fact.
- **Late-collected and backfilled rows.** No separate detection exists: a row stored after `as_of`, whether collected late or backfilled, has an ingestion time after `as_of` and is therefore not available at that `as_of`, live or in replay. Where the row is needed, its absence is a hole (DR-21) and an evaluation failure, never filled (DR-15). This decides OD-23: replay recognises such rows and treats them as unavailable.
- **Consequence for history.** Replay can use only rows that were stored before the `as_of` it evaluates. Rows stored before Quasar exposed a valid ingestion time carry, by Quasar's contract, the instant of that change, and backfilled rows carry the instant of the backfill; neither makes earlier history available. Usable history therefore grows only from live collection after that change.
- **Value known at `as_of`.** Quasar keeps the first value it stored and never overwrites it. An available row's value is therefore the value known at `as_of` (DR-20).
- **Conflicted rows.** A row that Quasar flags as conflicted is untrusted. If an available row of a series the pair's own declaration names, within its lookback, is flagged as conflicted, the pair's result is an evaluation failure (DR-14). A conflicted row in a series or history that only other pairs declared does not change the pair's result (section 6.9). Its code is open (OD-3).
- **Rows with a violated readability bound.** Quasar can detect, only after the row became visible, that a row became readable later than its ingestion time states. A row Quasar flags this way is untrusted and is treated exactly as a conflicted row: if it is available and in a series the pair's own declaration names, within its lookback, the pair's result is an evaluation failure (DR-14); otherwise it does not change the pair's result (section 6.9). Its code is open (OD-3).
- **Accepted differences between live and replay.** Quasar does not expose when a conflict or a readability violation was recorded. One recorded after `as_of` was not visible to a live evaluation at that `as_of`, but is visible to a later replay of it, which then fails where live did not. These are the only accepted exceptions to the equivalence in "Historical replay" (section 3); each can be removed only if Quasar exposes when it was recorded.

Left open: the publication delay (above) and how a difference between the Collector's clock, which stamps the ingestion time, and the instants of `as_of` is handled (OD-6); one consistent dataset within one run (OD-24).

## 7. Open decisions

Nothing here is to be decided by implementation. Each item says what it blocks. When one is decided, it moves to section 6 and the rules it touches are updated.

IDs not listed are closed and never reused: OD-1 (removed: it asked for one specific strategy), OD-2 (signal lifecycle belongs to the strategy, DR-25; its remainder is OD-18), and OD-7, OD-10, OD-14, OD-15, OD-21, OD-23 and OD-26 (section 6).

| ID | Open decision | Blocks |
|---|---|---|
| OD-3 | **Result model (remainder).** The taxonomy of machine-readable failure reasons, including the code for malformed parameters (section 6.5); what evidence, if any, a result carries; who produces an evaluation failure for a data problem, given that validation happens before evaluating (DR-16) while a result is what a strategy returns (DR-14): the engine without calling the strategy, the strategy, or both; what the pairs of an instrument report when its data cannot be read, and that this leaves the other instruments of the execution untouched (section 6.7); what a pair reports when the data its own declaration names is insufficient (section 6.9). | Data-quality gate, any strategy, execution of a pair with malformed parameters |
| OD-4 | **Universe (remainder).** *Decided: the instrument key is an opaque non-empty string, and pairs of strategy and instrument are given explicitly (sections 6.7, 6.8).* Still open: which venues, symbols and timeframes the engine evaluates, how it learns them (own configuration or Quasar's `GET /v1/instruments`), what an instrument key consists of and how it maps to a Quasar series. | Snapshot builder, scanning |
| OD-5 | **Evaluation schedule and `as_of`.** How a live `as_of` is chosen (for example aligned to a candle boundary), and the step and range of a replay. One execution has one `as_of` for all its pairs (section 6.7), so strategies or instruments on different rhythms run in different executions; how those are scheduled, and what happens when an execution, which is sequential, is not finished before the next `as_of`, is open. | Live scanning, replay |
| OD-6 | **Availability time (remainder).** *Decided: availability rests on the ingestion time exposed by Quasar, bounded below by the completion instant plus a publication delay; without the source fact a row is not available (section 6.10).* Still open: the value of the engine's publication delay and whether it differs by input (the API does not know the Collector's delay, Quasar contract section 6.1.4); how a difference between the Collector's clock, which stamps the ingestion time, and the instants of `as_of` is handled. | Snapshot builder, every input |
| OD-8 | **Data-quality thresholds.** Minimum history per input, how stale is too stale relative to `as_of`, what counts as a gap, and what "consistent across series" means. | DR-16, any strategy |
| OD-9 | **Indicators.** Whether the engine uses Quasar's indicators or computes its own from candles, and the numeric policy (Decimal context, precision, rounding) for any indicator value. | Any strategy |
| OD-11 | **Delivery.** Whether results are persisted, served over REST or notified, and how. | Anything past a result in memory |
| OD-12 | **Replay output.** What a historical replay produces and how it is judged, including whether it marks a failure that live would not have had because a conflict or a readability violation was recorded after `as_of` (section 6.10). Trading is excluded (DR-19), so any performance measure needs its own definition. | Replay tooling |
| OD-13 | **Strategy contract (remainder).** *Decided: how a strategy declares its inputs, and how the data of an instrument is read once and narrowed for each pair (section 6.9).* Still open: where strategy specifications live; which rows a lookback holds at its boundaries, given that a candle covers an interval and other inputs are instants (DR-01, DR-03, DR-24, OD-6); what a pair reports when its strategy raises while forming a declaration, or returns neither a declaration nor an evaluation failure, and that this leaves the other pairs untouched (OD-3, section 6.7). | Snapshot builder (lookback boundaries), the first real strategy |
| OD-16 | **Funding selection and completeness.** What "latest" means when settlement intervals vary and `Regular` and `Special` rows coexist; how staleness and completeness of funding are judged without a grid; how a missing `mark_price` is treated. | Any strategy using funding |
| OD-17 | **State scope and versioning.** Which elements beyond strategy identity, version and instrument belong to the evaluation scope (for example venue, timeframe, parameter set, live versus a particular replay run); what happens to recorded state when a strategy's version or parameters change (discarded, migrated by the strategy, or refused); how a replay's state is kept apart from live state (DR-27). If the scope gains an element beyond strategy identity, version and instrument, the duplicate rule of section 6.7 is re-examined with it, so that one execution still never holds two evaluations of one scope. | Any stateful strategy, state store |
| OD-18 | **Signal identity and delivery consistency.** What identifies a signal, derived from the inputs (DR-09), so that a repeated evaluation can be recognised; the delivery guarantee; the mechanism that makes recording a `next_state` and emitting its signals consistent (DR-28). | State persistence, delivery |
| OD-19 | **State on failure and continuity.** What state an evaluation failure leaves behind (the previous state kept, or a strategy-supplied `next_state`); what an absent `next_state` (section 6.4) leaves behind; what state a strategy that raises leaves behind (section 6.7); how a missed `as_of` or an out-of-order evaluation is handled so no transition is lost or applied twice; how lost or unreadable state is told apart from a first evaluation, given that the engine cannot interpret state (DR-14, DR-28). | Any stateful strategy |
| OD-20 | **State persistence.** Whether and how state is stored (part of OD-11); the encoding of opaque state, its size bound, and that identical state is encoded identically (DR-13); whether a stateful strategy may run without persistence, losing its state at restart; retention and deletion of state. | Any stateful strategy beyond one process |
| OD-22 | **Cross-instrument market context.** Whether an evaluation may receive, besides its primary instrument (section 6.6), read-only data of other instruments, and if so: how a strategy declares them (OD-13) and how they relate to the universe (OD-4); whether they are subject to exactly the same snapshot building, availability and validation as the primary instrument (DR-05, DR-16, DR-21, DR-24); whether a missing or failing context series fails the evaluation (DR-14, OD-8); whether the state scope must include them (DR-27, OD-17); how it interacts with multi-strategy execution (section 6.7). A strategy that relates instruments (for example a spread) falls under this decision. | Any strategy that needs another instrument's data |
| OD-24 | **Consistent data within one run.** Quasar pages are not a snapshot (contract section 3): between two requests rows may be added, backfilled rows before the cursor included, and conflicts recorded. Open: how a replay reading data for many `as_of` values, and a snapshot read in several pages, obtain one consistent dataset (for example reading once and evaluating over a frozen copy, or detecting a change and failing); whether that dataset is kept so that a later run can repeat on identical input (DR-13); what a change detected during a run produces (DR-14). Quasar's suggested check against `/v1/coverage` describes the present only (DR-21). | Replay; affects any snapshot read in several pages |
| OD-25 | **Payload depth and size bounds.** A payload may nest without a depth or size bound (section 6.3). Open: whether a bound is needed at all, and if so on what (nesting depth, number of entries, canonical-form bytes) and what exceeding it produces. A bound would be set by a real consumer's limit (storage, OD-20; delivery, OD-11), never chosen arbitrarily. | Delivery, persistence of signals |
| OD-27 | **Need for stateful strategies.** DR-25 allows a strategy to keep state and section 6.4 defines the stateful contract, but no strategy that needs state is known. A strategy whose output is a function of the market data available at `as_of` can be evaluated without state over a bounded window: a phase that depends on the path of the data can be recomputed from the last point at which it is unambiguous, such as a reset condition or an expiry after a bounded number of candles; a window without such a point would be an evaluation failure (DR-14). State that only replaces such a recomputation adds the questions of OD-17 to OD-20 and can make a result depend on when evaluation began, not on the data. State appears justified only for information the market data does not hold, for example what a live evaluation actually saw or emitted (OD-6, OD-7, OD-11). Open: whether the stateful contract is kept, and which concrete strategy justifies it. Decided before OD-17, OD-19 and OD-20. | State handling in execution, state persistence |

## 8. Maintaining this document

- **One authoritative place.** Engine-wide domain rules live here and nowhere else. If a rule must be mentioned elsewhere, cite its ID (`DR-xx`, `OD-xx`) instead of restating it. Quasar's contract stays authoritative for Quasar's data.
- **Stable IDs.** `DR-xx` for rules, `OD-xx` for decisions. IDs are never reused or renumbered. A change of wording that keeps the meaning keeps the ID; a change of meaning gets a new ID.
- **No assumed rules.** What is not written here is not decided. A gap is added to section 7, not filled by implementation.
- **Approval.** Established rules and decisions are not changed without explicit approval.
- **Describes behavior, not code.** This document says what the engine does. Module names, function signatures, error class names and test names belong to the code.
- **Enforcement is claimed only with evidence.** A rule is called enforced only when an automated check runs and a named negative test fails on a violation. Until such a test exists the rule is unenforced, however carefully the code was written.

## Appendix A. Payload values and canonical form (normative)

This appendix is the only definition of what a payload value is and of its canonical form (section 6.3). It is written for Python.

### A.1 Which Python values are payload values

Kinds are matched by exact type; a subclass of an accepted type is not that kind and is rejected.

| Kind | Accepted at construction | Notes |
|---|---|---|
| null | `None` | Not a scalar, so not a parameter value and not a signal `kind`. |
| boolean | exactly `bool` | A boolean is never an integer. |
| integer | exactly `int`, from −(2^53 − 1) to 2^53 − 1 inclusive | A larger or exact quantity is a `Decimal`. |
| string | exactly `str`, without a surrogate code point (U+D800 to U+DFFF) | |
| `Decimal` | exactly `decimal.Decimal`, finite | |
| sequence | exactly `tuple` or `list` | |
| mapping | exactly `dict`, or the engine's own immutable mapping type | Keys are exactly `str`. |

Rejected, among others: `float`; non-finite `Decimal` (NaN, sNaN, Infinity); an integer outside the range; `bytes`; every `Enum`, `IntEnum` and `(str, Enum)` mixins included; subclasses of `str`, `int` or `Decimal`; `set`, `frozenset`, generators, iterators and every other collection; non-string mapping keys; strategy-defined classes. A strategy that holds an enum passes its `.value`.

**Freezing by copy.** Construction copies every accepted container, recursively, into an immutable form owned by the payload. A `list` or `dict` given to construction is accepted, and changing it afterwards does not change the payload. Nothing mutable is reachable from a constructed payload.

**Duplicate keys.** Any construction given the same key twice, for example a mapping built from key-value pairs, is rejected; no occurrence wins.

**Equality.** In Python `True == 1` and `Decimal("1.0") == Decimal("1.00")` hold, so payload equality uses the canonical form, never Python equality of raw values.

### A.2 Canonical form

The canonical form is a UTF-8 byte string, without byte-order mark, without any whitespace outside strings and without a trailing newline. It is valid JSON (RFC 8259), but it is defined here, not by any JSON library. Each value is encoded by its kind:

| Kind | Encoding |
|---|---|
| null | `null` |
| boolean | `true` or `false` |
| integer | Decimal digits with no leading zero and no `+`; `-` before a negative value; zero is `0`. |
| string | `"`, the characters, `"`. Exactly these are escaped: `"` as `\"`, `\` as `\\`, U+0008 `\b`, U+0009 `\t`, U+000A `\n`, U+000C `\f`, U+000D `\r`, and every other code point U+0000 to U+001F as `\u` plus four **lowercase** hex digits. Every other code point, U+007F and non-ASCII included, appears literally as UTF-8. No Unicode normalization is applied. |
| `Decimal` | `{"$decimal":"` + text + `"}`, where text is the *to-scientific-string* conversion of the General Decimal Arithmetic Specification, with an uppercase `E`. The text is a function of the value's sign, coefficient digits and exponent alone and never depends on the `decimal` context; under the default context it equals Python's `str(Decimal)`. It keeps sign, coefficient and exponent exactly, so `1.0`, `1.00` and `1E+1` differ, and so do `0` and `-0`. |
| sequence | `[`, the encoded elements in their given order separated by `,`, `]`. Empty: `[]`. |
| mapping | `{"$map":{` + entries + `}}`. Each entry is the key encoded as a string, `:`, the encoded value; entries are separated by `,` and ordered by the keys' Unicode code points, compared element by element, a proper prefix first. Empty: `{"$map":{}}`. |

A payload's canonical form is the encoding of its top-level mapping, so it always starts with `{"$map":{`.

**Why the tags.** Every JSON object in the canonical form is either a one-key tag, `$decimal` or `$map`, or the entries object directly inside a `$map` tag. A `Decimal`, a string and a mapping can therefore never encode alike, whatever keys a strategy uses, and no key is reserved. A `Decimal` is text, never a JSON number, so no consumer can read it as a binary float (DR-11).

**Required properties.** The encoding is injective and type-preserving (`"1"`, `1`, `true`, `{"$decimal":"1"}` and `null` are five values). A payload can be reconstructed exactly from its form. The same payload gives the same bytes regardless of how it was built, in which process, under which `decimal` context or on which platform (DR-10, DR-13). A decoder accepts only bytes that are the canonical form of some payload and rejects anything else, an integer outside the range included.

### A.3 Test vectors

Each line is a payload in Python notation and its exact canonical form. The `Decimal` vectors give the same bytes under any `decimal` context, `capitals = 0` included.

| Payload | Canonical form |
|---|---|
| `{}` | `{"$map":{}}` |
| `{"b": 1, "a": True}` | `{"$map":{"a":true,"b":1}}` |
| `{"p": Decimal("64210.50"), "q": Decimal("-0"), "r": Decimal("1E+2"), "s": Decimal("0.0000001")}` | `{"$map":{"p":{"$decimal":"64210.50"},"q":{"$decimal":"-0"},"r":{"$decimal":"1E+2"},"s":{"$decimal":"1E-7"}}}` |
| `{"x": None, "y": [], "z": ["1", 1, None, {}]}` | `{"$map":{"x":null,"y":[],"z":["1",1,null,{"$map":{}}]}}` |
| `{"$map": "k", "é": "a\"b\\c\n\x01"}` | `{"$map":{"$map":"k","é":"a\"b\\c\n\u0001"}}` |
| `{"Z": 0, "a": -5, "ab": 2, "aa": 3}` | `{"$map":{"Z":0,"a":-5,"aa":3,"ab":2}}` |
| `{"max": 9007199254740991, "min": -9007199254740991}` | `{"$map":{"max":9007199254740991,"min":-9007199254740991}}` |
| `{"d": Decimal("-1.50E-12"), "t": (True, False)}` | `{"$map":{"d":{"$decimal":"-1.50E-12"},"t":[true,false]}}` |

**Rejected at construction:** `{"n": 9007199254740992}`, `{"n": -9007199254740992}`, `{"n": 1.5}`, `{"n": Decimal("NaN")}`, `{"s": {1, 2}}`, `{"e": IntEnum member}`, `{"e": (str, Enum) member}`, `{1: "a"}`, a mapping built from `[("a", 1), ("a", 2)]`.
