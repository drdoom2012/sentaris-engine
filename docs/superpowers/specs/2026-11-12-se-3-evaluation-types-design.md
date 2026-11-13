# SE-3 — Evaluation types: design

**Slice:** SE-3 (`docs/roadmap.md`, Phase A)  
**Status:** Revision 5, approved by the user together with section 13 (2026-11-12). Revision 5 records U9 and gives section 13 as exact before/after text (plan review). Revision 4 applies the user's corrections of 2026-11-12: malformed input raises only `EvaluationTypeError` (section 5, N15) and the candle boundary at `MAX_TIME_MS` (section 6, N8). Revision 3 records U8 and fixes the re-review (approved with changes: 1 HIGH and 1 MEDIUM answered by U8, 3 LOW fixed). Revision 1 was reviewed by Opus (`slice-reviewer`: not approved, 2 CRITICAL needing user decisions, 1 HIGH, 3 MEDIUM, 6 LOW); the user decided U5 to U7, and every other finding is addressed in this revision. Section 13 holds the document changes that follow from U5 and U8; they need the user's approval.  
**Domain references:** sections 3, 5, 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 6.8; DR-01, DR-02, DR-04, DR-10, DR-11, DR-14, DR-15, DR-26; OD-3, OD-6, OD-7, OD-8, OD-13, OD-16, OD-17, OD-18, OD-22 (none decided here; see sections 11 and 13)

Decisions marked **[user Un]** were given by the user in the SE-3 conversation (section 12). Everything marked "my call" is an implementation choice the builder may keep or improve without changing behavior. Names of modules, classes and functions are indicative; the behavior is what is specified.

## 1. Goal

The types an evaluation is made of: time (instants and durations), the instrument key, parameters, signal, the three-outcome result, the snapshot with the row types of the three inputs of section 5, and the evaluation context. These are types only: construction validates and freezes, and nothing else happens. Out of scope: the strategy contract (SE-4); execution, including the report entry for a strategy that raises and the conversion of parameter errors into failures (SE-5); reading Quasar (SE-6); availability filtering and snapshot building (SE-7b and later); and data-quality judgement (SE-10).

## 2. Why this shape

| Choice | Derivation |
|---|---|
| Instants and durations are plain `int`, checked by validators | Section 6.1 fixes integer milliseconds. A wrapper class adds nothing, and every arithmetic step would need a conversion (my call). |
| Instant range `0 … 2^53 − 1`; duration range `1 … 2^53 − 1` | **[user U4, U6]** |
| The instrument key is validated, but neither the snapshot nor the context carries it | Section 6.8. |
| Parameters reuse SE-2's scalar predicate and canonical form | Section 6.5 accepts and rejects scalars exactly as payload scalars. |
| Parameters are a strict type that refuses malformed input; the orchestration layer turns that refusal into a per-pair evaluation failure | **[user U5]**; section 6.5 (invalid parameters are an evaluation failure, not an exception); section 6.7 (each pair has its own evaluation context, so parameters belong to one pair). The conversion and its failure code are not part of SE-3 (section 13). |
| The snapshot holds its own `as_of` and rejects rows stamped after it | **[user U1]**; section 3 ("Snapshot": built for one `as_of`). |
| Rows carry Quasar's `conflicted` flag | **[user U2]**. How the flag is treated stays OD-7. |
| A failure code and a signal kind are each a non-empty exact `str` without surrogates | **[user U3]**. The taxonomy stays OD-3. |
| Rows hold `Decimal`, not Quasar's text | DR-11 allows either. My call: one representation keeps the types simple. The type is exactly `Decimal`, and the value is finite. |
| The context's `as_of` must equal the snapshot's | Section 3: a snapshot is built for one `as_of`. Section 6.7: one execution has one `as_of`. |
| The outcome types are final | Section 6.7: execution must recognise "a result that is not one of the three outcomes". With no subclasses, that check is an exact-type check (my call). |

