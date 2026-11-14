# SE-7a — Input declaration: design

**Slice:** SE-7a (`docs/roadmap.md`, Phase B)  
**Status:** Revision 3, approved by the user on 2026-11-14. Revision 2 was re-reviewed (approved with changes: 1 MEDIUM and 1 LOW on the domain amendment, which went to the user, and 3 LOW on the spec, fixed here). Revision 1 was reviewed by Opus (`slice-reviewer`: not approved; 1 CRITICAL, 1 HIGH, 5 MEDIUM, 5 LOW). The three findings that needed the user (F1, F2 and open question 1) were answered as U2 to U4 (section 12) and recorded in domain section 6.9; the others are fixed in this revision.  
**Domain references:** sections 5, 6.1, 6.2, 6.4, 6.5, 6.7, 6.8, 6.9; DR-08, DR-10, DR-22, DR-23; OD-3, OD-4, OD-8, OD-13 (remainder), OD-22 (none decided here; see section 11)

Decisions marked **[user Un]** were given by the user in the SE-7a conversation (section 12). Everything marked "my call" is an implementation choice the builder may keep or improve without changing behavior. Names of modules, classes and functions are indicative; the behavior is what is specified.

## 1. Goal

A strategy declares the inputs it needs, or returns an evaluation failure when it cannot (section 6.9 "Declaration", "Need", "One lookback per series", "Declaration failure"). The declarations of the pairs of one instrument are combined into the one set of needs read for that instrument (section 6.9 "Shared reading"). Pure domain code, no I/O.

Out of scope:
- narrowing a pair's snapshot to its own declaration **[user U1]** (SE-7b: it needs the lookback boundaries OD-13 leaves open);
- reading anything (SE-7b);
- calling `declare` from execution and reporting its outcome per pair, including the open report of a `declare` that raises or returns neither a declaration nor a failure (OD-13, OD-3).

## 2. Why this shape

| Choice | Derivation |
|---|---|
| `declare` is a method of both contracts, taking only the parameters | Section 6.9 "Declaration": a function of `id`, `version` (the strategy object, section 6.4) and the pair's parameters, and of nothing else. Neither `as_of`, a snapshot, state nor the instrument key (section 6.8) is passed. |
| `declare` returns a declaration or an evaluation failure | Section 6.9 "Declaration failure" **[user U2]**; section 6.5. |
| A need names an input, its series and a lookback | Section 6.9 "Need". The inputs are the three of section 5. The series is the candle timeframe or the open interest period, as the SE-3 snapshot keys them and as Quasar identifies an open interest series by `period` (api-v1 section 6.5). Funding has one series per instrument; treating it so settles nothing of OD-16. |
| A series appears at most once in a declaration; the empty declaration is valid | Section 6.9 "One lookback per series" **[user U3, U4]**. |
| The union holds each series once, with the longest lookback | Section 6.9 "Shared reading". |
| No narrowing | **[user U1]**. |
| Forming a declaration catches nothing; a value that is neither is reported by type only | The same shape as SE-4's `evaluate_stateless`. Catching and reporting are execution's, and that report is open (OD-13, OD-3). |
| Execution (SE-5) is not changed | Execution receives prebuilt snapshots. The declaration is used where the snapshots are built (SE-7b); the per-pair report of a declaration failure is wired with it. |

## 3. Scope

1. A module `sentaris_engine.domain.declaration` (my call) with the input kind, the need, the declaration, the union and the per-instrument requirements. It does not import `sentaris_engine.domain.strategy`.
2. A module `sentaris_engine.domain.declaring` (my call) with `NotADeclaration` and `declare_inputs`. It imports `declaration`, `strategy`, `parameters` and `result`.
3. An abstract `declare` on both contracts in `sentaris_engine.domain.strategy`, which imports `declaration` for its annotation. Import direction: `strategy → declaration`; `declaring → strategy, declaration`. No cycle and no `TYPE_CHECKING` import.
4. Every test strategy gains a `declare` returning the empty declaration unless its test needs another. Test strategies are defined in `tests/domain/strategy_helpers.py`, `tests/domain/test_strategy.py`, `tests/domain/test_evaluation.py`, `tests/application/execution_helpers.py` and `tests/application/test_execution.py` (including the namespace built with `ABCMeta.__new__(_ContractMeta, "Both", ...)`); the builder greps for every subclass of either contract under `tests/` to miss none. Every SE-4 "only X missing" class (`StatelessOnlyEvaluate`, `StatelessOnlyIdentity` and their stateful twins) implements `declare`, so it still fails for the reason it names.
5. The SE-4 contract test is extended: both contracts have exactly the abstract methods `identity`, `evaluate`, `declare`, and the signature of `declare` is pinned (section 8).
6. Tests under `tests/domain/`.
7. `CLAUDE.md` "Current state" says that SE-7a exists.

