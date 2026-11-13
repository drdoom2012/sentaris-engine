# SE-3 Evaluation Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. In this project the lifecycle is `/slice SE-3` (`.claude/skills/slice/SKILL.md`), and its rules override the sub-skill.

**Goal:** Build the validated, immutable evaluation types: time, instrument key, parameters, signal, the three-outcome result, the rows of the three inputs, the snapshot and the evaluation context.

**Architecture:** The types live in small pure modules under `sentaris_engine.domain`. Every type is a final, frozen class that validates itself at construction and raises only `EvaluationTypeError`. `Parameters` builds on SE-2's `FrozenMapping` and `is_payload_scalar`. The snapshot stores its series behind read-only mappings that iterate in ascending key order.

**Tech Stack:** Python 3.12, stdlib only (`dataclasses`, `decimal`, `types`, `typing`, `collections.abc`); pytest, mypy strict and ruff, as set up in SE-1.

**Spec:** `docs/superpowers/specs/2026-11-12-se-3-evaluation-types-design.md` (revision 5). "Spec 5.3" and "N8" below refer to that document. The domain document is `docs/domain.md`.

**Revision:** 3, approved by the user (2026-11-12). Revision 2 followed one Opus plan review and a scoped re-review (`slice-reviewer`: approved with changes; its HIGH finding and one MEDIUM were decided by the user as U9, everything else addressed). Revision 3 follows the user's request of 2026-11-12: four tasks instead of two, and a recorded check of SE-2's `FrozenMapping` against the assumptions of `Parameters` (section "FrozenMapping facts"). Requirements, U1 to U9, acceptance criteria, negative tests and the section 13 edits are unchanged. Revision 3 was reviewed by Opus (`slice-reviewer`: approved, three LOW notes, all addressed: a separate `row_builders.py`, complete RED expectations, new suffixed functions in the shared test file).

**Precondition:** No task starts until the user has explicitly approved the specification **and** the document changes of its section 13.

## Global Constraints

- Imports come only from the pinned pure-stdlib allowlist (`tests/architecture/purity.py`) and from `sentaris_engine.domain`. No list in `tests/architecture/` changes, and no dependency is added.
- **Exact types.** Check types with `type(v) is X`, never `isinstance`, so a `bool` is never accepted as an `int` and a subclass never passes.
- **Exceptions.** Every malformed value given to an SE-3 constructor or validator raises exactly `EvaluationTypeError` (spec 5, "Errors"). Each check comes before any operation that could raise on the value (hashing, unpacking, `<`, `+`, `len`, iteration). A `PayloadError` is re-raised as `EvaluationTypeError` with `raise … from`. No handler is broader than `PayloadError`.
  - Calling a constructor with the wrong number or names of arguments is a Python call error, not an input value, and is out of scope of N15.
  - A subclass definition raises `TypeError` (spec 5, "Final").
- **Decimal checks** use only `type(v) is Decimal`, `v.is_finite()`, `v.is_signed()` and `v.is_zero()`. These never consult or signal the context. Never compare a `Decimal` with `<` or `==` before `is_finite()` has passed, because comparing an sNaN raises `InvalidOperation`.
- **Final and frozen.**
  - Dataclass types use `@final` and `@dataclass(frozen=True, slots=True)`, with validation in `__post_init__`. Normalised values are stored with `object.__setattr__`.
  - Each class body defines `__init_subclass__`, which raises `TypeError`.
  - Snapshot and context use `eq=False`.