## 3. Scope

1. Modules in `sentaris_engine.domain`. My call on the split is `timing`, `instrument`, `parameters`, `signal`, `result`, `snapshot` and `context`; the plan may merge some of them.
2. One construction error class, `EvaluationTypeError` (my call), a subclass of `ValueError` distinct from `PayloadError`. Every SE-3 type raises it, `Parameters` included: a `PayloadError` raised inside `Parameters` construction is re-raised as `EvaluationTypeError`, chained with `from`. Tests assert the class only, never the message.
3. The surrogate check of SE-2 (`_has_surrogate` in `domain/payload.py`) is reused. My call: expose it under a public name in `payload.py`, which is a small change to SE-2's module. Copying it privately is also acceptable.
4. Tests, as listed in section 8.
5. `CLAUDE.md` "Current state" says that SE-3 exists.
6. The document edits of section 13 (domain sections 6.5 and 7, roadmap), only with the user's approval of this specification.

## 4. Dependencies

SE-2 is merged on `main` at `c7a732f` and `make check` passes. SE-3 has no gate. All modules are pure domain code. They import only `sentaris_engine.domain` and pinned pure-stdlib modules (expected: `dataclasses`, `decimal`, `types`, `typing`, `collections.abc`). No architecture list is widened and no dependency is added.

## 5. Interfaces and contracts

These rules apply to every type below:

- **Exact types.** A field declared as `int`, `str`, `bool`, `Decimal`, `tuple` or `dict` must hold exactly that type. `bool` is not accepted as an `int`. Subclass instances and `Enum` members are rejected. `float` is rejected in every field (DR-11).
- **Immutable.** Every type is frozen. No field can be reassigned, and there is no `__dict__`. Every container is copied at construction into a `tuple` or into an immutable mapping the type builds itself, so mutating the source afterwards changes nothing.
- **Final.** No SE-3 type can be subclassed. My call: `__init_subclass__` raises `TypeError`, and the classes are also marked `typing.final`.
- **Strings without surrogates** use SE-2's rule (scope item 3).
- **Errors.** Every malformed input to an SE-3 constructor or validator raises `EvaluationTypeError`, deterministically and never any other exception type: no built-in exception (`TypeError`, `KeyError`, `IndexError`, `AttributeError`, `ValueError` other than `EvaluationTypeError`, `PayloadError`) escapes for invalid input. Types and shapes are checked explicitly before any operation that could raise on them (hashing, unpacking, comparison, addition, `len`, iteration); a `PayloadError` from SE-2 is re-raised as `EvaluationTypeError`, chained (scope item 2). This covers malformed pair structures, unhashable keys, invalid nested containers and unexpected input types at every position (N15). Defining a subclass of an SE-3 type is not an input and keeps raising `TypeError` (Final).

### 5.1 Time (section 6.1)

- `MAX_TIME_MS = 2**53 - 1`.
- `check_instant(value) -> int`: accepts an exact `int` in `0 … MAX_TIME_MS` **[U4]** and returns it.
- `check_duration(value) -> int`: accepts an exact `int` in `1 … MAX_TIME_MS` **[U6]** and returns it.
- `Instant = int` and `Duration = int` are type aliases for annotations only.

### 5.2 Instrument key (section 6.8)

`check_instrument_key(value) -> str` accepts any non-empty exact `str` and nothing else. It imposes no format and no surrogate rule, because section 6.8 states only "non-empty string" and anything more would be a new rule. Execution (SE-5) and the builder (SE-7b) use it; no SE-3 type holds a key.

### 5.3 Parameters (section 6.5, U5)

