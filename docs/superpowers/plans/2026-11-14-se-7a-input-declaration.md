# SE-7a Input Declaration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. In this project the lifecycle is `/slice SE-7a` (`.claude/skills/slice/SKILL.md`), and its rules override the sub-skill.

**Goal:** A strategy declares its inputs from its parameters, or returns an evaluation failure; the declarations of one instrument's pairs are combined into one set of needs per instrument. Pure domain code, no I/O.

**Architecture:** Task 1 adds the value types and the combination (`sentaris_engine.domain.declaration`: `InputKind`, `InputNeed`, `Declaration`, `union`, `requirements`). Task 2 adds the abstract `declare` to both contracts in `sentaris_engine.domain.strategy`, the call side (`sentaris_engine.domain.declaring`: `NotADeclaration`, `declare_inputs`), and gives every test strategy a `declare`. Imports: `declaration → errors, instrument, timing`; `strategy → declaration, parameters` (besides its existing imports); `declaring → strategy, declaration, parameters, result, errors`. No cycle, no `TYPE_CHECKING` import.

**Tech Stack:** Python 3.12, stdlib only (`dataclasses`, `enum`, `typing`); pytest, mypy strict and ruff, as set up in SE-1.

**Spec:** `docs/superpowers/specs/2026-11-13-se-7a-input-declaration-design.md` (revision 3, approved by the user on 2026-11-14). "Spec 5.3" and so on below refer to that document. The domain document is `docs/domain.md`.

**Revision:** 2, approved by the user on 2026-11-14. Revision 1 was reviewed by Opus (`slice-reviewer`: approved with changes; 0 CRITICAL, 0 HIGH, 2 MEDIUM, 4 LOW; none needed the user). Revision 2 fixes all six.

## Global Constraints

- Production imports come only from `dataclasses`, `enum`, `typing` and `sentaris_engine.domain`. No list in `tests/architecture/` changes, no dependency is added, `pyproject.toml` does not change. Tests may use any stdlib module.
- **Exact types.** Check types with `type(v) is X`, never `isinstance` or `issubclass`. Contract membership is checked with `type.__subclasscheck__(Contract, type(v))`, as `evaluate_stateless` does (`src/sentaris_engine/domain/evaluation.py`).
- **Errors.** Malformed input to a constructor, `union` or `requirements` raises exactly SE-3's `EvaluationTypeError` (`sentaris_engine.domain.errors`). A message never formats a caller value.
- **Final and frozen.** Value types use `@final`, `@dataclass(frozen=True, slots=True)` (`eq=False` only for `NotADeclaration`), validation in `__post_init__`, and an `__init_subclass__` that raises `TypeError`, as `strategy.py` and `evaluation.py`. Durations are checked with `check_duration` (`sentaris_engine.domain.timing`); instrument keys with `check_instrument_key` (`sentaris_engine.domain.instrument`).
- **No strategy code beyond `declare`.** `declare_inputs` calls `strategy.declare(parameters)` once and never compares, hashes, formats or reprs the strategy or the returned value; it reads neither `identity` nor anything else of the strategy.
- **Tests** assert exception classes through `raises_exactly` from `tests/domain/evaluation_helpers.py`, never messages. Propagation and pass-through tests assert with `is`. Hostile classes or objects are built inside the test body or passed as `pytest.param(..., id="...")`, never as a bare parametrize value.
- **Intentional type misuse** in tests gets a narrow `# type: ignore[<code>]`; no unused ignore (strict mypy).
- **Comments** cite rules by ID (section 6.9, DR-10, OD-13, `U3`); they do not restate them.
- **Documents.** `docs/domain.md`, `docs/roadmap.md` and the spec do not change. `CLAUDE.md` changes only in Task 2 ("Current state").
- **Branch.** Work on `se-7a-input-declaration` in the main working tree (the spec and section 6.9 are already committed there). `make check` passes before every commit.

## Rulings made in this plan (implementation only)