- **Tests** assert the exception class with `type(exc) is EvaluationTypeError` through the helper `raises_exactly` (Task 1), never with the message.
- **Every task** runs its own RED/GREEN cycle, its focused tests, `make check` and one commit. A later task never edits the production module of an earlier task. In the shared `test_evaluation_type_rules.py` a task adds **new** test functions, named after the N-test with a suffix for its group (`_parameters`, `_result`, `_rows`, `_snapshot`; for example `test_types_are_immutable_rows`), and never edits an earlier task's functions, so each review package shows exactly what the task added. Builders that import a later module live in their own helper module (`row_builders.py`, Task 3), so earlier tests keep collecting.
- **One change from a valid baseline.** Every negative case is built from a valid baseline by changing exactly one field or element, and has a positive twin in the same test with that element correct. The builders' defaults are valid. The order, shape and key-order tests (N7, N11, N13) use `as_of = 10_000_000`, so that an order case cannot be rejected by the `as_of` check instead; tests that fix their own `as_of` (N8, the `MAX_TIME_MS` boundary) keep it.
- **`UNEXPECTED_VALUES`** (in `evaluation_helpers.py`, Task 1) is the shared N15 list: `None`, `object()`, `1.0`, `b"x"`, `{1}`, a generator, `"1"`, `1`, an `int` subclass instance, a `str` subclass instance, a `Decimal` subclass instance and an `Enum` member. N15 parametrises over every (constructor or validator, argument) pair, `check_instant`, `check_duration` and `check_instrument_key` included, and skips per argument only the values that are valid there. The skips are exactly: `None` for `turnover`, `mark_price` and `funding`; `1` for `check_instant`, `check_duration`, every row instant field and `Snapshot.as_of` (over the empty baseline `Snapshot(as_of, {}, {}, None)` it is valid); `EvaluationContext.as_of` is not skipped, because its baseline snapshot has `as_of = 10_000_000`, so `1` raises by the mismatch check; `"1"` for `check_instrument_key`, the failure code and the signal kind.
- **`EvaluationTypeError`** is an exception class, not one of the types of spec 5. It is not final, and N14 does not cover it (my call on "every SE-3 class").
- **mypy.** `Parameters.__getitem__` may use one `typing.cast` over `FrozenMapping`'s `PayloadValue`; that is the only cast in `parameters.py`. Tests may use narrow casts or `# type: ignore[<code>]` as the "Type checking" bullet says.
- **Type checking.** Intentional type misuse in tests gets a narrow `# type: ignore[<code>]`.
- **Comments** cite rules by ID (`DR-14`, `U1`, `OD-3`); they do not restate them.
- **Documents.** `docs/domain.md` and `docs/roadmap.md` change only in Task 1, and only with the exact text of spec section 13.

## Review Focus

1. **sNaN and NaN in a decimal field** must raise `EvaluationTypeError`, never `InvalidOperation`, from the sign or comparison check. Test `test_decimal_nan_kinds_are_refused` in Task 3 covers `Decimal("NaN")`, `Decimal("sNaN")` and `Decimal("-sNaN")` in every decimal field.
2. **`dataclasses.replace` must re-validate**, so it cannot produce an invalid row or outcome. Test `test_replace_revalidates` in Task 3: `dataclasses.replace(candle, open=Decimal("-1"))` raises `EvaluationTypeError`. The same test exists in Task 2 for `EvaluationFailure(code="")`.
3. **`Parameters` must not inherit `Mapping.__eq__`.** The inherited method would make `Parameters({"a": 1}) == {"a": 1}` true and `{"a": True}` equal `{"a": 1}`. Test: N3's `test_parameters_equality_is_canonical` in Task 1.
4. **Huge integers** such as `10**400` and `-(10**400)`, given as an instant or a duration, raise `EvaluationTypeError` without any conversion to `str` or `float`. Test: cases in N1 in Task 1.
5. **A `Decimal` subclass instance** in a row field or as a parameter value is refused even though it is finite. Test: cases in N6 in Task 3 and in N3 in Task 1.

---

## File structure

| File | Task | Responsibility |
|---|---|---|
| `src/sentaris_engine/domain/payload.py` | 1 | Rename `_has_surrogate` to the public `has_surrogate` and update its internal uses. Nothing else changes. |
| `src/sentaris_engine/domain/errors.py` | 1 | `EvaluationTypeError`. |
| `src/sentaris_engine/domain/timing.py` | 1 | `MAX_TIME_MS`, `Instant`, `Duration`, `check_instant`, `check_duration`. |
| `src/sentaris_engine/domain/instrument.py` | 1 | `check_instrument_key`. |
| `src/sentaris_engine/domain/parameters.py` | 1 | `Parameters`. |
| `src/sentaris_engine/domain/signal.py` | 2 | `Signal`. |
| `src/sentaris_engine/domain/result.py` | 2 | `Signals`, `NoSignal`, `EvaluationFailure`, `Result`. |
| `src/sentaris_engine/domain/rows.py` | 3 | `Candle`, `OpenInterest`, `FundingRate`, `RATE_TYPES`. |
| `src/sentaris_engine/domain/snapshot.py` | 4 | `Snapshot`. |
| `src/sentaris_engine/domain/context.py` | 4 | `EvaluationContext`. |
| `tests/domain/evaluation_helpers.py` | 1 | `raises_exactly`, `UNEXPECTED_VALUES`. Imports nothing from later tasks. |
| `tests/domain/row_builders.py` | 3, 4 | Task 3: `candle`, `open_interest`, `funding`. Task 4: `snapshot`. |
| `tests/domain/test_timing.py` | 1 | N1, N2. |
| `tests/domain/test_parameters.py` | 1 | N3. |
| `tests/domain/test_result.py` | 2 | N4, N5. |
| `tests/domain/test_rows.py` | 3 | N6. |
| `tests/domain/test_snapshot.py` | 4 | N7, N8, N11, N13. |
| `tests/domain/test_context.py` | 4 | N9, N12. |
| `tests/domain/test_evaluation_type_rules.py` | 1 to 4 | N10, N14, N15. Each task adds the cases for its own types. |
| `docs/domain.md`, `docs/roadmap.md` | 1 | Spec section 13, edits 1 to 9, verbatim. |
| `CLAUDE.md` | 4 | "Current state": SE-3 exists. |