- `Parameters(source)` accepts as `source` either an exact `dict` or exact `list`/`tuple` of 2-tuples. Any other source, a `FrozenMapping` included, is rejected (my call: one path for raw configuration). A list or tuple of pairs goes through `FrozenMapping`'s own pair path, so a duplicate key is rejected the same way. Keys follow the payload key rules. Every value must satisfy `is_payload_scalar`, so `None`, a sequence, a mapping and every non-scalar are rejected. `Parameters({})` is valid, because the domain does not forbid empty parameters.
- Read access goes through the `Mapping[str, scalar]` interface and iterates in code-point key order.
- Equality and hash are by canonical form, so two `Parameters` with the same entries are equal. A `Parameters` never equals a `dict` or a `FrozenMapping`. This equality is representational only. It does not prejudge whether a parameter set is part of the state scope, or how such sets would be compared (OD-17).
- `Parameters` is not a payload value. It cannot be put into a payload as it is.
- The engine never reads a parameter value (section 6.5). Whether the values mean anything valid is the strategy's to judge (SE-4).
- A refusal here is not an evaluation failure and does not decide which code a failure carries. Wherever a pair's `Parameters` is constructed, a refusal becomes that pair's evaluation failure without touching other pairs **[U5]**. Where that happens and which code it carries are fixed by SE-5b (section 13), not by SE-3.

### 5.4 Signal (section 6.3)

- `Signal(kind, payload)` takes a `kind` that is a non-empty exact `str` without surrogates **[U3]**, and a `payload` that is exactly a `FrozenMapping`. My call: there is no implicit conversion from a `dict`.
- Two signals are equal when they have the same `kind` and equal payloads, payload equality being by canonical form (SE-2). The hash is consistent with this equality.

### 5.5 Result (section 6.2, DR-14)

There are exactly three outcome types. None of them is `None` and none is an exception.

- **`Signals(signals)`.** `signals` is an exact `tuple` of one or more exact `Signal` values. They are kept in the given order and never sorted. An empty tuple, a `list`, or any element that is not a `Signal` is rejected. Equal signals within one tuple are kept as given; there is no rule about them **[U7]**, and signal identity stays OD-18.
- **`NoSignal()`.** It has no fields, and all instances are equal. My call: it does not have to be a singleton.
- **`EvaluationFailure(code)`.** `code` is a non-empty exact `str` without surrogates **[U3]**. There is no evidence field (OD-3).
- **`Result`** is the type alias `Signals | NoSignal | EvaluationFailure`.

An outcome never equals an outcome of another type, nor `None`. Since the types are final, "one of the three outcomes" (section 6.7) means `type(r)` is one of these three classes. The separate entry for a strategy that raises is not a `Result`; it belongs to SE-5.

### 5.6 Rows (section 5; Quasar contract sections 1, 5.2, 6.5.1, 6.7.1)

Every decimal field holds an exact finite `Decimal`. A field marked non-negative rejects a negative sign, and `Decimal("-0")` counts as negative. For `funding_rate`, which is signed, `Decimal("-0")` is also rejected. This mirrors contract section 1 and 6.7.1, where `-0` is never sent, and fails closed (my call). Field names follow the engine's style rather than Quasar's JSON (my call). No relation between fields is checked, such as `low ≤ high`, because what "consistent" means is OD-8.

| Row | Fields |
|---|---|
| `Candle` | `open_time` (instant); `open`, `high`, `low`, `close`, `volume` (non-negative); `turnover` (non-negative or `None`); `conflicted` (`bool`) **[U2]**. The timeframe is not a field; it is the key of the series (5.7). |
| `OpenInterest` | `time` (instant: the **end** of the period, contract 6.5.1); `open_interest`, `open_interest_value` (non-negative); `conflicted` (`bool`). |
| `FundingRate` | `funding_time` (instant: the settlement); `rate_type` (exact `str`, either `"Regular"` or `"Special"` as the contract lists; my call: no `Enum`); `funding_rate` (signed, never `-0`); `mark_price` (non-negative or `None`); `conflicted` (`bool`). |

A `None` in `turnover` or `mark_price` carries the source's own null. It is never a default and never stands in for a missing row (DR-15). How a missing `mark_price` is treated is OD-16.