No domain edit is part of this slice. Section 6.9, its amendment of 2026-11-14 and the roadmap changes are committed on this branch before the plan (`a8a8518`, `4560dbd`, `4973ee9`).

## 4. Dependencies

SE-4 is merged on `main`; `main` is at `b6c3f31` (SE-6) and `make check` passes (2274 tests). The gate (OD-13, the part decided as section 6.9) is taken. The new modules import only `sentaris_engine.domain` and pinned pure-stdlib modules (expected: `dataclasses`, `enum`, `typing`). No architecture list is widened and no dependency is added.

## 5. Interfaces and contracts

The SE-3 rules apply to every new value type: exact types, immutable, final (`__init_subclass__` raises `TypeError`), and malformed input to a constructor raises exactly `EvaluationTypeError` (SE-3 spec 5).

### 5.1 Input kind

A final plain `Enum` `InputKind` (not `IntEnum` or `StrEnum`, so a member never equals an `int` or `str`) with exactly three members, one per input of section 5, in this order: `CANDLES`, `OPEN_INTEREST`, `FUNDING`. It names engine inputs only; it is not a signal kind (DR-23). A new input is added here only when section 5 adds one. `Enum` members are not orderable; the canonical order of 5.3 uses an explicit rank, the member's position in this list (precedent: `FaultCause`, SE-5).

### 5.2 Need

`InputNeed(input, series, lookback)`:

- `input`: an `InputKind` member (`type(input) is InputKind`), else `EvaluationTypeError`.
- `series`: for `CANDLES` the timeframe and for `OPEN_INTEREST` the period, each a duration checked with SE-3's `check_duration` (section 6.1: an exact `int`, not `bool`, in `1 … 2^53 − 1`); for `FUNDING` exactly `None`. Every other combination raises `EvaluationTypeError`.
- `lookback`: a duration checked with `check_duration`.
- No instrument field (section 6.9: a strategy declares no instrument, and until OD-22 no other instrument's data).
- Frozen, slotted and final; equality and hash by fields.

The **series key** of a need is `(input, series)`.

### 5.3 Declaration

`Declaration(needs)`:

- `needs`: an exact `tuple` of exact `InputNeed`, else `EvaluationTypeError`.
- Two needs with the same series key raise `EvaluationTypeError` **[user U3]**, whether their lookbacks differ or not (section 6.9 "One lookback per series").
- The empty tuple is valid **[user U4]**.
- The needs are held as an exact `tuple` in one canonical order, independent of the given order (DR-10): ascending by the rank of 5.1, then by series (funding has one). Equality and hash are by that tuple, so two declarations of the same needs are equal.
- Frozen, slotted and final.

### 5.4 The `declare` method

Both `StatelessStrategy` and `StatefulStrategy` gain an abstract method `declare(self, parameters: Parameters) -> Declaration | EvaluationFailure`. Its signature is exactly `(self, parameters)`, both positional-or-keyword with no default. It receives the pair's parameters only (section 6.9), never `as_of`, a snapshot, state or the instrument key (section 6.8).

A strategy returns an `EvaluationFailure` with a code it chooses when it cannot form a declaration, for example for parameters it judges invalid (section 6.9 "Declaration failure", section 6.5) **[user U2]**. That `declare` depends only on the strategy's version and parameters and is pure is the strategy author's obligation (section 6.9, DR-08; section 9).

### 5.5 Forming a declaration

`declare_inputs(strategy, parameters) -> Declaration | EvaluationFailure | NotADeclaration`:

1. `strategy` must derive, by real inheritance, from `StatelessStrategy` or `StatefulStrategy` (checked with `type.__subclasscheck__`, as `evaluate_stateless` does; the contracts refuse virtual subclasses), and `parameters` must be an exact `Parameters`. Otherwise `EvaluationTypeError`, and `declare` is not called.
2. It calls `strategy.declare(parameters)` once, with the very `parameters` object as the only argument.
3. An exact `Declaration` or an exact `EvaluationFailure` is returned as the very object.
4. Any other returned value gives `NotADeclaration(type(value))`. `NotADeclaration` is shaped exactly as SE-4's `NotAnOutcome`: final, frozen, slotted, `eq=False` (identity equality); one field `returned_type` with `repr=False`, checked with `type.__subclasscheck__(type, type(returned_type))`; the value itself is not kept.
5. Nothing is caught: every exception of `declare` propagates unchanged. The strategy's identity is not read.

What a pair reports for an `EvaluationFailure` (its result, section 6.9) and for a `NotADeclaration` or a raise (open, OD-13, OD-3) is wired where `declare_inputs` is called, not here.

### 5.6 Union

`union(declarations) -> Declaration`:

- `declarations`: an exact `tuple` of exact `Declaration`, else `EvaluationTypeError`.
- The result holds one need per series key that appears in any declaration, with the longest lookback any of them declares for that key (section 6.9 "Shared reading").
- The result does not depend on the order of `declarations` (DR-10). An empty tuple gives the empty declaration.

A pair whose `declare` returned an evaluation failure adds nothing (section 6.9 "Declaration failure"): its caller passes declarations only.

### 5.7 Requirements by instrument

`requirements(declared) -> dict[str, Declaration]` (my call to include it here; it is the per-instrument step of section 6.9 that SE-7b consumes):

- `declared`: an exact `tuple` whose elements are exact `tuple`s of length two, `(instrument key, Declaration)`; the key is checked with `check_instrument_key` (section 6.8), the declaration is an exact `Declaration`. Else `EvaluationTypeError`.
- The result is a fresh exact `dict` that maps each instrument key that appears to the `union` of the declarations given for it, inserted in ascending key order by code point (section 6.7, DR-10). Pairs of different instruments are never combined (section 6.7 "Snapshot"). Nothing is kept between calls.

## 6. Expected behavior

- Candles 1h over 100 h and candles 1h over 500 h, declared by two strategies on one instrument, give one need: candles 1h over 500 h.
- Candles 1h and candles 4h are different series and both appear.
- Funding declared by one strategy only appears in the union with that strategy's lookback.
- Declarations on two instruments stay apart.
- A `declare` that returns `EvaluationFailure("bad_lookback")` gives that very failure; one that returns `None` gives `NotADeclaration` with `returned_type` `NoneType`; one that raises propagates its exception.

## 7. Acceptance criteria

- AC-1: `InputKind` has exactly the three members of 5.1, is a plain `Enum`, and is final.
- AC-2: `InputNeed` accepts exactly the combinations of 5.2 and refuses every other with `EvaluationTypeError`.
- AC-3: `Declaration` refuses what 5.3 refuses, accepts the empty tuple, and holds the canonical order for every permutation of its input.
- AC-4: Both contracts have exactly the abstract methods `identity`, `evaluate` and `declare`; `declare` has exactly the signature of 5.4; a strategy lacking only `declare` cannot be instantiated.
- AC-5: `declare_inputs` behaves as 5.5 steps 1 to 5.
- AC-6: `union` gives the longest lookback per series key, is independent of input order, and refuses what 5.6 refuses.
- AC-7: `requirements` combines per instrument only, in code-point key order, and refuses what 5.7 refuses.
- AC-8: Every new type is final and immutable (SE-3 rules).
- AC-9: `make check` passes; no architecture list is widened.

## 8. Negative tests

One named test per rule this slice claims to enforce (names indicative). Refusals assert with SE-3's `raises_exactly(EvaluationTypeError, ...)`.

| Rule | Negative test |
|---|---|
| Section 6.9 "Shared reading": longest lookback per series | `test_union_keeps_the_longest_lookback_per_series`: fails if a shorter lookback, or two needs for one series, appear. |
| DR-10 for the union | `test_union_is_independent_of_declaration_order`, over all permutations. |
| DR-10 for the declaration | `test_declaration_order_is_independent_of_need_order`, over all permutations. |
| DR-10 and section 6.7 for requirements | `test_requirements_are_in_code_point_key_order`, with interleaved, reverse-ordered input (`b`, `a`, `b`). |
| Section 6.7 "Snapshot" (instruments share nothing) | `test_requirements_never_combine_two_instruments`. |
| Section 6.9 "One lookback per series" | `test_declaration_refuses_a_repeated_series`, parametrised over equal and different lookbacks. |
| Section 6.9 "Declaration": parameters only, call side | `test_declare_inputs_passes_only_the_parameters`: a recording strategy sees one call with one positional argument, the very `Parameters` object, and no keyword argument. |
| Section 6.9 "Declaration": parameters only, contract side | `test_declare_signature_takes_only_the_parameters`: `inspect.signature` of `declare` on both contracts is exactly `self, parameters`, both positional-or-keyword with no default; extends `test_contract_signatures_take_only_the_transition_inputs_contracts` in `tests/domain/test_strategy.py`. |
| `declare` is required | `test_strategy_without_declare_cannot_be_instantiated`, stateless and stateful (`...OnlyEvaluateAndIdentity`), each raising `TypeError`. |
| Section 6.9 "Declaration failure" | `test_declare_inputs_returns_an_evaluation_failure_as_the_very_object`. |
| A value that is neither is reported by type only | `test_declare_inputs_reports_a_non_declaration_by_type_only`: parametrised over `None`, a `NoSignal`, a `Signals` and a `StateTransition`: `returned_type` is the value's type, the value is not kept, and the result is neither a `Declaration` nor an `EvaluationFailure`. |
| Nothing caught (OD-13, OD-3 left open) | `test_declare_inputs_propagates_an_exception_unchanged`, the very exception object. |
| Identity not read (5.5 step 5) | `test_declare_inputs_does_not_read_identity`, with a strategy whose `identity` raises (like `_UnreadableIdentity` in `tests/domain/test_evaluation.py`); its declaration is still returned. |
| Section 5 (no other input exists) | `test_input_kind_has_exactly_the_section_5_inputs`. |
| Shape of a need | `test_input_need_refuses_malformed_fields`, parametrised: a non-`InputKind` input (including a `str` and an `int`); `bool`, an `IntEnum`, `0`, a negative and `2^53` as series or lookback; `None` as series for candles or open interest; any series for funding. |
| Shape of a declaration | `test_declaration_refuses_malformed_needs`: a list, a non-`InputNeed` element. |
| Inputs of `declare_inputs` | `test_declare_inputs_refuses_malformed_inputs_without_calling_declare`: a non-strategy, a class not deriving from a contract, a `dict` or a `Parameters`-like mapping as parameters; a recording strategy asserts `declare` was not called. |
| Inputs of `union` | `test_union_refuses_malformed_input`: a list, a non-`Declaration` element. |
| Inputs of `requirements` | `test_requirements_refuse_malformed_input`: a list; an element that is a list, of length one or three; an empty or non-`str` key; a non-`Declaration` value. |
| Final and immutable | `test_new_types_are_final_and_immutable`: subclassing raises `TypeError`, assigning a field raises. |

## 9. Enforced guarantees and known limitations

- Enforced by the tests of section 8: the union, its order independence, per-instrument separation, one lookback per series, the shape of needs and declarations, that `declare` is required and takes only the parameters, and that `declare_inputs` passes only the parameters, returns a failure as given, reports anything else by type and catches nothing.
- Structural: a need has no instrument field.
- Convention, review-only: that a strategy's `declare` depends only on its version and parameters and is pure (section 6.9, DR-08). The SE-1 purity checks cover strategy modules under `sentaris_engine.strategies`, as they do for `evaluate`; no test can show that an arbitrary strategy's `declare` is deterministic.
- Not enforced in this slice: the narrowed view and sufficiency per pair (section 6.9; SE-7b, SE-10), and that a pair whose declaration failed is not evaluated and adds nothing to the shared reading (section 6.9 "Declaration failure"), which is wired where `declare_inputs` is called.

## 10. Exclusions

- Narrowing a snapshot; reading data; lookback boundaries (OD-13).
- Calling `declare` from execution; the report and code for a `declare` that raises or returns neither (OD-13, OD-3); any engine-chosen failure code (OD-3).
- Whether a declared series is one Quasar offers (open interest is `5m` only in v1; OD-4, SE-7b).
- Any relation between lookback and series, such as a lookback shorter than one candle or not a multiple of the timeframe (OD-13 boundaries, OD-8).
- Judging whether data is sufficient (OD-8); cross-instrument needs (OD-22); where strategy specifications live (OD-13).

## 11. Open questions

None for this slice. The open parts of OD-13 (where strategy specifications live, lookback boundaries, the report of a `declare` that raises or returns neither) are outside it (section 10).

## 12. Decisions by the user

- **U1** (2026-11-13). Narrowing a pair's snapshot, by series and by lookback, belongs entirely to SE-7b; SE-7a has the declaration and the union only. The roadmap rows of SE-7a and SE-7b say so (`4560dbd`).
- **U2** (2026-11-14). A strategy that cannot form a declaration returns an evaluation failure with a code it chooses; that failure is the pair's result, the strategy is not evaluated, and the pair adds nothing to the shared reading. Recorded in section 6.9 "Declaration failure".
- **U3** (2026-11-14). A declaration names each series at most once; a repeat is malformed. Recorded in section 6.9 "One lookback per series".
- **U4** (2026-11-14). The empty declaration is valid. Recorded in section 6.9 "One lookback per series".
- Section 6.9 itself (declaration from version and parameters, lookback as a duration before `as_of`, longest lookback per series, read once and narrowed per pair, sufficiency per pair) was decided on 2026-11-13 before this specification.