## FrozenMapping facts (checked 2026-11-12)

The orchestrator ran SE-2's `FrozenMapping` (`src/sentaris_engine/domain/payload.py`, on `main` at `c7a732f`) over the inputs `Parameters` passes to it, with a throwaway script outside the repository. Results:

- **Raises exactly `PayloadError`, nothing else:**
  - pair structures `[("a",)]`, `[("a", 1, 2)]`, `[["a", 1]]`, `["a"]`, `[("a", 1), "b"]` and `[None]`;
  - unhashable keys `[([1], 1)]` and `[({}, 1)]`: the key type is checked before any hashing;
  - a duplicate key from pairs and an `int` key in a `dict`;
  - cyclic values: a self-containing `list` as a value, a pair list that contains itself, and a self-containing `dict`;
  - the values `1.0`, `b"x"`, `{1}`, a generator, `object()`, a `Decimal`, `int` or `str` subclass instance, an `Enum` member, `Decimal("sNaN")`, `2**53` and a surrogate key;
  - the sources `None`, `{1}`, a generator, `5`, `"ab"` and `b"ab"`.
- **Accepted by `FrozenMapping`, so `Parameters` must refuse them itself:**
  - the values `None`, `[1]`, `(1,)`, `{}` and `FrozenMapping({})`: they are payload values, and `is_payload_scalar` returns `False` for each;
  - a `FrozenMapping` given as the source: `Parameters` refuses it by its own source check before calling `FrozenMapping`.
- **`is_payload_scalar` never raises.** It returns `False` for `Decimal("sNaN")`, `object()`, `{1}` and a `Decimal` subclass instance.

So the order of Task 1 Step 3 is sufficient:
1. the exact source type;
2. `FrozenMapping` under `except PayloadError` only;
3. `is_payload_scalar` per value.

No broader handler is needed or allowed. The facts are pinned by Task 1's N3 and N15 cases; if SE-2 changes, those tests fail.

## Interfaces (whole slice)

```python
# errors.py
class EvaluationTypeError(ValueError): ...

# timing.py
MAX_TIME_MS: Final = 2**53 - 1
type Instant = int
type Duration = int
def check_instant(value: object) -> int: ...        # exact int, 0 ≤ v ≤ MAX_TIME_MS (U4)
def check_duration(value: object) -> int: ...       # exact int, 1 ≤ v ≤ MAX_TIME_MS (U6)

# instrument.py
def check_instrument_key(value: object) -> str: ... # exact str, non-empty; nothing else (6.8)

# payload.py (changed)
def has_surrogate(text: str) -> bool: ...

# parameters.py
@final
class Parameters(Mapping[str, bool | int | str | Decimal]):
    def __init__(self, source: object) -> None: ...  # exact dict, or exact list/tuple of pairs
    # __getitem__, __iter__ (code-point order), __len__, __eq__ (canonical bytes; NotImplemented
    # for every other type), __hash__ (hash of canonical bytes), __repr__

# signal.py
@final @dataclass(frozen=True, slots=True)
class Signal:
    kind: str
    payload: FrozenMapping

# result.py
@final @dataclass(frozen=True, slots=True)
class Signals:
    signals: tuple[Signal, ...]
@final @dataclass(frozen=True, slots=True)
class NoSignal: ...
@final @dataclass(frozen=True, slots=True)
class EvaluationFailure:
    code: str
type Result = Signals | NoSignal | EvaluationFailure

# rows.py
@final @dataclass(frozen=True, slots=True)
class Candle:
    open_time: int; open: Decimal; high: Decimal; low: Decimal; close: Decimal
    volume: Decimal; turnover: Decimal | None; conflicted: bool
@final @dataclass(frozen=True, slots=True)
class OpenInterest:
    time: int; open_interest: Decimal; open_interest_value: Decimal; conflicted: bool
@final @dataclass(frozen=True, slots=True)
class FundingRate:
    funding_time: int; rate_type: str; funding_rate: Decimal; mark_price: Decimal | None; conflicted: bool
RATE_TYPES: Final = frozenset({"Regular", "Special"})

# snapshot.py
@final @dataclass(frozen=True, slots=True, eq=False)
class Snapshot:
    as_of: int
    candles: Mapping[int, tuple[Candle, ...]]              # given as dict; stored as MappingProxyType
    open_interest: Mapping[int, tuple[OpenInterest, ...]]  # same
    funding: tuple[FundingRate, ...] | None

# context.py
@final @dataclass(frozen=True, slots=True, eq=False)
class EvaluationContext:
    snapshot: Snapshot
    parameters: Parameters
    as_of: int
```

