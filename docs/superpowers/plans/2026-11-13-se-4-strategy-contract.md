# SE-4 Strategy Contract and Stateless Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. In this project the lifecycle is `/slice SE-4` (`.claude/skills/slice/SKILL.md`), and its rules override the sub-skill.

**Goal:** Build strategy identity, the stateless and stateful contracts, the absent-state marker, the stateful outcome type, and the evaluation of one stateless strategy for one context as a pure pass-through.

**Architecture:** Two pure modules under `sentaris_engine.domain`. `strategy.py` holds the types a strategy codes against: `StrategyIdentity`, the two contract ABCs sharing one metaclass that refuses virtual subclasses and double membership, `NoState`/`NO_STATE` and `StateTransition`. `evaluation.py` holds `NotAnOutcome` and `evaluate_stateless`, which checks its arguments, calls the strategy once and returns its outcome unchanged, wrapping anything else in a new `NotAnOutcome` and catching nothing.

**Tech Stack:** Python 3.12, stdlib only (`abc`, `dataclasses`, `typing`); pytest, mypy strict and ruff, as set up in SE-1.

**Spec:** `docs/superpowers/specs/2026-11-13-se-4-strategy-contract-design.md` (revision 4, approved with its section 13; 5.4 step 4 amended 2026-11-13 under R1). "Spec 5.4" and "N4" below refer to that document. The domain document is `docs/domain.md`.

**Revision:** 3, approved by the user (2026-11-13). Revision 1 was reviewed by Opus (`slice-reviewer`: approved with changes; 1 HIGH, 3 MEDIUM, 7 LOW); revision 2 addressed every finding. Revision 3 follows the user's review: R1 approved and written into spec 5.4 step 4; one real-inheritance check for both contract membership and `NotAnOutcome`; the reach of the determinism tests stated.

## Global Constraints

- Production imports come only from `abc`, `dataclasses`, `typing` (all in the pinned `PURE_STDLIB`) and `sentaris_engine.domain`. No list in `tests/architecture/` changes, and no dependency is added. Tests may also use `copy` and `inspect`.
- **Exact types.** Check types with `type(v) is X`, never `isinstance` or `issubclass`, which accept virtual subclasses and read a spoofed `__class__`.
- **Real inheritance.** Where a check must accept subclasses, it is one call, `type.__subclasscheck__(base, type(obj))`, which walks the real MRO of the object's own type and ignores the `abc` registry, a claimed `__class__` and a metaclass that overrides `__mro__`. It is used in exactly two places: contract membership (`base` = `StatelessStrategy`, spec 5.2) and `NotAnOutcome` (`base` = `type`, R1). The outcome check is three separate `type(value) is X` comparisons: no `in`, no tuple, set or dict membership, because those call the metaclass's `__eq__`/`__hash__` (strategy code).
- **Errors.** Malformed arguments to the SE-4 value types and to `evaluate_stateless` raise exactly SE-3's `EvaluationTypeError`. No new error class. A subclass definition of a final type, a class deriving from both contracts, and `register` on a contract raise `TypeError`.
- **Final and frozen.** Value types use `@final`, `@dataclass(frozen=True, slots=True)` (with `eq=False` where stated), validation in `__post_init__`, and an `__init_subclass__` that raises `TypeError`, exactly as SE-3's `result.py`. The two contract classes are not final.
- **No `try` in `evaluation.py`.** `evaluate_stateless` contains no `try`, `except`, `finally` or `with` (spec 5.4 step 5). It never calls `isinstance`, `==`, `hash`, `bool`, `repr`, `str` or any attribute on the returned value; it uses `type(value)` only.
- **Tests** assert exception classes through `raises_exactly` from `tests/domain/evaluation_helpers.py`, never messages. Propagation tests assert the caught object with `is`.
- **Every task** runs its own RED/GREEN cycle, its focused tests, `make check` and one commit. Task 2 does not edit `strategy.py`. Test strategies live under `tests/` only; nothing is added under `sentaris_engine.strategies` (spec scope item 3).
- **Intentional type misuse** in tests gets a narrow `# type: ignore[<code>]`.
- **Comments** cite rules by ID (`DR-26`, `U2`, `OD-19`); they do not restate them.
- **Documents.** `docs/domain.md` changes only in Task 1, with exactly the six edits of spec section 13. `docs/roadmap.md` does not change. `CLAUDE.md` changes only in Task 2 ("Current state").