**Equality of rows.** Rows compare field by field with Python equality, so `Decimal("1.0") == Decimal("1.00")`, and they are hashable. My call: this is representational only. No domain rule depends on it, and later slices that compare outputs compare results (5.5), not rows.

### 5.7 Snapshot (sections 3, 6.6; DR-05)

`Snapshot(as_of, candles, open_interest, funding)` has these fields:

- `as_of`: an instant.
- `candles`: an exact `dict` from timeframe (a valid duration) to a series, which is an exact `tuple` of exact `Candle`.
- `open_interest`: an exact `dict` from period (a valid duration) to an exact `tuple` of exact `OpenInterest`.
- `funding`: an exact `tuple` of exact `FundingRate`, or `None`.

The snapshot exposes `candles` and `open_interest` as read-only mappings. My call: a `MappingProxyType` over a private `dict` built in ascending key order. Whatever the insertion order of the source, they iterate in ascending key order (DR-10).

**Equality of snapshot and context.** Both compare by identity and hash by identity (my call: `eq=False`). Execution shares one snapshot object between the pairs of an instrument (section 6.7), so identity is the relation it needs. Structural equality is not defined.

**Absent versus empty** (my call, representation only). A timeframe or period that is not a key, and `funding = None`, mean the input is not in the snapshot. An empty tuple means the input is in the snapshot and has no rows. The type judges neither case: whether an input is required, and whether there is enough history, are OD-13 and OD-8 (SE-10). The snapshot carries no coverage or verification evidence, so an empty funding tuple says nothing about whether settlements occurred (section 10).

**Order and uniqueness** (DR-10). Candles must be strictly ascending by `open_time` and open interest strictly ascending by `time`. Funding must be strictly ascending by `(funding_time, rate_type)`, comparing `rate_type` by code point, so two rows with equal `funding_time` and different `rate_type` are allowed (contract 6.7.1). A series that is out of order or holds a duplicate is rejected, never sorted. There is no gap or grid check (OD-8, OD-16).

**Nothing stamped after `as_of`** **[U1].** Each of these is a necessary condition only. None is a statement that a row was available, so DR-06 and OD-6 are untouched.

- Candle: `open_time + timeframe ≤ as_of` (the closed part of DR-01; DR-02).
- Open interest: `time ≤ as_of`.
- Funding: `funding_time ≤ as_of` (the settled part of DR-04).

A row that violates its condition makes the whole snapshot fail to construct; it is never dropped silently. Filtering belongs to the builder (DR-05).

The snapshot holds **no instrument key** (section 6.8). That it holds data of one instrument only (section 6.6) is the builder's job. The type cannot check it, because rows carry no instrument.

### 5.8 Evaluation context (section 3, DR-26)

`EvaluationContext(snapshot, parameters, as_of)` takes an exact `Snapshot`, an exact `Parameters` and an instant `as_of`. It rejects an `as_of` that differs from `snapshot.as_of` (section 2). It carries no state, no instrument key and no mode flag (DR-12).

## 6. Expected behavior

- Every value valid under section 5 constructs and is immutable. Every input that section 5 does not allow raises `EvaluationTypeError`.
- `Signals((s1, s2))` keeps the order `s1, s2`. Two `Signals` holding the same signals in a different order are not equal. `Signals((s, s))` constructs.
- `NoSignal()` and `EvaluationFailure("x")` never equal each other, `None`, or a `Signals`.
- Boundaries at `as_of`:
  - a snapshot with a candle that closes exactly at `as_of` constructs; the same candle one millisecond later is rejected;
  - open interest with `time = as_of` constructs, and `time = as_of + 1` is rejected;
  - funding with `funding_time = as_of` constructs, and `funding_time = as_of + 1` is rejected.