---

### Task 1: Time, instrument key, Parameters, and the domain document changes

**Implementer:** `opus`. `Parameters` equality goes through the canonical form, its exception discipline over pair sources is subtle, and the task edits the domain document (slice skill, rule 4).

**Files:** the Task 1 rows of the file structure table.

**Scope:** spec 5.1, 5.2, 5.3; the parts of spec 5 (exact types, immutable, final, errors) that apply to `Parameters`; scope item 3 (`has_surrogate`); spec section 13, edits 1 to 9.

**Interfaces:**
- Consumes `FrozenMapping`, `PayloadError` and `is_payload_scalar` from `payload.py`.
- Produces `EvaluationTypeError`, everything under `timing`, `check_instrument_key`, `Parameters` and `has_surrogate`, as in the interfaces block, plus two test helpers:
  - `raises_exactly(exc_type: type[BaseException], fn: Callable[[], object]) -> None` calls `fn` and asserts that it raised an exception `e` with `type(e) is exc_type`;
  - `UNEXPECTED_VALUES: tuple[object, ...]` (Global Constraints).

- [ ] **Step 1: Write the failing tests**

  **`test_timing.py`**
  - `test_invalid_instant_is_refused`, parametrised over `-1`, `2**53`, `10**400`, `-(10**400)`, `True`, `False`, `1.0`, `Decimal(1)`, `"1"`, `None`, an `int` subclass instance and an `IntEnum` member. Each raises exactly `EvaluationTypeError`.
  - `test_invalid_duration_is_refused`, parametrised over the same values plus `0`.
  - `test_valid_time_is_returned`: `check_instant` returns `0`, `1` and `2**53 - 1`; `check_duration` returns `1` and `2**53 - 1`.
  - `test_invalid_instrument_key_is_refused`, parametrised over `""`, `None`, `b"x"`, a `str` subclass instance and `1`.
  - `test_instrument_key_is_opaque`: `"a b"`, `"\ud800"` and `"BTC/USDT:USDT"` are returned unchanged.

  **`test_parameters.py`**
  - `test_invalid_parameters_are_refused`:
    - value cases: `None`, `[1]`, `(1,)`, `{}`, `FrozenMapping({})`, `1.0`, `Decimal("NaN")`, `2**53`, a `Decimal` subclass instance and an `IntEnum` member;
    - key cases: `1` and `"\ud800"`;
    - pair case: `[("a", 1), ("a", 2)]`;
    - source cases: `None`, `{1}`, `5` and `FrozenMapping({"a": 1})`.
  - `test_parameters_equality_is_canonical`:
    - `Parameters({"a": True}) != Parameters({"a": 1})`;
    - `Parameters({"a": 1}) != {"a": 1}`;
    - `Parameters({"a": 1}) != FrozenMapping({"a": 1})`;
    - `Parameters({}) == Parameters([])`;
    - `Parameters({"b": 1, "a": 2})` equals `Parameters([("a", 2), ("b", 1)])` with the same hash, and `list(...)` gives `["a", "b"]`.
  - `test_parameters_hold_values`: `Parameters({"k": Decimal("1.0")})["k"]` is exactly `Decimal("1.0")`, and `len` is 1.

  **`test_evaluation_type_rules.py`** (created), with Task 1's types:
  - `test_types_are_immutable`:
    - `Parameters` attribute assignment raises `AttributeError`;
    - a source `dict` mutated after `Parameters(d)`, and a pairs `list` mutated after `Parameters(pairs)`, change nothing;
    - `not hasattr(p, "__dict__")`;
    - calling `p.__init__({"b": 2})` on an existing `Parameters` raises `TypeError` and leaves `p` and `hash(p)` unchanged.
  - `test_types_cannot_be_subclassed`, for `Parameters`.
  - `test_malformed_input_raises_only_evaluation_type_error`, with the Task 1 cases of N15:
    - the pair structures, unhashable keys and cyclic values listed under "FrozenMapping facts";
    - nested values: a `list`, `tuple`, `dict`, `set`, `FrozenMapping`, and a cyclic `list` (`l = []; l.append(l)`);
    - `UNEXPECTED_VALUES` in every argument of `check_instant`, `check_duration`, `check_instrument_key` and `Parameters`, with the skips of Global Constraints.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/domain/test_timing.py tests/domain/test_parameters.py tests/domain/test_evaluation_type_rules.py -q`

  Expected: collection errors (modules missing).

- [ ] **Step 3: Implement**

  - `payload.py`: rename `_has_surrogate` to `has_surrogate` only. SE-2's tests stay unchanged and must pass.
  - `Parameters.__init__`, in the order justified under "FrozenMapping facts":
    1. Check that the source is an exact `dict`, `list` or `tuple`.
    2. Build `FrozenMapping(source)` inside `try`/`except PayloadError`, re-raising as `EvaluationTypeError` with `from`.
    3. Reject any value for which `is_payload_scalar` is `False`.
    4. Store the mapping in a slot. A second `__init__` call raises `TypeError` before touching anything, like `FrozenMapping` does with its `hasattr` guard. `__setattr__` and `__delattr__` raise `AttributeError` once the instance is initialised.
  - `Parameters` equality and hash: `__eq__` compares `canonical_bytes()` of the two inner mappings and returns `NotImplemented` for any type other than `Parameters`; `__hash__` is the hash of those bytes.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: the command from Step 2, then `uv run pytest tests/domain -q`.

  Expected: all pass, the SE-2 tests included.

- [ ] **Step 5: Apply spec section 13 to `docs/domain.md` and `docs/roadmap.md`**

  Apply edits 1 to 9 of spec section 13: replace each quoted "before" text by its "after" text, or insert the given line at the given place. Each "before" text occurs exactly once; the orchestrator checked this when writing the plan. Change nothing else.

  Verify:
  - `git diff --stat docs/` shows only `docs/domain.md` and `docs/roadmap.md`;
  - `git diff docs/` contains exactly the nine edits, character for character.

- [ ] **Step 6: Run the gate and commit**

  Run: `make check`. Expected: the final pytest line reports `passed` with no failures, and ruff, mypy and lint-imports are clean.

  ```bash
  git add src/sentaris_engine/domain tests/domain docs/domain.md docs/roadmap.md
  git commit -m "feat: SE-3 time, instrument key and parameters"
  ```

**Completion condition:**
- AC-1, AC-2 and AC-3 hold.
- The `Parameters` and validator parts of AC-8 and AC-10 hold.
- `make check` passes.
- The diff of `docs/` is exactly edits 1 to 9 of spec section 13.

---

### Task 2: Signal and Result

**Implementer:** `sonnet`. These are small dataclasses with exact-type checks; equality reuses `FrozenMapping`'s canonical equality, which is already tested in SE-2.

**Files:** the Task 2 rows of the file structure table; adds cases to `tests/domain/test_evaluation_type_rules.py`.

**Scope:** spec 5.4 and 5.5; the parts of spec 5 that apply to them.

**Interfaces:**
- Consumes `EvaluationTypeError`, `raises_exactly`, `UNEXPECTED_VALUES`, `has_surrogate`, `FrozenMapping` and `Parameters`, the last only as a wrong payload type in a test.
- Produces `Signal`, `Signals`, `NoSignal`, `EvaluationFailure` and `Result`, as in the interfaces block.

- [ ] **Step 1: Write the failing tests**

  **`test_result.py`**
  - `test_signals_outcome_requires_signals`: `Signals(())`, `Signals([s])`, `Signals((None,))`, `Signals(({},))`, `Signals(((s,),))` and `Signals((NoSignal(),))` each raise. Positive twin: `Signals((s,))` constructs.
  - `test_signals_keep_order_and_duplicates`:
    - `Signals((s1, s2)).signals == (s1, s2)`;
    - `Signals((s1, s2)) != Signals((s2, s1))`;
    - `Signals((s1, s1))` constructs (U7).
  - `test_failure_requires_code`: `""`, `None`, `1`, `"\ud800"` and a `str` subclass instance each raise. Positive twin: `EvaluationFailure("x")`.
  - `test_outcomes_are_distinct`:
    - `NoSignal() == NoSignal()`;
    - no pair from `Signals((s,))`, `NoSignal()` and `EvaluationFailure("x")` compares equal;
    - none of them equals `None`.
  - `test_invalid_signal_is_refused`:
    - kind `""`, `None`, `1` or `"\ud800"`;
    - payload `{}`, `None` or `Parameters({})`;
    - positive twin: `Signal("k", FrozenMapping({}))`.
  - `test_signal_equality_is_canonical`:
    - `Signal("k", FrozenMapping({"a": True})) != Signal("k", FrozenMapping({"a": 1}))`;
    - equal signals hash equally.
  - `test_replace_revalidates`: `dataclasses.replace(EvaluationFailure("x"), code="")` raises.

  **`test_evaluation_type_rules.py`**, extended with `Signal`, `Signals`, `NoSignal` and `EvaluationFailure`:
  - immutability:
    - assigning to every field raises `dataclasses.FrozenInstanceError`;
    - `type(Signals((s,)).signals) is tuple`;
    - `not hasattr(x, "__dict__")`;
  - no subclassing;
  - N15:
    - `Signals(((s,),))`;
    - `UNEXPECTED_VALUES` in every argument, with the skips of Global Constraints.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/domain/test_result.py tests/domain/test_evaluation_type_rules.py -q`

  Expected: collection errors in `test_result.py` and in the whole of `test_evaluation_type_rules.py`, whose imports now name the missing modules; Task 1's tests in the other files still pass.