## Rulings made in this plan (implementation only)

- **R1 (approved by the user, 2026-11-13; now spec 5.4 step 4). `NotAnOutcome.returned_type`** accepts any genuine class, whatever its metaclass: `type.__subclasscheck__(type, type(returned_type))`. An object that only claims to be a class through `__class__` is refused. The earlier wording "an exact `type` instance" would have made a returned `Enum` member or strategy instance raise, contradicting "raises nothing".
- **R2. `NotAnOutcome` uses `eq=False`** (identity equality, identity hash). Value equality would compare and hash the held class, which runs metaclass code a strategy controls (spec 5.6). No SE-4 test compares two `NotAnOutcome`s.
- **R3. `NoState()` returns `NO_STATE`** (spec 5.3 leaves "returns or raises" to the builder and prefers "returns").

## Review Focus

1. **A returned value whose class has a hostile metaclass:** the metaclass's `__eq__` returns `True`, its `__hash__` returns `hash(Signals)`, its `__instancecheck__` and `__subclasscheck__` return `True`, and its `__repr__` raises `AssertionError`. An `in`- or set-based outcome check would pass it off as an outcome. `evaluate_stateless` returns a new `NotAnOutcome` whose `returned_type is` that class, and nothing raises. Test `test_non_outcome_with_hostile_metaclass_is_reported` (Task 2).
2. **A returned value that lies or explodes on touch:** an object whose `__class__` property returns `Signals`, and whose `__eq__`, `__hash__`, `__bool__` and `__repr__` raise `AssertionError`. An `isinstance`-based check would return it as an outcome. `evaluate_stateless` returns a `NotAnOutcome` holding the real class and touches nothing. Test `test_non_outcome_value_is_not_touched` (Task 2). In the same task, `test_non_outcome_of_any_metaclass_is_reported` covers benign metaclasses (an `Enum` member, a `StatelessStrategy` instance) under R1.
3. **Membership that is not real inheritance:** after `ABCMeta.register(StatelessStrategy, Plain)`, which bypasses the override, and for an instance of a class whose metaclass defines a `__mro__` property claiming `StatelessStrategy`, `evaluate_stateless` raises exactly `EvaluationTypeError` without calling `evaluate`. Test `test_virtual_subclass_is_refused` (Task 2).
4. **Indirect inheritance:** a subclass of a concrete test strategy is accepted by `evaluate_stateless`; a class deriving from a concrete stateless strategy and from `StatefulStrategy` is refused at definition. Tests `test_indirect_subclass_is_accepted` (Task 2) and a case in `test_strategy_cannot_take_both_contracts` (Task 1).
5. **The identity is never read:** a strategy whose `identity` property raises is still evaluated normally (spec 5.4 step 6). Test `test_identity_is_not_read` (Task 2).

**Reach of the determinism tests (N7, spec section 9).** `test_repeated_stateless_evaluation_is_identical` shows that the three chosen test strategies give identical results through `evaluate_stateless`, and `test_determinism_check_detects_a_varying_strategy` shows that the check catches the included `VaryingStrategy`. Neither proves purity or determinism for an arbitrary strategy; that stays the static check for `sentaris_engine.strategies` (SE-1) and review. Test docstrings and the slice report say so.

---

## File structure

| File | Task | Responsibility |
|---|---|---|
| `src/sentaris_engine/domain/strategy.py` | 1 | `StrategyIdentity`, `StatelessStrategy`, `StatefulStrategy`, `NoState`, `NO_STATE`, `StateTransition`. |
| `src/sentaris_engine/domain/evaluation.py` | 2 | `NotAnOutcome`, `evaluate_stateless`. |
| `tests/domain/strategy_helpers.py` | 1, 2 | Test strategies and builders. Task 1: `MinimalStateless`, `MinimalStateful`, `IDENTITY`. Task 2: `make_context`, `ReturningStrategy`, `RaisingStrategy`, `ContextSignalStrategy`, `VaryingStrategy`, `check_deterministic`. |
| `tests/domain/test_strategy.py` | 1, 2 | Task 1: N1, N2 (contracts), N3, N10, N11, N12 (`_strategy`). Task 2: N11's `NotAnOutcome` case and N12 (`_evaluation`) as new functions. |
| `tests/domain/test_evaluation.py` | 2 | N2 (`evaluate_stateless`), N4 to N9, Review Focus 1 to 5. |
| `docs/domain.md` | 1 | Spec section 13, edits 1 to 6, verbatim. |
| `CLAUDE.md` | 2 | "Current state": SE-4 exists. |