- **R1. `InputKind` values** are `"candles"`, `"open_interest"`, `"funding"`. Nothing reads them.
- **R2. Rank.** A module-private `Final` mapping `_RANK: dict[InputKind, int]` with `CANDLES: 0, OPEN_INTEREST: 1, FUNDING: 2` gives the canonical order of spec 5.3 (members are not orderable). The sort key of a need is `(_RANK[input], 0 if series is None else series)`; funding has one series, so `0` never collides.
- **R3. `Declaration` stores the sorted tuple** in `__post_init__` with `object.__setattr__(self, "needs", ...)`, after all checks. Duplicate series keys are found with a `set` of `(input, series)`; both elements are exact `InputKind` and `int`/`None` by then.
- **R4. `union`** builds a `dict` from series key to the longest lookback and returns `Declaration(tuple(InputNeed(...) for ...))`; the constructor sorts, so the result does not depend on input order.
- **R5. `requirements`** checks every element before it groups anything, groups declarations per key in a `dict[str, list[Declaration]]`, and returns `{key: union(tuple(groups[key])) for key in sorted(groups)}`.
- **R6. Test strategies** gain `def declare(self, parameters: Parameters) -> Declaration: return Declaration(())`. `tests/domain/strategy_helpers.py` exports `EMPTY_DECLARATION = Declaration(())` for reuse; other test modules may import it.

## Review Focus

1. **A stateful strategy:** `declare_inputs` behaves the same for a `StatefulStrategy` as for a stateless one: a declaration and a failure come back as the very object, `None` gives `NotADeclaration`. Test `test_declare_inputs_serves_both_contracts` (Task 2).
2. **Boundary durations:** `1` and `2**53 - 1` are accepted as series and as lookback for candles and open interest. Test `test_input_need_accepts_boundary_durations` (Task 1).
3. **Equal lookbacks across strategies:** two declarations each holding candles 1h over 100 h give exactly one need in the union; the union of one declaration equals that declaration; funding declared by two strategies with 8 h and 24 h gives one funding need of 24 h. Cases in `test_union_keeps_the_longest_lookback_per_series` (Task 1).
4. **Empty and repeated input to `requirements`:** an empty tuple gives `{}`; the very same `Declaration` object given twice for one key gives one entry equal to it; each call returns a new `dict`, so changing one result does not change the next. Test `test_requirements_edge_inputs` (Task 1).
5. **Declaration-like returns:** a `declare` returning a `tuple` of `InputNeed`, a `list`, a `NotAnOutcome(int)` or a `NotADeclaration(int)` gives `NotADeclaration` with that value's type. Cases in `test_declare_inputs_reports_a_non_declaration_by_type_only` (Task 2).

---

## File structure

| File | Task | Responsibility |
|---|---|---|
| `src/sentaris_engine/domain/declaration.py` | 1 | `InputKind`, `InputNeed`, `Declaration`, `union`, `requirements` (spec 5.1 to 5.3, 5.6, 5.7). Imports `errors`, `instrument`, `timing` only. |
| `tests/domain/test_declaration.py` | 1 | AC-1 to AC-3, AC-6 to AC-8 for these types. |
| `src/sentaris_engine/domain/strategy.py` | 2 | Abstract `declare` on both contracts (spec 5.4). |
| `src/sentaris_engine/domain/declaring.py` | 2 | `NotADeclaration`, `declare_inputs` (spec 5.5). |
| `tests/domain/test_declaring.py` | 2 | AC-5, AC-8 for `NotADeclaration`. |
| `tests/domain/test_strategy.py` | 2 | AC-4. |
| `tests/domain/strategy_helpers.py`, `tests/domain/test_evaluation.py`, `tests/application/execution_helpers.py`, `tests/application/test_execution.py` | 2 | `declare` on every test strategy (spec 3 item 4). |
| `CLAUDE.md` | 2 | "Current state" names SE-7a. |

---

### Task 1: Input kinds, needs, declarations and their combination

**Implementer model:** `sonnet` (value types in the established SE-3 pattern, one small grouping function).

**Files:**
- Create: `src/sentaris_engine/domain/declaration.py`
- Test: `tests/domain/test_declaration.py`

**Interfaces:**
- Consumes: `EvaluationTypeError`; `check_duration(value: object) -> int`; `check_instrument_key(value: object) -> str`.
- Produces (Task 2 and SE-7b rely on these names):
  - `class InputKind(Enum)`: `CANDLES`, `OPEN_INTEREST`, `FUNDING` (R1).
  - `class InputNeed`: fields `input: InputKind`, `series: int | None`, `lookback: int`.
  - `class Declaration`: field `needs: tuple[InputNeed, ...]`, held in canonical order.
  - `def union(declarations: tuple[Declaration, ...]) -> Declaration`
  - `def requirements(declared: tuple[tuple[str, Declaration], ...]) -> dict[str, Declaration]`

Use `H = 3_600_000` (one hour in ms) in the tests.