- [ ] **Step 3: Implement `signal.py` and `result.py`**

  Validation goes in `__post_init__`, with exact-type checks first. `Signals` checks `type(signals) is tuple`, then that it is non-empty, then each element's exact type.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: the command from Step 2, then `uv run pytest tests/domain -q`.

  Expected: all pass.

- [ ] **Step 5: Run the gate and commit**

  Run: `make check`. Expected: all steps clean, and the final pytest line reports `passed`.

  ```bash
  git add src/sentaris_engine/domain tests/domain
  git commit -m "feat: SE-3 signal and result"
  ```

**Completion condition:**
- AC-4 holds.
- The Task 2 parts of AC-8 and AC-10 hold.
- `make check` passes.

---

### Task 3: Rows

**Implementer:** `sonnet`. These are field checks only. The one subtle point, that NaN kinds must not raise `InvalidOperation`, is fixed by the Global Constraints rule on `Decimal` and pinned by Review Focus 1.

**Files:** the Task 3 rows of the file structure table; adds cases to `tests/domain/test_evaluation_type_rules.py`.

**Scope:** spec 5.6; the parts of spec 5 that apply to rows.

**Interfaces:**
- Consumes `check_instant`, `EvaluationTypeError`, `raises_exactly` and `UNEXPECTED_VALUES`.
- Produces `Candle`, `OpenInterest`, `FundingRate` and `RATE_TYPES`, as in the interfaces block. It also creates `tests/domain/row_builders.py` with these builders, each with valid defaults:
  - `candle(open_time: int, **overrides: object) -> Candle`;
  - `open_interest(time: int, **overrides: object) -> OpenInterest`;
  - `funding(funding_time: int, rate_type: str = "Regular", **overrides: object) -> FundingRate`.