## Interfaces (whole slice)

```python
# strategy.py
@final @dataclass(frozen=True, slots=True)
class StrategyIdentity:
    id: str          # non-empty exact str, nothing else checked (surrogates allowed)
    version: str     # same

class _ContractMeta(ABCMeta): ...   # register -> TypeError; a class with both contracts in its MRO -> TypeError

class StatelessStrategy(metaclass=_ContractMeta, contract=True):
    @property
    @abstractmethod
    def identity(self) -> StrategyIdentity: ...
    @abstractmethod
    def evaluate(self, context: EvaluationContext) -> Result: ...

class StatefulStrategy(metaclass=_ContractMeta, contract=True):
    @property
    @abstractmethod
    def identity(self) -> StrategyIdentity: ...
    @abstractmethod
    def evaluate(self, context: EvaluationContext, previous_state: object) -> StateTransition: ...

@final
class NoState: ...   # __slots__ = (); __new__ returns the singleton (kept in a class variable); __copy__/__deepcopy__ return self
NO_STATE: Final[NoState]

@final @dataclass(frozen=True, slots=True, eq=False)
class StateTransition:
    result: Result       # exactly Signals, NoSignal or EvaluationFailure
    next_state: object   # anything, NO_STATE and None included; held as given

# evaluation.py
@final @dataclass(frozen=True, slots=True, eq=False)
class NotAnOutcome:
    returned_type: type  # a genuine class of any metaclass (R1, spec 5.4 step 4)

def evaluate_stateless(strategy: StatelessStrategy, context: EvaluationContext) -> Result | NotAnOutcome: ...
```

---

### Task 1: Strategy types and the domain document changes

**Implementer:** `sonnet`. Small types whose shape the plan pins; the metaclass behavior is fully specified by the tests below.

**Files:** the Task 1 rows of the file structure table.

**Scope:** spec 5.1, 5.2, 5.3, 5.5; the parts of spec 5 (exact types, immutable, final, errors) that apply to them; spec section 13, edits 1 to 6.

**Interfaces:**
- Consumes `EvaluationContext`, `Signals`, `NoSignal`, `EvaluationFailure`, `Result`, `EvaluationTypeError`, `Parameters`, `FrozenMapping`, `PayloadError`, and the test helpers `raises_exactly`, `UNEXPECTED_VALUES`, `UNEXPECTED_IDS`.
- Produces the `strategy.py` names of the interfaces block, and in `strategy_helpers.py`:
  - `IDENTITY = StrategyIdentity("test", "1")`;
  - `MinimalStateless(StatelessStrategy)`: `identity = IDENTITY`, `evaluate` returns `NoSignal()`;
  - `MinimalStateful(StatefulStrategy)`: `identity = IDENTITY`, `evaluate` returns `StateTransition(NoSignal(), previous_state)`.