- A snapshot built from `{300000: …, 60000: …}` iterates `60000` first.
- Candle boundary at `MAX_TIME_MS`: with `as_of = MAX_TIME_MS`, a candle with `open_time + timeframe = MAX_TIME_MS` constructs; a candle with `open_time + timeframe = MAX_TIME_MS + 1` (for example `open_time = MAX_TIME_MS` with `timeframe = 1`, or `open_time = 1` with `timeframe = MAX_TIME_MS`) is rejected, because it is not closed by any valid `as_of` (U1). The sum is computed in exact Python integers; no overflow, wrap or clamp. No separate rule is added: the rejection follows from `open_time + timeframe ≤ as_of ≤ MAX_TIME_MS`.

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC-1 | The time validators accept exactly the ranges of 5.1 (N1). |
| AC-2 | The instrument key validator accepts every non-empty exact `str` and nothing else (N2). |
| AC-3 | `Parameters` accepts exactly flat scalar mappings, the empty one included, and its equality is by canonical form (N3). |
| AC-4 | `Signal` and the three outcomes validate as 5.4 and 5.5, and the DR-14 distinctions hold (N4, N5). |
| AC-5 | Rows validate every field as 5.6 (N6). |
| AC-6 | The snapshot rejects an invalid shape (N11), an unordered or duplicate series (N7) and every row stamped after `as_of`, exactly at the boundary (N8). Its mappings iterate in ascending key order (N13). |
| AC-7 | The context rejects an invalid field (N12) and an `as_of` that differs from the snapshot's (N9). |
| AC-8 | No mutable object is reachable through the public interface of any type, mutating the source has no effect, and no type can be subclassed (N10, N14). |
| AC-10 | Every malformed input raises exactly `EvaluationTypeError`, never a built-in exception (N15); the candle boundary at `MAX_TIME_MS` holds (N8). |
| AC-9 | `make check` passes, and the new modules fall under the SE-1 purity checks without any list being widened. |

## 8. Negative tests

Names are indicative; the plan fixes them. Rejection tests assert the exception class only.