- [ ] **Step 1: Write the failing tests**

  **`test_rows.py`**
  - `test_invalid_row_field_is_refused`, parametrised over every field of the three rows, each case overriding one field of a valid builder default:
    - decimal fields: `1.0`, `Decimal("Infinity")`, `Decimal("-Infinity")`, `"1"`, `1`, a `Decimal` subclass instance, and `None` where the field does not allow it;
    - non-negative fields: also `Decimal("-1")` and `Decimal("-0")`;
    - `funding_rate`: valid at `Decimal("-0.00005123")` and `Decimal("0")`, raises at `Decimal("-0")`;
    - instants: N1's invalid values;
    - `conflicted`: `0`, `1` and `None`;
    - `rate_type`: `"regular"`, `""` and `None`.
  - `test_decimal_nan_kinds_are_refused` (Review Focus 1).
  - `test_nullable_fields`: `turnover=None` and `mark_price=None` construct.
  - `test_rows_compare_by_fields`:
    - two candles built from the same values are equal and hash equally;
    - `candle(0, open=Decimal("1.0")) == candle(0, open=Decimal("1.00"))` (spec 5.6);
    - a different `conflicted` makes them unequal.
  - `test_replace_revalidates` (Review Focus 2).

  **`test_evaluation_type_rules.py`**, extended with the three rows:
  - immutability: field assignment fails, and `not hasattr(x, "__dict__")`;
  - no subclassing;
  - N15: `UNEXPECTED_VALUES` in every field, with the skips of Global Constraints.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/domain/test_rows.py tests/domain/test_evaluation_type_rules.py -q`

  Expected: collection errors in `test_rows.py` and in the whole of `test_evaluation_type_rules.py`; the tests of Tasks 1 and 2 in their own files still pass.

- [ ] **Step 3: Implement `rows.py`**

  Two private checks, `_non_negative(value: object) -> Decimal` and `_signed(value: object) -> Decimal`, use only the `Decimal` predicates of Global Constraints. `rate_type` is checked as `type(v) is str and v in RATE_TYPES`.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: the command from Step 2, then `uv run pytest tests/domain -q`.

  Expected: all pass.

- [ ] **Step 5: Run the gate and commit**

  Run: `make check`. Expected: all steps clean, and the final pytest line reports `passed`.

  ```bash
  git add src/sentaris_engine/domain tests/domain
  git commit -m "feat: SE-3 candle, open interest and funding rows"
  ```

**Completion condition:**
- AC-5 holds.
- The row parts of AC-8 and AC-10 hold.
- `make check` passes.

---

### Task 4: Snapshot, EvaluationContext, and CLAUDE.md

**Implementer:** `opus`. The task touches availability (U1 and the `as_of` and `MAX_TIME_MS` boundaries), the ordering contract (DR-10) and the strict exception discipline over nested containers.

**Files:** the Task 4 rows of the file structure table; adds cases to `tests/domain/test_evaluation_type_rules.py`.

**Scope:**
- spec 5.7 and 5.8;
- section 6 (the boundaries at `as_of` and `MAX_TIME_MS`, and key order);
- the parts of spec 5 that apply to these types;
- scope item 5 (`CLAUDE.md`).

**Interfaces:**
- Consumes `check_instant`, `check_duration`, `MAX_TIME_MS`, `EvaluationTypeError`, `Parameters`, the row types and their builders, `raises_exactly` and `UNEXPECTED_VALUES`.
- Produces `Snapshot` and `EvaluationContext`, as in the interfaces block, and adds to `row_builders.py` the test builder `snapshot(as_of: int = 10_000_000, **overrides: object) -> Snapshot`. Its default is `Snapshot(as_of, {}, {}, None)`.

- [ ] **Step 1: Write the failing tests**

  **`test_snapshot.py`**
  - `test_unordered_or_duplicate_series_is_refused`, with `as_of = 10_000_000`:
    - rejected: candles `(c(0), c(0))` and `(c(60000), c(0))`; open interest likewise; funding at equal `funding_time` with `("Regular", "Regular")` and with `("Special", "Regular")`;
    - positive twins: `(c(0), c(60000))`, the same for open interest, and `(f(t, "Regular"), f(t, "Special"))`.
  - `test_row_after_as_of_is_refused`, with `as_of = 1_000_000` and timeframe `60000`. Each case is the last row of an otherwise valid series of three:
    - candle `open_time = 940_001` raises; `940_000` constructs;
    - open interest `time = 1_000_001` raises; `1_000_000` constructs;
    - funding `funding_time = 1_000_001` raises; `1_000_000` constructs.
  - `test_candle_boundary_at_max_time`, with `as_of = MAX_TIME_MS`:
    - `open_time = MAX_TIME_MS - 60000` at timeframe `60000` constructs;
    - `open_time = MAX_TIME_MS` at timeframe `1` raises;
    - `open_time = 1` at timeframe `MAX_TIME_MS` raises;
    - both rejections raise exactly `EvaluationTypeError`.
  - `test_invalid_snapshot_shape_is_refused`. The key, source, series and element cases are parametrised over both `candles` and `open_interest`:
    - `as_of`: `-1` and `True`;
    - keys: `0`, `-1`, `True` and `"5m"`;
    - source: `MappingProxyType({})` and `[(60000, ())]`;
    - a series given as a `list`;
    - an `OpenInterest` in `candles`;
    - `funding` given as `[]` or `{}`;
    - a series tuple holding a `tuple`, a `dict`, a `list` or `None`;
    - a `candles` value that is a `dict` of series.
  - `test_absent_and_empty_inputs`: `Snapshot(t, {}, {}, None)` and `Snapshot(t, {60000: ()}, {300000: ()}, ())` both construct; the second one's `candles[60000] == ()`.
  - `test_snapshot_mappings_iterate_in_key_order`: `{300000: (), 60000: (), 3600000: ()}` and a shuffled variant iterate `[60000, 300000, 3600000]`, for both mappings.
  - `test_snapshot_replace_is_refused`: `dataclasses.replace(snap, as_of=snap.as_of)` raises `EvaluationTypeError`. The stored mappings are `MappingProxyType`, which the constructor refuses (N11); this fails closed by design.

  **`test_context.py`**
  - `test_context_as_of_must_match_snapshot`: `EvaluationContext(snap, Parameters({}), snap.as_of + 1)` raises; with `snap.as_of` it constructs.
  - `test_invalid_context_field_is_refused`:
    - `parameters` given as `{}` or `FrozenMapping({})`;
    - `snapshot` given as `None` or an object that is not a `Snapshot`;
    - `as_of` given as `-1` or `1.0`.
  - `test_context_identity`: two contexts built from the same arguments are not equal and are hashable.

  **`test_evaluation_type_rules.py`**, extended with `Snapshot` and `EvaluationContext`:
  - immutability:
    - field assignment fails;
    - `type(snap.candles) is MappingProxyType` and `type(snap.open_interest) is MappingProxyType`;
    - `snap.candles[60000] = ()` raises `TypeError`;
    - `type(snap.funding) is tuple`;
    - a mutated source `dict` changes nothing;
    - `not hasattr(x, "__dict__")`;
  - no subclassing;
  - N15: `UNEXPECTED_VALUES` in every argument, with the skips of Global Constraints.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/domain/test_snapshot.py tests/domain/test_context.py tests/domain/test_evaluation_type_rules.py -q`

  Expected: collection errors.