- [ ] **Step 1: Write the failing tests in `tests/domain/test_strategy.py`**

  - `test_invalid_strategy_identity_is_refused` (N1), parametrised over field (`id`, `version`) and value: `""`, `None`, `1`, `b"x"`, a `str` subclass instance, and every `UNEXPECTED_VALUES` entry except `"1"` (valid here). Each raises exactly `EvaluationTypeError`; the other field is `"x"`.
  - `test_strategy_identity_accepts_any_non_empty_str` (N1 positive): `StrategyIdentity("a b", "\ud800")` constructs; `StrategyIdentity("a", "1") == StrategyIdentity("a", "1")` with equal hashes; `StrategyIdentity("a", "1") != StrategyIdentity("a", "2")`; `StrategyIdentity("a", "1") != ("a", "1")`; `StrategyIdentity("a", "1") < StrategyIdentity("b", "1")` raises `TypeError` (no ordering, spec 5.1).
  - `test_contract_signatures_take_only_the_transition_inputs_contracts` (N2): for `inspect.signature(StatelessStrategy.evaluate)` the parameter names are exactly `["self", "context"]`, for `StatefulStrategy.evaluate` exactly `["self", "context", "previous_state"]`; every parameter is `POSITIONAL_OR_KEYWORD` with no default. `StatelessStrategy.__abstractmethods__ == StatefulStrategy.__abstractmethods__ == frozenset({"identity", "evaluate"})`.
  - `test_strategy_cannot_take_both_contracts` (N3): defining `class C(StatelessStrategy, StatefulStrategy)`, `class C(StatefulStrategy, StatelessStrategy)` and `class C(MinimalStateless, StatefulStrategy)` each raises exactly `TypeError`; `StatelessStrategy.register(X)` and `StatefulStrategy.register(X)` for a plain class `X` raise exactly `TypeError`. Positive twin: `MinimalStateless` and `MinimalStateful` exist and instantiate.
  - `test_contract_requires_evaluate_and_identity` (N3): for each contract, a subclass defining only `evaluate`, and one defining only `identity`, raises `TypeError` on instantiation. Positive twin: a subclass providing `identity` as a property instead of a class attribute instantiates.
  - `test_no_state_marker` (N10): `NO_STATE is not None`; `NO_STATE != x` for `x` in `None`, `False`, `0`, `""`, `()`; `hash(NO_STATE)` works and `{NO_STATE: 1}[NO_STATE] == 1`; `NoState() is NO_STATE`; `copy.copy(NO_STATE) is NO_STATE`; `copy.deepcopy(NO_STATE) is NO_STATE` and `copy.deepcopy([NO_STATE])[0] is NO_STATE`; defining a subclass of `NoState` raises exactly `TypeError`; `FrozenMapping({"a": NO_STATE})` raises exactly `PayloadError`; `Parameters({"a": NO_STATE})` raises exactly `EvaluationTypeError`.
  - `test_state_transition` (N11): `result` as `None`, a `Signal`, a `tuple` of `Signal`, a `list`, the class `NoSignal`, `NO_STATE`, a `StateTransition`, `ValueError("x")`, `True`, and every `UNEXPECTED_VALUES` entry raises exactly `EvaluationTypeError`. For `next_state` in `NO_STATE`, `None`, a `dict` `d` and `object()`, `StateTransition(NoSignal(), s).next_state is s`, and `d` is unchanged; each of the three outcome types is accepted as `result` and held with `is`. Two transitions built from the same arguments compare unequal (`eq=False`).
  - `test_new_types_are_final_and_frozen_strategy` (N12): defining a subclass of `StrategyIdentity`, `StateTransition` or `NoState` raises exactly `TypeError`; assigning `id`, `version`, `result` or `next_state` raises `dataclasses.FrozenInstanceError`; `setattr(NO_STATE, "x", 1)` raises `AttributeError`; `not hasattr(x, "__dict__")` for an identity, a transition and `NO_STATE`; `dataclasses.replace(identity, id="")` raises exactly `EvaluationTypeError`.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/domain/test_strategy.py -q`
  Expected: collection error, `sentaris_engine.domain.strategy` does not exist.

- [ ] **Step 3: Implement `src/sentaris_engine/domain/strategy.py` and the Task 1 part of `tests/domain/strategy_helpers.py`**

  - `_ContractMeta(ABCMeta)`: `register(cls, subclass)` raises `TypeError` (a signature mypy accepts as an override, e.g. returning `NoReturn`). `__new__(mcls, name, bases, namespace, contract: bool = False)` records a class created with `contract=True` in a private class-level tuple of root contracts; for any other class it counts the root contracts in the new class's `__mro__` by `is` (no `in`, no `globals()`, which is a forbidden call) and raises `TypeError` when the count is 2.
  - The contract docstrings cite DR-26, DR-22, DR-12 and section 6.8 by ID (spec 5.2).
  - `NoState.__new__` returns the singleton held in a class variable, creating it on the first call; `NO_STATE = NoState()`. `__init_subclass__`, `__copy__` and `__deepcopy__` as in the interfaces block. Add nothing for pickling, neither support nor refusal (no `__reduce__`); it is untested (spec 5.3, OD-20). A `__repr__` is optional convenience and is not tested.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: the command from Step 2, then `uv run pytest tests/domain -q`. Expected: all pass.

- [ ] **Step 5: Apply spec section 13 to `docs/domain.md`**

  Apply edits 1 to 6: replace each quoted "before" text by its "after" text, or insert at the given place. Each anchor occurs exactly once; the orchestrator checked this when writing the plan. The texts of edits 2 and 4 are indented code blocks in the spec; insert them without that indentation. Change nothing else.

  Verify: `git diff --stat docs/` shows only `docs/domain.md`; `git diff docs/` contains exactly the six edits, character for character.

- [ ] **Step 6: Run the gate and commit**

  Run: `make check`. Expected: ruff, mypy and lint-imports clean; the final pytest line reports `passed` with no failures.

  ```bash
  git add src/sentaris_engine/domain/strategy.py tests/domain docs/domain.md
  git commit -m "feat: SE-4 strategy identity, contracts and state types"
  ```

**Completion condition:** AC-1, AC-2 (contract part), AC-3, AC-7 and the Task 1 part of AC-8 hold; `make check` passes; the `docs/` diff is exactly edits 1 to 6.

---

### Task 2: Stateless evaluation

**Implementer:** `opus`. The task is small but carries the slice's subtle guarantees: the outcome passes through untouched (DR-23), nothing of the returned value but its type is read, no exception is caught or chained, and the determinism check must itself be shown to work (slice skill, rule 4: determinism).

**Files:** the Task 2 rows of the file structure table.

**Scope:** spec 5.4, the `NotAnOutcome` case of 5.5 (N11), spec section 6, the Review Focus tests, scope item 5 (`CLAUDE.md`).

**Interfaces:**
- Consumes everything Task 1 produces, plus `snapshot` from `tests/domain/row_builders.py`, `Signal`, `FrozenMapping`, `Parameters`.
- Produces `NotAnOutcome` and `evaluate_stateless` (interfaces block), and in `strategy_helpers.py`:
  - `make_context(as_of: int = 10_000_000) -> EvaluationContext`: a fresh `snapshot(as_of)`, `Parameters({"k": 7})`, `as_of`; every call builds new objects with the same field values;
  - `ReturningStrategy(value: object)`: stateless, returns `value` every call, appends each received context to `self.calls: list[EvaluationContext]`;
  - `RaisingStrategy(exc: BaseException)`: stateless, raises the given object (`raise self.exc`), appending to `calls`;
  - `ContextSignalStrategy`: stateless, deterministic, returns `Signals((Signal("seen", FrozenMapping({"as_of": context.as_of, "k": context.parameters["k"]})),))` and records `calls`;
  - `VaryingStrategy`: stateless, returns a `Signals` whose payload holds a call counter incremented on each call;
  - `check_deterministic(strategy: StatelessStrategy, contexts: Sequence[EvaluationContext], repeats: int = 3) -> None`: evaluates each context `repeats` times through `evaluate_stateless` and raises `AssertionError` unless every result, across all contexts and repeats, `==` the first result of the first context.

- [ ] **Step 1: Write the failing tests**

  **`tests/domain/test_evaluation.py`**
  - `test_contract_signatures_take_only_the_transition_inputs_evaluation` (N2): `inspect.signature(evaluate_stateless)` parameter names are exactly `["strategy", "context"]`, both `POSITIONAL_OR_KEYWORD` without default.
  - `test_non_outcome_result_is_reported_as_value` (N4), parametrised over `None`, `Signal(...)`, `(Signal(...),)`, `[]`, the class `NoSignal`, `StateTransition(NoSignal(), NO_STATE)`, `NO_STATE`, `ValueError("x")`, `True`, and `NotAnOutcome(int)`: `r = evaluate_stateless(ReturningStrategy(v), make_context())` raises nothing; `type(r) is NotAnOutcome`; `r.returned_type is type(v)` (for the self-built case `NotAnOutcome`, not `int`); `r is not v`.
  - `test_not_an_outcome_is_validated` (N4): `NotAnOutcome(None)`, `NotAnOutcome("int")`, `NotAnOutcome(1)` and `NotAnOutcome(<an object of a plain class whose __class__ property returns type>)` raise exactly `EvaluationTypeError`; positive twins (R1): `NotAnOutcome(int)`, `NotAnOutcome(MinimalStateless)` and `NotAnOutcome(<a test Enum class>)` hold the given class with `is`.
  - `test_strategy_exception_propagates_unchanged` (N5), parametrised over `ValueError("v")`, `EvaluationTypeError("e")`, `KeyboardInterrupt()`, `SystemExit(3)` and an instance of a test-defined `class _Direct(BaseException)`. Before raising, each exception gets `__cause__` set to `RuntimeError("cause")` and `__context__` to `RuntimeError("ctx")` (distinct exception instances; `object()` is not assignable). `RaisingStrategy` raises outside any `except` block, so the pre-set `__context__` is not replaced. Caught with `pytest.raises(BaseException)`: `info.value is exc`, `info.value.__cause__ is cause`, `info.value.__context__ is ctx`, and the strategy's `calls` has length 1.
  - `test_malformed_evaluation_arguments_are_refused` (N6): `strategy` as `MinimalStateful()`, the class `MinimalStateless` itself, a plain object with an `evaluate` method, a function, `None`, and an object of a plain class whose `__class__` property returns `StatelessStrategy`; `context` as `None`, `snapshot()`, `{}`, and an object of a plain class whose `__class__` property returns `EvaluationContext`, with a `ReturningStrategy(NoSignal())` as strategy. Each raises exactly `EvaluationTypeError`. Every object with an `evaluate` method in these cases records its calls (the plain object and the spoofed-`__class__` object get a recording `evaluate`), and every `calls` list is empty afterwards.
  - `test_evaluate_is_called_positionally` (spec 5.2, 5.4 step 2): a stateless test strategy with `def evaluate(self, ctx, /)` (`# type: ignore[override]`) is evaluated and its outcome returned with `is`.
  - `test_repeated_stateless_evaluation_is_identical` (N7), parametrised over `ContextSignalStrategy()`, `ReturningStrategy(NoSignal())` and `ReturningStrategy(EvaluationFailure("f"))`: `check_deterministic(s, [c])` and `check_deterministic(s, [make_context(), make_context()])` pass. Its docstring states the reach given under Review Focus: these test strategies only.
  - `test_determinism_check_detects_a_varying_strategy` (N7): `check_deterministic(VaryingStrategy(), [make_context()])` raises `AssertionError`. Its docstring states that it validates the check against this one varying strategy.
  - `test_outcome_is_returned_unchanged` (N8): for each of `Signals((Signal("zz", …), Signal("mm", …), Signal("aa", …)))`, `NoSignal()` and `EvaluationFailure("f")`, `evaluate_stateless(ReturningStrategy(o), c) is o`; for the `Signals` case `r.signals is o.signals` and the kinds read `["zz", "mm", "aa"]`; `strategy.calls == [c]` with `calls[0] is c`.
  - `test_evaluation_is_independent_of_other_strategies` (N9): `a = ContextSignalStrategy()`; record `evaluate_stateless(a, c)` alone; then after B returning `EvaluationFailure("f")`, after B raising `ValueError` (caught by the test), and after B returning `None`; every A result `==` the first, and each A call received `c` itself (`is`).
  - `test_non_outcome_with_hostile_metaclass_is_reported` (Review Focus 1): as described there; `type(r) is NotAnOutcome` and `r.returned_type is` the hostile class.
  - `test_non_outcome_value_is_not_touched` (Review Focus 2): a returned object of a test class whose `__class__` property returns `Signals` and whose `__eq__`, `__hash__`, `__bool__` and `__repr__` each raise `AssertionError`; `type(r) is NotAnOutcome`, `r.returned_type` is that test class, and nothing raised.
  - `test_non_outcome_of_any_metaclass_is_reported` (Review Focus 2, R1): returning an `Enum` member and a `MinimalStateless()` instance gives a `NotAnOutcome` holding the member's enum class and `MinimalStateless`.
  - `test_virtual_subclass_is_refused` (Review Focus 3): both cases there, each a test-local class with a recording `identity` and `evaluate`; each raises exactly `EvaluationTypeError` and `calls` stays empty.
  - `test_indirect_subclass_is_accepted` (Review Focus 4): an instance of `class Sub(ReturningStrategy)` is evaluated and its outcome returned.
  - `test_identity_is_not_read` (Review Focus 5): a stateless test strategy whose `identity` property raises `AssertionError` returns its `NoSignal()` through `evaluate_stateless`.

  **`tests/domain/test_strategy.py`** (new functions only)
  - `test_state_transition_refuses_not_an_outcome` (N11): `StateTransition(NotAnOutcome(int), NO_STATE)` raises exactly `EvaluationTypeError`.
  - `test_new_types_are_final_and_frozen_evaluation` (N12): defining a subclass of `NotAnOutcome` raises exactly `TypeError`; assigning `returned_type` raises `dataclasses.FrozenInstanceError`; `not hasattr(NotAnOutcome(int), "__dict__")`; `dataclasses.replace(NotAnOutcome(int), returned_type=None)` raises exactly `EvaluationTypeError`.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/domain/test_evaluation.py tests/domain/test_strategy.py -q`
  Expected: collection errors in both files (`sentaris_engine.domain.evaluation` missing); Task 1's tests in other files still pass.

- [ ] **Step 3: Implement `src/sentaris_engine/domain/evaluation.py` and the Task 2 helpers**

  `NotAnOutcome.__post_init__` uses the real-inheritance check of Global Constraints with `base` = `type`. `evaluate_stateless` follows spec 5.4 steps 1 to 6 in order: the real-inheritance check with `base` = `StatelessStrategy`, then `type(context) is EvaluationContext`, then one positional call `strategy.evaluate(context)` bound to a variable annotated `object`, then three separate `if type(value) is X: return value` for `Signals`, `NoSignal`, `EvaluationFailure` (separate `if`s so mypy narrows; no `cast`), else `return NotAnOutcome(type(value))`. Obey the "No `try`" constraint. Docstrings cite DR-23, DR-26, DR-22 and section 6.7 by ID.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: the command from Step 2, then `uv run pytest tests/domain -q`. Expected: all pass.

- [ ] **Step 5: Update `CLAUDE.md` "Current state"**

  Name SE-4 next to SE-1 to SE-3 and state that SE-4 is the strategy contract and stateless evaluation in `sentaris_engine.domain` (`strategy`, `evaluation`). Change nothing else in the file.

- [ ] **Step 6: Run the gate and commit**

  Run: `make check`. Expected: all steps clean; the final pytest line reports `passed` with no failures.

  ```bash
  git add src/sentaris_engine/domain/evaluation.py tests/domain CLAUDE.md
  git commit -m "feat: SE-4 stateless evaluation"
  ```

**Completion condition:** AC-2 (evaluation signature), AC-4, AC-5, AC-6, AC-8 and AC-9 hold; the Review Focus tests pass; `make check` passes.

---

## Acceptance criteria → tests

| AC | Tests |
|---|---|
| AC-1 | `test_invalid_strategy_identity_is_refused`, `test_strategy_identity_accepts_any_non_empty_str` |
| AC-2 | `test_contract_signatures_take_only_the_transition_inputs_contracts`, `_evaluation`, `test_strategy_cannot_take_both_contracts`, `test_contract_requires_evaluate_and_identity` |
| AC-3 | `test_no_state_marker` |
| AC-4 | `test_outcome_is_returned_unchanged`, `test_non_outcome_result_is_reported_as_value`, `test_not_an_outcome_is_validated`, `test_strategy_exception_propagates_unchanged`, `test_malformed_evaluation_arguments_are_refused`, `test_evaluate_is_called_positionally` |
| AC-5 | `test_repeated_stateless_evaluation_is_identical`, `test_determinism_check_detects_a_varying_strategy` (for the included test strategies only; see "Reach of the determinism tests") |
| AC-6 | `test_evaluation_is_independent_of_other_strategies` |
| AC-7 | `test_state_transition`, `test_state_transition_refuses_not_an_outcome` |
| AC-8 | `test_new_types_are_final_and_frozen_strategy`, `test_new_types_are_final_and_frozen_evaluation` |
| AC-9 | `make check`, with `tests/architecture/test_purity.py` covering the two new modules unchanged |