| # | Rule | Test | Fails when |
|---|---|---|---|
| N1 | Section 6.1, U4, U6 | `test_invalid_instant_is_refused` with `-1`, `2**53`, `True`, `1.0`, `Decimal(1)`, `"1"`, `None`, an `int` subclass instance and an `IntEnum` member; `test_invalid_duration_is_refused` with `0`, `-1`, `2**53` and the same type cases. Positive companions at `0`, `1` and `2**53 - 1`. | any is accepted |
| N2 | Section 6.8 | `test_invalid_instrument_key_is_refused` with `""`, `None`, `b"x"`, a `str` subclass instance and `1`. Positive companion: a key with a surrogate and one with spaces are accepted. | any is refused or accepted wrongly |
| N3 | Section 6.5, U5 | `test_invalid_parameters_are_refused`: values `None`, a `list`, a `dict` and a `FrozenMapping`; `float`; `Decimal` NaN; `2**53`; a non-`str` key; a duplicate key from pairs; a source of a shape that is not accepted (`None`, a `set`, a scalar, a `FrozenMapping`). The error raised is exactly `EvaluationTypeError`. `test_parameters_equality_is_canonical`: `{"a": True}` ≠ `{"a": 1}`, and `Parameters({})` ≠ `{}`. | any is accepted, a different error class escapes, or Python equality decides |
| N4 | DR-14, section 6.2 | `test_signals_outcome_requires_signals` with an empty tuple, a `list`, a `None` element and a `dict` element. `test_failure_requires_code` with `""`, `None`, a non-`str` and a surrogate. `test_outcomes_are_distinct`: no two outcome types compare equal, and none equals `None`. | an empty `Signals` or a failure without a code is accepted, or two outcomes compare equal |
| N5 | Section 6.3, U3 | `test_invalid_signal_is_refused`: kind `""`, `None`, a non-`str` or a surrogate; payload a `dict` or `None` | any is accepted |
| N6 | DR-11, section 5 | `test_invalid_row_field_is_refused`, parametrised over every field of the three rows: `float`, NaN, Infinity, a negative value where non-negative is required, `-0` (also for `funding_rate`), `str` text, `None` where it is not allowed, an `int` for a `Decimal`, an unknown `rate_type`, and a non-`bool` `conflicted` (`0`, `1`) | any is accepted |
| N7 | DR-10 | `test_unordered_or_duplicate_series_is_refused` for each of the three series, plus two funding cases: equal `funding_time` with equal `rate_type`, and different `rate_type` in descending order | accepted, or sorted silently |
| N8 | DR-01 (closed part), DR-02, DR-04 (settled part), U1 | `test_row_after_as_of_is_refused`: a forming candle (`open_time + timeframe = as_of + 1`), open interest with `time = as_of + 1`, and funding with `funding_time = as_of + 1`, each placed in a series of otherwise valid rows. Positive companion at equality. Boundary at `MAX_TIME_MS` (section 6): `as_of = MAX_TIME_MS` with `open_time + timeframe = MAX_TIME_MS` accepted; `open_time = MAX_TIME_MS, timeframe = 1` and `open_time = 1, timeframe = MAX_TIME_MS` rejected, and the error is exactly `EvaluationTypeError`. | a row after `as_of` is accepted or dropped |
| N9 | Sections 3, 6.7 | `test_context_as_of_must_match_snapshot` | accepted |
| N10 | Immutability | `test_types_are_immutable`: assignment to every field fails; mutating the source `dict`, or a list that went into it, after construction changes nothing; container fields are a `tuple` or a read-only mapping | assignment succeeds, or a change to the source shows |
| N11 | Section 5.7 | `test_invalid_snapshot_shape_is_refused`: an invalid `as_of`; a mapping key `0`, `-1`, `True` or `"5m"`; a source that is not exactly a `dict` (a `MappingProxyType`, a list of pairs); a series given as a `list`; a row of the wrong type in a series (an `OpenInterest` in `candles`); `funding` given as a `list` or a `dict` | any is accepted |
| N12 | Section 5.8 | `test_invalid_context_field_is_refused`: `parameters` given as a `dict` or `FrozenMapping`; `snapshot` that is not a `Snapshot`; an invalid `as_of` | any is accepted |
| N13 | DR-10 | `test_snapshot_mappings_iterate_in_key_order`: sources with descending and shuffled insertion order | the iteration order follows insertion |
| N14 | Section 5 (final), section 6.7 | `test_types_cannot_be_subclassed`, for every SE-3 class | a subclass can be defined |
| N15 | Section 5 (Errors) | `test_malformed_input_raises_only_evaluation_type_error`, parametrised over every constructor and validator of SE-3, asserting `type(exc) is EvaluationTypeError` (not a subclass check that would let `PayloadError` pass): **malformed pair structures** for `Parameters` (`[("a",)]`, `[("a", 1, 2)]`, `[["a", 1]]`, `["a"]`, `[("a", 1), "b"]`, `[None]`); **unhashable keys** (`[([1], 1)]`, `[({}, 1)]` as parameter pairs; a `list` or `dict` as a key position wherever pairs are accepted); **invalid nested containers** (a parameter value that is a `list`, `tuple`, `dict`, `set`, `FrozenMapping` or a cyclic `list`; a series that is a `tuple` holding a `tuple`, a `dict`, a `list` or `None` instead of a row; a `candles` value that is a `dict` of series; a `Signals` tuple holding a `tuple` of signals); **unexpected input types** in every field and argument (`None`, `object()`, `float`, `bytes`, `set`, a generator, a `str` where a number is expected and the reverse, an `int` subclass, a `str` subclass, a `Decimal` subclass, an `Enum` member). Only the exception class is asserted. | any case raises another exception class, or none |

## 9. Enforced guarantees and known limitations

After this slice, the tests above enforce:

- the ranges of section 6.1 (N1);
- key validation under section 6.8 (N2);
- the parameter shape of section 6.5 (N3);
- the DR-14 distinction in the result type (N4);
- the signal shape of section 6.3 (N5);
- DR-11 for row fields (N6);
- DR-10 for the order of series and of snapshot mappings (N7, N13);
- the "nothing stamped after `as_of`" parts of DR-01, DR-02 and DR-04 inside a snapshot (N8);
- that no SE-3 type can be subclassed (N14);
- that malformed input raises only `EvaluationTypeError` (N15), over the cases listed; that no other input lets a built-in exception escape rests on the explicit checks of section 5 and on review.

These remain convention or review only:

- **Availability.** N8 shows a necessary condition only. DR-01's publication part, DR-03, DR-04's publication part, DR-05, DR-06, DR-07 and DR-20 belong to the builder slices; SE-3 claims none of them as enforced.
- **Section 6.5, the evaluation-failure part.** SE-3 only refuses malformed parameters. Turning that refusal into a per-pair failure is SE-5's job (U5, section 13).
- **One instrument per snapshot** (section 6.6). The type cannot check it.
- **Reachability through private attributes**, as in SE-2 section 9. Likewise, calling `__init__` again on an existing dataclass instance (a row, a signal, an outcome, a snapshot, a context) re-runs construction with validation and replaces its fields; only `Parameters` refuses a second `__init__`. Domain and strategy code never does this; it is not detected.
- **DR-15.** The types fill nothing. That no caller fills data is for the builder and SE-10 to ensure.

## 10. Exclusions

- The strategy contract and identity (SE-4).
- Report entries, the raise entry, and the conversion of a parameter refusal into a failure (SE-5).
- Quasar parsing (SE-6).
- Input declaration and snapshot forming (SE-7a, OD-13).
- Availability filtering (SE-7b to SE-9, OD-6, OD-7).
- Data-quality checks and the taxonomy of failure codes (SE-10, OD-3, OD-8).
- Indicators (OD-9), cross-instrument data (OD-22) and state (SE-14).
- Coverage, verification and availability evidence. These are deliberately absent from the snapshot, and later gated slices may add fields for them (SE-9, SE-10; OD-8, OD-16).
- No change to `docs/domain.md` or `docs/roadmap.md` beyond section 13, and none at all without the user's approval.

## 11. Open questions

None, apart from the approval of section 13.

## 12. Decisions by the user (2026-11-12)

- **U1.** The snapshot type carries its `as_of` and rejects rows stamped after it (5.7): unclosed candles, open interest with `time > as_of`, and funding with `funding_time > as_of`. This is a necessary condition, not availability, and OD-6 is untouched.
- **U2.** Rows carry Quasar's `conflicted` flag as a `bool`. Its treatment stays OD-7.
- **U3.** A failure code and a signal kind are each a non-empty exact `str` without surrogate code points, with no other format. The taxonomy stays OD-3.
- **U4.** Instants are integers in `0 … 2^53 − 1`.
- **U5.** Parameters belong to one (strategy, instrument) pair, as section 6.7 gives each pair its own evaluation context.
  - Malformed parameters produce an evaluation failure for that pair only and do not abort unrelated evaluations.
  - `Parameters` stays a strict, validated type. The orchestration layer converts its refusal into a structured evaluation failure.
  - No failure code is invented: OD-3 is resolved before the mapping is implemented in SE-5 (in SE-5b since U8).
  - Existing domain rules are kept unless the user approves an explicit amendment.
- **U6.** Durations are integers in `1 … 2^53 − 1`.
- **U7.** Equal signals within one `Signals` are kept as given, with no rule about them. Signal identity stays OD-18.
- **U8.** U5 is recorded in `docs/domain.md` section 6.5. Only the conversion of a parameter refusal into a per-pair failure waits for OD-3: it is split out of SE-5 into a new slice SE-5b, and SE-5 is built without it (section 13).
- **U9.** SE-5b goes into roadmap Phase C next to SE-10, as it shares OD-3 with it; domain section 6.5 and the roadmap status record the amendment date 2026-11-12 (section 13).