- [ ] **Step 3: Implement `snapshot.py` and `context.py`**

  `Snapshot.__post_init__` checks in this order, so that no built-in exception can arise:
  1. `as_of` through `check_instant`.
  2. Exact `dict` for `candles` and `open_interest`.
  3. Each key through `check_duration`.
  4. Each value an exact `tuple`.
  5. Each element of the exact row type.
  6. Strictly ascending order by the spec 5.7 key.
  7. The `as_of` condition of U1.
  8. `funding` is `None` or an exact `tuple` of exact `FundingRate`, then its order and `as_of` checks.

  Store each validated mapping with `object.__setattr__` as a `MappingProxyType` over a new `dict` built in ascending key order.

  `EvaluationContext.__post_init__` checks exact `Snapshot`, exact `Parameters`, `check_instant(as_of)`, and `as_of == snapshot.as_of`.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: the command from Step 2, then `uv run pytest tests/domain -q`.

  Expected: all pass.

- [ ] **Step 5: Update `CLAUDE.md` "Current state"**

  Say that SE-3 exists: the evaluation types in `sentaris_engine.domain` (time, instrument key, parameters, signal, result, rows, snapshot, context).

- [ ] **Step 6: Run the gate and commit**

  Run: `make check`. Expected: all steps clean, and the final pytest line reports `passed`.

  ```bash
  git add src/sentaris_engine/domain tests/domain CLAUDE.md
  git commit -m "feat: SE-3 snapshot and evaluation context"
  ```

**Completion condition:**
- AC-6, AC-7 and AC-9 hold.
- The remaining parts of AC-8 and AC-10 hold.
- Every N-test of the spec exists under the name given here or in the spec.
- `make check` passes.

## Spec coverage

| Spec | Task |
|---|---|
| 5.1, 5.2, N1, N2 | 1 |
| 5.3, N3 | 1 |
| 5.4, 5.5, N4, N5 | 2 |
| 5.6, N6 | 3 |
| 5.7, N7, N8, N11, N13, section 6 boundaries | 4 |
| 5.8, N9, N12 | 4 |
| Section 5 (immutable, final, errors), N10, N14, N15 | 1 to 4, each for its own types |
| AC-9 (`make check`, purity) | every task; finally 4 |
| Scope 3 (`has_surrogate`) | 1 |
| Scope 5 (`CLAUDE.md`) | 4 |
| Scope 6, section 13 edits 1 to 9 | 1 |