- [ ] **Step 1: Write the failing tests** in `tests/domain/test_declaration.py`:
  - `test_input_kind_has_exactly_the_section_5_inputs`: `[m.name for m in InputKind] == ["CANDLES", "OPEN_INTEREST", "FUNDING"]`; `type(InputKind.CANDLES) is InputKind`; `InputKind.CANDLES != "candles"` and `!= 0`; `InputKind.__mro__ == (InputKind, Enum, object)` (plain `Enum`, AC-1).
  - `test_input_need_refuses_malformed_fields`, parametrised (spec 8 row "Shape of a need"): input `"candles"`, `0`, `None`; series or lookback `True`, an `IntEnum` member of value `H`, `0`, `-1`, `2**53`, `1.0`; series `None` for `CANDLES` and `OPEN_INTEREST`; series `H` and `0` for `FUNDING`. Each `raises_exactly(EvaluationTypeError, ...)`.
  - `test_input_need_accepts_boundary_durations` (Review Focus 2): `InputNeed(k, 1, 1)` and `InputNeed(k, 2**53 - 1, 2**53 - 1)` for `CANDLES` and `OPEN_INTEREST`; `InputNeed(InputKind.FUNDING, None, 1)`; equal field values give equal needs with equal hashes.
  - `test_declaration_refuses_malformed_needs`: a `list` of needs, a tuple holding a `str` or a tuple of fields.
  - `test_declaration_refuses_a_repeated_series`, parametrised over lookbacks `(100 * H, 100 * H)` and `(100 * H, 500 * H)` for candles 1h, and for funding.
  - `test_declaration_order_is_independent_of_need_order`: needs candles 4h, candles 1h, open interest 300 000, funding; for every `itertools.permutations` of them `Declaration(p).needs == (candles 1h, candles 4h, open interest, funding)` and all declarations are equal with equal hashes; `Declaration(())` is valid and has `needs == ()`.
  - `test_union_keeps_the_longest_lookback_per_series`: candles 1h over 100 h and over 500 h give exactly `Declaration((InputNeed(CANDLES, H, 500 * H),))`; candles 1h and 4h both appear; funding declared by one declaration only appears with its lookback; plus the three cases of Review Focus 3.
  - `test_union_is_independent_of_declaration_order`: four declarations overlapping on candles 1h and funding; every permutation gives the same `Declaration`; `union(())` equals `Declaration(())`.
  - `test_union_refuses_malformed_input`: a `list` of declarations; a tuple holding an `InputNeed`; a tuple holding `None`.
  - `test_requirements_are_in_code_point_key_order`: input `(("b", d1), ("a", d2), ("b", d3))` gives `list(result) == ["a", "b"]`, `result["b"] == union((d1, d3))`, `result["a"] == d2`; keys `"B"` and `"a"` order as `["B", "a"]`.
  - `test_requirements_never_combine_two_instruments`: candles 1h over 100 h on `"A"` and over 500 h on `"B"` keep their own lookbacks.
  - `test_requirements_edge_inputs` (Review Focus 4).
  - `test_requirements_refuse_malformed_input`: a `list`; an element that is a `list`, a tuple of length one or three; key `""`, `1`, a `str` subclass instance; value `None` or an `InputNeed`.
  - `test_new_types_are_final_and_immutable_declaration`: subclassing `InputNeed`, `Declaration` and `InputKind` raises `TypeError`; assigning a field of a need or a declaration raises `dataclasses.FrozenInstanceError`; neither has `__dict__`.

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest tests/domain/test_declaration.py -q`
Expected: collection error, `ModuleNotFoundError: sentaris_engine.domain.declaration`.

- [ ] **Step 3: Implement `src/sentaris_engine/domain/declaration.py`** with the interfaces above, spec 5.1 to 5.3, 5.6, 5.7 and rulings R1 to R5. `InputKind` is `@final` like `FaultCause` in `src/sentaris_engine/application/execution.py`. `InputNeed.__post_init__` checks `input` first, then `series` by kind, then `lookback`. `union` and `requirements` check their whole input before building anything; neither keeps anything between calls.

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest tests/domain/test_declaration.py -q && uv run ruff check src/sentaris_engine/domain/declaration.py tests/domain/test_declaration.py && uv run mypy src/sentaris_engine/domain/declaration.py tests/domain/test_declaration.py`
Expected: all tests pass; ruff and mypy report no issues.

- [ ] **Step 5: Run the gate and commit**

Run: `make check`
Expected: passes; the test count is SE-6's 2274 plus this task's.

```bash
git add src/sentaris_engine/domain/declaration.py tests/domain/test_declaration.py
git commit -m "feat: SE-7a input needs, declarations and their union"
```