## 13. Proposed document changes (need the user's approval)

The user decided on 2026-11-12, in answer to the specification review, that U5 is recorded in the domain document (section 6.5) and that only the conversion of a parameter refusal is gated, split out of SE-5 (**U8**). In answer to the plan review the same day, the user placed SE-5b in Phase C next to SE-10 and had both documents date the amendment (**U9**). The exact text below is approved or rejected together with this specification; it alters no established rule (section 4) and no other decision of section 6. Each edit is a replacement of the quoted "before" text by the "after" text; nothing else in either document changes.

**`docs/domain.md`**

1. Section 6.5 heading. Before: `### 6.5 Parameters (part of OD-13, 2026-11-10)`. After: `### 6.5 Parameters (part of OD-13, 2026-11-10; amended 2026-11-12)`.
2. Section 6.5, a new paragraph after the existing one (separated by a blank line): `Malformed parameters, that is, parameters outside the shape of this section, give an evaluation failure for that pair alone, produced by execution without calling the strategy; the other pairs of the execution are unaffected (section 6.7). Its code is open (OD-3).`
3. Section 7, OD-3 row. Before: `**Result model (remainder).** The taxonomy of machine-readable failure reasons;`. After: `**Result model (remainder).** The taxonomy of machine-readable failure reasons, including the code for malformed parameters (section 6.5);`. In the same row, "Blocks" before: `Data-quality gate, any strategy`; after: `Data-quality gate, any strategy, execution of a pair with malformed parameters`.

**`docs/roadmap.md`**

4. Status line. Before: `**Status:** Approved (2026-11-11). Nothing is built.`. After: `**Status:** Approved (2026-11-11); amended 2026-11-12 (SE-5b). Nothing is built.` (the trailing two spaces of the Markdown line break are kept).
5. SE-5 row, "Content": append the sentence ` Malformed parameters (domain section 6.5) are SE-5b's.` after `Stateless pairs only; stateful pairs wait for SE-14.`
6. Phase C table, a new row directly before the SE-10 row:
   `| **SE-5b** Malformed parameters in execution | A pair whose parameters are refused gets an evaluation failure for that pair alone, without calling the strategy; the other pairs are unaffected. | Sections 6.5, 6.7; DR-14, DR-22 | SE-5 | OD-3 (the code for malformed parameters) |`
7. SE-12 row, "Depends on". Before: `SE-10; SE-8, SE-9 and SE-11 only if the strategy uses them`. After: `SE-10, SE-5b; SE-8, SE-9 and SE-11 only if the strategy uses them`.
8. Section 3, row 4, "Unblocks". Before: `| 4 | OD-3 (remainder), OD-8 | SE-10 | |`. After: `| 4 | OD-3 (remainder), OD-8 | SE-10, SE-5b | |`.
9. Section 4 diagram, inside the code block. Before (three lines, the middle one empty):
   ```text
          └→ [OD-5, OD-12, OD-23, OD-24] SE-16

   Optional inputs of SE-12, only if the strategy uses them: SE-8, SE-9, SE-11.
   ```
   After (five lines):
   ```text
          └→ [OD-5, OD-12, OD-23, OD-24] SE-16

   SE-5 → [OD-3] SE-5b → SE-12

   Optional inputs of SE-12, only if the strategy uses them: SE-8, SE-9, SE-11.
   ```
   The lines keep their indentation in the roadmap (the first line starts with seven spaces; the others at column 0).

Phase A (SE-1 to SE-6) stays free of gates, so roadmap section 1 and `CLAUDE.md` need no change. The edits are made in Task 1 of the SE-3 plan. If the user does not approve them, none is made.