**Completion condition:** AC-1, AC-2, AC-3, AC-6, AC-7 and the `InputNeed`/`Declaration`/`InputKind` part of AC-8 are shown by the tests named above; `make check` passes.

---

### Task 2: `declare` on the contracts and forming a declaration

**Implementer model:** `sonnet` (mirrors SE-4's `evaluate_stateless` and `NotAnOutcome`; the test-strategy edits are mechanical).

**Files:**
- Modify: `src/sentaris_engine/domain/strategy.py` (both contract classes)
- Create: `src/sentaris_engine/domain/declaring.py`
- Test: `tests/domain/test_declaring.py`
- Modify: `tests/domain/test_strategy.py` (`test_contract_signatures_take_only_the_transition_inputs_contracts`, `test_contract_requires_evaluate_and_identity`, new test)
- Modify: `tests/domain/strategy_helpers.py`, `tests/domain/test_evaluation.py`, `tests/application/execution_helpers.py`, `tests/application/test_execution.py`
- Modify: `CLAUDE.md` ("Current state")

**Interfaces:**
- Consumes: Task 1's `Declaration`, `InputNeed`, `InputKind`; `Parameters`; `EvaluationFailure`; `NotAnOutcome` (tests only).
- Produces:
  - On `StatelessStrategy` and `StatefulStrategy`: `@abstractmethod def declare(self, parameters: Parameters) -> Declaration | EvaluationFailure: ...`
  - `class NotADeclaration`: field `returned_type: type` (`repr=False`), shaped exactly as `NotAnOutcome`.
  - `def declare_inputs(strategy: StatelessStrategy | StatefulStrategy, parameters: Parameters) -> Declaration | EvaluationFailure | NotADeclaration`

- [ ] **Step 1: Write the failing tests.**

  In `tests/domain/test_strategy.py`:
  - Extend `test_contract_signatures_take_only_the_transition_inputs_contracts`: `expected = frozenset({"identity", "evaluate", "declare"})`.
  - `test_declare_signature_takes_only_the_parameters`: for both contracts, `list(inspect.signature(C.declare).parameters) == ["self", "parameters"]`, each `POSITIONAL_OR_KEYWORD` with no default.
  - `test_strategy_without_declare_cannot_be_instantiated`: `StatelessOnlyEvaluateAndIdentity` and `StatefulOnlyEvaluateAndIdentity`, defined in the test body, each `raises_exactly(TypeError, ...)` on instantiation.
  - In `test_contract_requires_evaluate_and_identity`, the four "only X" classes and the two `...WithProperty` classes gain `declare` (R6), so each still fails, or succeeds, for the reason it names.

  In `tests/domain/test_declaring.py`: a recording strategy, defined here as a subclass of `MinimalStateless` (so `identity` and `evaluate` exist) that overrides only `declare`, stores each call's `args` and `kwargs` and returns a given value; a stateful twin subclasses `MinimalStateful` the same way. Hostile objects follow the SE-4 helpers in `tests/domain/test_evaluation.py` (`_ClaimsToBeStateless`, `test_virtual_subclass_is_refused`, `_Explosive`, `_Hostile`, `test_not_an_outcome_repr_runs_no_strategy_code`).
  - `test_declare_inputs_passes_only_the_parameters`: one call, `args == (params,)` with `args[0] is params`, `kwargs == {}`.
  - `test_declare_inputs_returns_a_declaration_as_the_very_object` and `test_declare_inputs_returns_an_evaluation_failure_as_the_very_object` (`EvaluationFailure("bad_lookback")`): `result is` the returned object.
  - `test_declare_inputs_reports_a_non_declaration_by_type_only`, parametrised over `None`, `NoSignal()`, a `Signals` of one signal, `StateTransition(NoSignal(), NO_STATE)`, the four values of Review Focus 5, and two hostile values built in the test body or as `pytest.param(..., id=...)`: an object whose `__class__` property claims `Declaration` (and one claiming `EvaluationFailure`) and whose `__eq__`, `__hash__`, `__bool__` and `__repr__` raise `AssertionError`; and an object whose metaclass claims equality and subclass membership with everything. In every case `type(result) is NotADeclaration`, `result.returned_type is` the value's real class (`type(value)`), and the result has no attribute holding the value (`dataclasses.fields(result)` is exactly `returned_type`).
  - `test_declare_inputs_propagates_an_exception_unchanged`: a `declare` raising a prebuilt `ValueError`; the caught object `is` it.
  - `test_declare_inputs_does_not_read_identity`: a strategy whose `identity` property raises `AssertionError` (as `_UnreadableIdentity` in `tests/domain/test_evaluation.py`) still returns its declaration.
  - `test_declare_inputs_refuses_malformed_inputs_without_calling_declare`: strategy candidates `object()`, the class `MinimalStateless` itself, an instance of a plain class with a `declare` method, an object whose `__class__` property claims `StatelessStrategy` (and one claiming `StatefulStrategy`), an instance of a class made a virtual subclass through `ABCMeta.register(StatelessStrategy, X)`, and an instance of a class whose metaclass fakes `__mro__` to include a contract; parameters `{"k": 7}` and an instance of a `collections.abc.Mapping` subclass, given to a recording strategy. Each raises `raises_exactly(EvaluationTypeError, ...)`. Every candidate that has a `declare` records its calls, and every such log, including the recording strategy's, stays empty.
  - `test_declare_inputs_serves_both_contracts` (Review Focus 1).
  - `test_new_types_are_final_and_immutable_declaring`: as `test_new_types_are_final_and_frozen_evaluation` in `tests/domain/test_strategy.py`, for `NotADeclaration`; `NotADeclaration(1)` raises `EvaluationTypeError`; `NotADeclaration(int) != NotADeclaration(int)` (identity equality); `repr(NotADeclaration(C))` for a class `C` whose metaclass `__repr__` raises `AssertionError` does not raise (`repr=False`).

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest tests/domain/test_strategy.py tests/domain/test_declaring.py -q`
Expected: `test_declaring.py` fails to import `sentaris_engine.domain.declaring`; the extended contract tests fail on the missing `declare`.

- [ ] **Step 3: Add `declare` to both contracts** in `strategy.py`, after `evaluate`, with a docstring citing section 6.9 and 6.8. `strategy.py` imports `Declaration` and `Parameters` at module level (no `TYPE_CHECKING`).

- [ ] **Step 4: Implement `src/sentaris_engine/domain/declaring.py`**: spec 5.5 steps 1 to 5, in the shape of `evaluate_stateless` and `NotAnOutcome` in `evaluation.py`. The strategy check accepts either contract via `type.__subclasscheck__`; the parameters check is `type(parameters) is Parameters`; the returned value is bound as `value: object`; there is no `try`.

- [ ] **Step 5: Give every test strategy a `declare`** (R6). Find them with `grep -rnE "StatelessStrategy\)|StatefulStrategy\)|_ContractMeta" tests`; indirect subclasses inherit `declare` from their base. The namespace passed to `ABCMeta.__new__(_ContractMeta, "Both", ...)` in `tests/application/test_execution.py` gains a `declare` too, so that object is still refused for holding both roots and not for being abstract. Classes that exist only to fail at definition (for example the `_define_*` helpers in `test_strategy.py`) are left as they are.

- [ ] **Step 6: Run the tests and see them pass**

Run: `uv run pytest tests/domain tests/application -q && uv run ruff check src tests && uv run mypy src tests`
Expected: all tests pass; ruff and mypy report no issues.

- [ ] **Step 7: Update `CLAUDE.md` "Current state"**: SE-7a exists; it is the input declaration in `sentaris_engine.domain` (`declaration`, `declaring`) and the `declare` method of both contracts; nothing calls `declare_inputs` yet (SE-7b).

- [ ] **Step 8: Run the gate and commit**

Run: `make check`
Expected: passes; `lint-imports` reports both contracts kept.

```bash
git add src/sentaris_engine/domain/strategy.py src/sentaris_engine/domain/declaring.py tests CLAUDE.md
git commit -m "feat: SE-7a declare on the strategy contracts and declare_inputs"
```

**Completion condition:** AC-4, AC-5 and the `NotADeclaration` part of AC-8 are shown by the tests named above; every SE-4 and SE-5 test still passes unchanged in what it asserts; `make check` passes (AC-9).

---

## Spec coverage

| Spec | Task |
|---|---|
| 3 items 1, 6; 5.1 to 5.3, 5.6, 5.7; AC-1 to AC-3, AC-6, AC-7 | 1 |
| 3 items 2 to 5, 7; 5.4, 5.5; AC-4, AC-5 | 2 |
| AC-8 | 1 (`InputKind`, `InputNeed`, `Declaration`), 2 (`NotADeclaration`) |
| AC-9 | 1, 2 (gate at each commit) |
| Section 8, every row | the test of the same name in Task 1 or 2; `test_new_types_are_final_and_immutable` is split into `..._declaration` and `..._declaring` |
