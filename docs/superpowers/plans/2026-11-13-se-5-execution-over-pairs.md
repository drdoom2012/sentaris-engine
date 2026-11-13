# SE-5 Execution over Pairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. In this project the lifecycle is `/slice SE-5` (`.claude/skills/slice/SKILL.md`), and its rules override the sub-skill.

**Goal:** One execution for one `as_of` over an explicit list of (stateless strategy, instrument) pairs with prebuilt snapshots: refuse malformed input as a whole, evaluate in `(instrument, id, version)` order, isolate a raising or non-outcome strategy to its own pair, and return one report entry per pair.

**Architecture:** One pure module, `sentaris_engine.application.execution`. Task 1 adds its value types (`Pair`, `FaultCause`, `StrategyFault`, `ReportEntry`, `ExecutionReport`), the refusal error and the safe type-name derivation. Task 2 adds `execute`, which runs spec 5.3 steps 1 to 8 on top of SE-4's `evaluate_stateless`.

**Tech Stack:** Python 3.12, stdlib only (`dataclasses`, `enum`, `typing`); pytest, mypy strict and ruff, as set up in SE-1.

**Spec:** `docs/superpowers/specs/2026-11-13-se-5-execution-over-pairs-design.md` (revision 4, approved with its section 13). "Spec 5.3" and "N4" below refer to that document. The domain document is `docs/domain.md`.

**Revision:** 2. Revision 1 was reviewed by Opus (`slice-reviewer`: approved with changes; 0 CRITICAL, 0 HIGH, 3 MEDIUM, 7 LOW; none needed the user). Revision 2 fixes all ten. The CPython behavior behind findings 1 and 3 (a `__qualname__` property in a metaclass body raises `TypeError`; `getattr(cls, "__name__", None)` propagates a metaclass `AssertionError`) was confirmed by a probe on Python 3.12.

## Global Constraints

- Production imports come only from `dataclasses`, `enum`, `typing` (all in the pinned `PURE_STDLIB`) and `sentaris_engine.domain`. No list in `tests/architecture/` changes and no dependency is added. Tests may use any stdlib module.
- **Exact types.** Check types with `type(v) is X`, never `isinstance` or `issubclass`. Where a check must accept subclasses (the `str` test of spec 5.5), use `type.__subclasscheck__(str, type(v))`, as SE-4 does.
- **No foreign code.** Production code never calls `==`, `!=`, `in`, `hash`, `bool`, `len`, `repr`, `str`, `format` or f-strings on a strategy, a key before it is checked, an exception, a returned value or anything read from them. Strategy objects are told apart by `id()` only; snapshot objects by `is`/`id()` only. Sets and dict lookups are used only on exact `str` and `int` values.
- **Descriptors.** MRO, qualname and module are read through `type`'s own descriptors: `type.__dict__["__mro__"].__get__(cls)`, `type.__dict__["__qualname__"].__get__(cls)`, `type.__dict__["__module__"].__get__(cls)`. Never `cls.__mro__`, `cls.__qualname__`, `cls.__module__`, `getattr` or `inspect`.
- **Errors.** Malformed input to a Task 1 value type raises exactly SE-3's `EvaluationTypeError`. Every refusal of `execute` raises exactly `ExecutionRefusedError`: `from exc` only where the strategy's `identity` read raised (spec 5.3 step 4), `from None` everywhere else (spec 5.4). A message never formats a caller value.
- **Final and frozen.** Value types use `@final`, `@dataclass(frozen=True, slots=True)` (`eq=False` only for `Pair`), validation in `__post_init__`, and an `__init_subclass__` that raises `TypeError`, as SE-3's `result.py` and SE-4's `strategy.py`.
- **One `try` around strategy evaluation.** In `execute`, the only `try` that can see a strategy's `evaluate` wraps exactly the `evaluate_stateless(...)` call; its handler is `except Exception`. The context is built before it and the fault after it (spec 5.3 step 7). The one other `try` around strategy code is the `identity` read (step 4); `qualified_type_name` may use one `try` for the `AttributeError` of the module descriptor.
- **Tests** assert exception classes through `raises_exactly` from `tests/domain/evaluation_helpers.py`, never messages. Propagation tests assert the caught object with `is`. "Nothing runs" means every recording strategy's log is empty.
- **Hostile values in tests.** pytest touches bare parameter values (id generation reads `__name__`; `isinstance(value, ParameterSet)` reads `__class__`). Every hostile class or object is therefore either built inside the test body or passed as `pytest.param(..., id="<case id>")`; never as a bare parametrize value.
- **mypy.** Descriptor reads through `type.__dict__[...]` are typed `Any`; bind them to annotated locals (`mro: tuple[type, ...]`, `module_value: object`, `qualname: str`) instead of adding ignores. Never `vars(type)` (`vars` is a forbidden call).
- **Test strategies** live under `tests/` only; nothing is added under `sentaris_engine.strategies`.
- **Intentional type misuse** in tests gets a narrow `# type: ignore[<code>]`; no unused ignore (strict mypy).
- **Comments** cite rules by ID (`DR-22`, section 6.7, `U2`, `OD-3`); they do not restate them.
- **Documents.** `docs/domain.md` changes only in Task 1, with exactly the two edits of spec section 13. `docs/roadmap.md` does not change. `CLAUDE.md` changes only in Task 2 ("Current state").

## Rulings made in this plan (implementation only)

- **R1. `qualified_type_name(cls: type) -> str`** is a public function of the execution module, so that Task 1 can test spec 5.5 directly and Task 2 through `execute`.
- **R2. Execution works on its own copy of `snapshots`.** Step 1 builds a new `dict[str, Snapshot]` from the checked entries, and every later step reads only that copy. A strategy holding a reference to the caller's dict, and changing it during the run, cannot then bypass the step 2 checks or make a later context fail. Copying the mapping copies no snapshot (section 6.7).
- **R3. `FaultCause` values** are `"raised"` and `"returned_non_outcome"`. Nothing reads them; they are fixed only so the enum has stable values.
- **R4. `Pair.strategy` is annotated `StatelessStrategy`** and not checked by `Pair` (spec 5.1). SE-14 widens it.
- **R5. Execution reads each `Pair` once** (review finding 4). Step 1 copies each pair's `instrument`, `strategy` and `parameters` into engine-held values (with R2), and steps 2 to 8 use only those, so a strategy that changes a `Pair` with `object.__setattr__` during the run changes nothing the engine holds.

## Review Focus

1. **The caller's `snapshots` dict changed during the run:** a strategy that holds the caller's dict, and in its `evaluate` deletes the other instrument's entry and inserts a surplus one, does not change the later pairs: they are evaluated with the snapshot objects given at the call, and a report is returned (R2). Test `test_snapshots_dict_changed_during_run_changes_nothing` (Task 2).
2. **A strategy class instead of an instance:** `Pair("A", MyStrategy, params)`, where `MyStrategy` is a `StatelessStrategy` subclass, is refused by `execute` with `ExecutionRefusedError`, and nothing runs. Case in `test_strategy_of_wrong_contract_is_refused` (Task 2).
3. **An exception that is hostile to inspection:** a raised exception whose `__str__`, `__repr__` and `__getattribute__` raise `AssertionError` is reported as `StrategyFault(RAISED, <its name>)`, and a report is returned. Case in `test_strategy_exception_is_isolated_to_its_pair` (Task 2).
4. **An outcome passes through as the very object:** for a `Signals` of three signals in non-sorted kind order, a `NoSignal` and an `EvaluationFailure`, `entry.outcome is` the returned object, and the `Signals` keeps its order. Test `test_outcome_is_reported_as_the_very_object` (Task 2).
5. **Nothing is kept between executions:** calling `execute` twice with the same pairs reads each strategy's `identity` once per call (two reads in total), and the second report equals the first. Case in `test_identity_is_read_once_and_checked` (Task 2).

Also covered, from the plan review: a strategy that changes a later `Pair`'s fields with `object.__setattr__` during its `evaluate` (R5; `test_snapshots_dict_changed_during_run_changes_nothing` gets this second case); a strategy that *returns* an exception object (N7); a strategy that raises `ExecutionRefusedError` from `evaluate`, which is a `RAISED` fault, not a refusal (N6).

---

## File structure

| File | Task | Responsibility |
|---|---|---|
| `src/sentaris_engine/application/execution.py` | 1, 2 | Task 1: `ExecutionRefusedError`, `Pair`, `FaultCause`, `StrategyFault`, `ReportEntry`, `ExecutionReport`, `qualified_type_name`. Task 2: `execute`. |
| `tests/application/__init__.py` | 1 | Package marker. |
| `tests/application/type_name_cases.py` | 1 | `type_name_cases(base: type) -> list[tuple[str, type, str, list[str]]]`: the N9 classes built on `base` (`object` or `Exception`), each with its case id, expected name and a log that must stay empty; it includes this module's `Twin` case. |
| `tests/application/type_name_other.py` | 1 | `type_name_cases(base: type)` with the same name, building only `Twin` on `base` the same way, so both Twins have the identical qualname `type_name_cases.<locals>.Twin` and differ only by module (N9, "different modules"). |
| `tests/application/test_execution_types.py` | 1 | N9 (direct), N12, N13. |
| `tests/application/execution_helpers.py` | 2 | Test strategies and builders for `execute`. |
| `tests/application/test_execution.py` | 2 | N1 to N8, N9 (through `execute`), N10, N11, Review Focus 1 to 5. |
| `docs/domain.md` | 1 | Spec section 13, edits 1 and 2, verbatim. |
| `CLAUDE.md` | 2 | "Current state": SE-5 exists. |

## Interfaces (whole slice)

```python
# src/sentaris_engine/application/execution.py
class ExecutionRefusedError(ValueError): ...   # spec 5.4

@final @dataclass(frozen=True, slots=True, eq=False)
class Pair:
    instrument: str                                   # check_instrument_key
    strategy: StatelessStrategy = field(repr=False)   # held as given, never touched (R4)
    parameters: Parameters                            # exact Parameters (U6); Pair(instrument, strategy, parameters)

@final
class FaultCause(Enum):
    RAISED = "raised"
    RETURNED_NON_OUTCOME = "returned_non_outcome"     # R3

@final @dataclass(frozen=True, slots=True)
class StrategyFault:
    cause: FaultCause        # exact FaultCause member
    type_name: str           # exact str, may be "" (U9)

type Outcome = Signals | NoSignal | EvaluationFailure | StrategyFault

@final @dataclass(frozen=True, slots=True)
class ReportEntry:
    instrument: str               # check_instrument_key
    strategy: StrategyIdentity    # exact StrategyIdentity
    outcome: Outcome              # exactly one of the four types

@final @dataclass(frozen=True, slots=True)
class ExecutionReport:
    as_of: int                          # check_instant
    entries: tuple[ReportEntry, ...]    # exact tuple of exact ReportEntry

def qualified_type_name(cls: type) -> str: ...   # spec 5.5 (R1)

def execute(as_of: int, pairs: tuple[Pair, ...], snapshots: dict[str, Snapshot]) -> ExecutionReport: ...  # Task 2
```

---

### Task 1: Execution value types, type names and the domain document changes

**Implementer:** `opus`. The value types are routine, but `qualified_type_name` is the subtle part of the slice's "no strategy code runs" guarantee: descriptor reads that bypass a metaclass, `str`-subclass conversion without running any subclass method, and the U9 fallback (slice skill, rule 4).

**Files:** the Task 1 rows of the file structure table.

**Scope:** spec 5.1, 5.2, 5.4 (the class), 5.5; spec section 13, edits 1 and 2.

**Interfaces:**
- Consumes `check_instrument_key`, `check_instant`, `Parameters`, `Snapshot`, `Signals`, `NoSignal`, `EvaluationFailure`, `StrategyIdentity`, `StatelessStrategy`, `NotAnOutcome`, `EvaluationTypeError`, and the test helpers `raises_exactly`, `MinimalStateless`, `IDENTITY`.
- Produces the Task 1 names of the interfaces block, and `type_name_cases` (file structure table). The classes are created inside `type_name_cases(base)`, so their real qualname starts with `type_name_cases.<locals>.`; each expected name is spelled from the defining module's `__name__` and that real qualname (for example `f"{__name__}.type_name_cases.<locals>.Outer.Inner"`), never hard-coded otherwise.

- [ ] **Step 1: Write the failing tests in `tests/application/test_execution_types.py`**

  - `test_type_name_is_module_qualified_and_safe` (N9, direct), parametrised over `type_name_cases(object)` and `type_name_cases(Exception)`: `qualified_type_name(cls) == expected` with `type(result) is str`, and the case's log is empty afterwards. `type_name_cases(base)` holds, each class deriving from `base`:
    - a nested class `Outer.Inner` → `"<module>.type_name_cases.<locals>.Outer.Inner"`;
    - `Twin` here and `Twin` in `type_name_other.py`, built on the same `base`, with identical qualnames and different module-qualified names (asserted for both bases in a separate small test, `test_same_name_in_two_modules_differs`; the other module's Twin is also a case of `test_type_names_through_execute`);
    - (a) a class whose metaclass `__getattribute__` logs and raises `AssertionError` for `__name__`, `__qualname__` and `__module__` → the real `"<module>.<qualname>"`;
    - (b) a class whose metaclass `__getattribute__` logs and returns lies for those three names, and whose metaclass body has lying `__name__` and `__module__` properties → the real `"<module>.<qualname>"`. A `__qualname__` property in a metaclass body is impossible (CPython raises `TypeError` at metaclass creation), so none is written;
    - a class whose `__qualname__` was set after creation to an instance of a `str` subclass with logging `__radd__`, `__add__` and `__str__` → the plain text, module-qualified;
    - a class whose body sets `__module__` to a `str` subclass instance `"mymod"` with logging `__len__`, `__bool__`, `__eq__`, `__hash__` and `__str__` → `"mymod.<qualname>"`;
    - classes whose body sets `__module__` to `42`, to a `property`, and to `""` → the qualname alone;
    - a class made by `exec('C = type("C", (base,), {})', {"base": base})` (globals without `__name__`, so no `__module__` is recorded) → `"C"`;
    - the same `exec` construction with name `""` → `""` (U9);
    - `type(None)` → `"builtins.NoneType"` and `ValueError` → `"builtins.ValueError"` (only for the matching `base`, or as two plain parametrised entries).
  - `test_pair_is_validated` (N12): `instrument` as `""`, `None`, `1` and a `str`-subclass instance; `parameters` as `{}`, `None` and `FrozenMapping({})`; each raises exactly `EvaluationTypeError`. A strategy whose class defines `__getattribute__`, `__eq__`, `__hash__` and `__repr__` that raise `AssertionError` is accepted as `strategy`, and `repr(pair)` succeeds without it (F8). `Pair("A", s, p).strategy is s`, `.parameters is p`. Two pairs built from the same arguments compare unequal (`eq=False`).
  - `test_report_types_are_validated_final_and_frozen` (N13):
    - `StrategyFault`: `cause` as `"raised"`, `None`, `1`; `type_name` as `None`, `1`, a `str`-subclass instance → exactly `EvaluationTypeError`. `StrategyFault(FaultCause.RAISED, "")` is accepted (U9). `StrategyFault(FaultCause.RAISED, "x") == StrategyFault(FaultCause.RAISED, "x")` with equal hashes, and `!=` with the other cause.
    - `ReportEntry`: `instrument` as `""` or `1`; `strategy` as `None`, `("test", "1")` or an object whose `__class__` property returns `StrategyIdentity`; `outcome` as `None`, `NotAnOutcome(int)`, the class `NoSignal`, a `Signal` → exactly `EvaluationTypeError`. Each of `Signals(...)`, `NoSignal()`, `EvaluationFailure("f")` and a `StrategyFault` is accepted and held with `is`.
    - `ExecutionReport`: `as_of` as `-1`, `True`, `2**53`, `1.0`; `entries` as a `list`, or a tuple holding `None` → exactly `EvaluationTypeError`. `ExecutionReport(5, ())` is accepted.
    - Defining a subclass of `Pair`, `StrategyFault`, `ReportEntry`, `ExecutionReport` or `FaultCause` raises exactly `TypeError`. For `Pair`, `StrategyFault`, `ReportEntry` and `ExecutionReport` (not the enum): assigning any field raises `dataclasses.FrozenInstanceError`, and none has a `__dict__`. `list(FaultCause) == [FaultCause.RAISED, FaultCause.RETURNED_NON_OUTCOME]`.
  - `test_refusal_error_is_its_own_class`: `issubclass(ExecutionRefusedError, ValueError)` and `not issubclass(ExecutionRefusedError, EvaluationTypeError)` (spec 5.4).

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/application -q`
  Expected: collection error, `sentaris_engine.application.execution` does not exist.

- [ ] **Step 3: Implement the Task 1 part of `src/sentaris_engine/application/execution.py`**

  The types as in the interfaces block. `ReportEntry.outcome` is checked with four separate `type(v) is X` comparisons (no tuple, no `in`). `qualified_type_name` follows spec 5.5 exactly:

  ```python
  def qualified_type_name(cls: type) -> str:
      qualname = str.__str__(type.__dict__["__qualname__"].__get__(cls))
      try:
          module_value = type.__dict__["__module__"].__get__(cls)
      except AttributeError:
          return qualname
      if not type.__subclasscheck__(str, type(module_value)):
          return qualname
      module = str.__str__(module_value)
      if not module:     # exact str: no subclass __len__/__bool__ runs
          return qualname
      return module + "." + qualname
  ```

  The module docstring cites section 6.7, DR-22, U2, U4, U9 and SE-4 spec 5.6 by ID.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: `uv run pytest tests/application -q`. Expected: all pass.

- [ ] **Step 5: Apply spec section 13 to `docs/domain.md`**

  Apply edits 1 and 2: replace each quoted "before" sentence by its "after" text. Each anchor occurs exactly once in `docs/domain.md` (section 6.7, lines 218 and 224 at the time of writing). The "after" texts are fenced ```` ```text ```` blocks in the spec; insert only the inner text, without fences or indentation, in place of the "before" sentence on the same line. Change nothing else.

  Verify: `git diff --stat docs/` shows only `docs/domain.md`; `git diff docs/` contains exactly the two edits, character for character.

- [ ] **Step 6: Run the gate and commit**

  Run: `make check`. Expected: ruff, mypy and lint-imports clean; the final pytest line reports `passed` with no failures.

  ```bash
  git add src/sentaris_engine/application/execution.py tests/application docs/domain.md docs/superpowers/specs/2026-11-13-se-5-execution-over-pairs-design.md docs/superpowers/plans/2026-11-13-se-5-execution-over-pairs.md
  git commit -m "feat: SE-5 execution value types and type names"
  ```

**Completion condition:** AC-6 (direct), AC-9 and the Task 1 part of AC-10 hold; `make check` passes; the `docs/domain.md` diff is exactly edits 1 and 2.

---

### Task 2: Execution

**Implementer:** `opus`. Every guarantee of section 6.7 meets here: refusals before any strategy code, identity read once and copied, ordering, the narrow `try`, and propagation of non-ordinary exceptions. A mistake in what runs inside or outside the `try`, or in what foreign code is called, is invisible in normal tests (slice skill, rule 4).

**Files:** the Task 2 rows of the file structure table.

**Scope:** spec 5.3, 5.4 (chaining), section 6, N1 to N11, Review Focus 1 to 5, scope item 3 (`CLAUDE.md`).

**Interfaces:**
- Consumes everything Task 1 produces; `evaluate_stateless`, `NotAnOutcome`, `EvaluationContext`, `StatelessStrategy`, `StatefulStrategy`, `_ContractMeta` (only in tests, for the N3 bypass), `snapshot` from `tests/domain/row_builders.py`, `MinimalStateful`, `raises_exactly`, `type_name_cases`.
- Produces `execute` (interfaces block), and in `tests/application/execution_helpers.py`:
  - `Call = tuple[StrategyIdentity, EvaluationContext]`;
  - `RecordingStrategy(identity: StrategyIdentity, log: list[Call], outcome: object = NoSignal(), *, raises: bool = False)`: stateless; its `identity` property counts reads in `self.identity_reads: int`; `evaluate` appends `(identity, context)` to `log` and then raises `outcome` when `raises` is true (it must then be an exception), else returns it, an exception object included;
  - `params(k: int = 1) -> Parameters`: `Parameters({"k": k})`;
  - `instrument_of(context: EvaluationContext, snapshots: dict[str, Snapshot]) -> str`: the key whose snapshot `is context.snapshot` (found by `is`, for test assertions).

  `execute` follows spec 5.3 steps 1 to 8 in that order, with R2 and R5 in step 1. Sketch of the parts the spec leaves to the builder:
  - step 1: `check_instant` and the `snapshots` entry checks inside one `try`/`except EvaluationTypeError` that raises `ExecutionRefusedError` `from None`; then the copy of R2, and each pair's three fields read once into engine-held values (R5), used by every later step;
  - step 2: compare `set(copy)` with `{pair.instrument for pair in pairs}` (exact `str` only); a `dict[int, str]` keyed by `id(snapshot)` detects one object under two keys;
  - step 3: `mro = type.__dict__["__mro__"].__get__(type(strategy))`; count `base is StatelessStrategy` and `base is StatefulStrategy` over it; refuse unless the counts are exactly 1 and 0. All pairs are checked before step 4 starts;
  - step 4: `identities: dict[int, StrategyIdentity]` keyed by `id(pair.strategy)`; the read is `try: value = pair.strategy.identity` / `except Exception as exc: raise ExecutionRefusedError(...) from exc`; then `type(value) is StrategyIdentity`, read `value.id` and `value.version`, check each `type(x) is str and x`, and store `StrategyIdentity(id, version)`;
  - steps 5 and 6: keys `(pair.instrument, identity.id, identity.version)`; duplicates through a `set` of those tuples; `sorted(range(len(pairs)), key=...)` or equivalent, so that no `Pair` is ever compared;
  - step 7: `context = EvaluationContext(copy[pair.instrument], pair.parameters, as_of)`, then the one `try` around `evaluate_stateless(pair.strategy, context)` with `except Exception as exc: raised = type(exc)`; the `StrategyFault` is built after the `try` statement, so `exc` is gone when the name is derived. A `NotAnOutcome` result becomes `StrategyFault(RETURNED_NON_OUTCOME, qualified_type_name(result.returned_type))`.

- [ ] **Step 1: Write the failing tests in `tests/application/test_execution.py`**

  Unless a test says otherwise, instruments are `"A"` and `"B"`, every snapshot is `snapshot(AS_OF)` with `AS_OF = 10_000_000`, built fresh per instrument, and every strategy is a `RecordingStrategy` sharing one `log`.

  - `test_pairs_run_in_code_point_order` (N1): four pairs `("A", ("s","1"))`, `("A", ("s","2"))`, `("A", ("r","9"))`, `("B", ("r","9"))` (the last two share one strategy object), so that instrument, `id` and `version` each decide one comparison; the expected order is `A/r/9`, `A/s/1`, `A/s/2`, `B/r/9`; for all 24 permutations of `pairs`, and for the `snapshots` dict built in both insertion orders, the report's `(instrument, id, version)` list is `sorted(...)` of the triples, every report equals the first, and the log's `(identity, instrument_of(context))` order matches the entries. A second case with instrument keys `"\U00010000"`, `"￿"`, `"a"`, `"B"` given in that order yields entries in the order `"B"`, `"a"`, `"￿"`, `"\U00010000"` (write `￿` as an escape in the test source, never as a literal).
  - `test_duplicate_pair_is_refused` (N2): the same strategy object twice on `"A"`, and two objects with equal identities on `"A"` → `ExecutionRefusedError`; log empty. Positive: one identity on `"A"` and `"B"`, and `("s","1")` and `("s","2")` on `"A"`, each give a report with the expected entries.
  - `test_strategy_of_wrong_contract_is_refused` (N3): as `strategy` of one pair, with a valid `RecordingStrategy` pair beside it that sorts first and one that sorts last: a `StatefulStrategy` subclass with a counting `identity` property; a plain object with `identity` and `evaluate`; an object of a plain class whose `__class__` property returns `StatelessStrategy`; an instance of a class made with `ABCMeta.__new__(_ContractMeta, "Both", (StatelessStrategy, StatefulStrategy), {...})`, which bypasses `_ContractMeta.__new__`; and the class `RecordingStrategy` itself (Review Focus 2). Each → `ExecutionRefusedError`; log empty and every `identity_reads` (also of the valid pairs, and a counting `identity` on the wrong objects) is 0. Positive: a stateless strategy whose metaclass (derived from `type(StatelessStrategy)`) defines `__eq__` and `__hash__` that raise `AssertionError` is evaluated normally.
  - `test_identity_is_read_once_and_checked` (N4, Review Focus 5):
    - one strategy object in three pairs (`"A"`, `"B"`, `"C"`) and another in one pair: `identity_reads` is 1 for each, and each strategy's read happened before the first log entry (record the log length at read time in the property);
    - a second `execute` with the same arguments: `identity_reads` is 2 and the report equals the first;
    - an `identity` raising `ValueError` → `ExecutionRefusedError` with `__cause__ is` that `ValueError`; log empty;
    - an `identity` returning `None`, `("id", "1")`, or an object whose `__class__` property returns `StrategyIdentity` → `ExecutionRefusedError`, `__cause__ is None`; log empty;
    - a `StrategyIdentity` whose `id` was set with `object.__setattr__` to `""`, `1` or a `str`-subclass instance → `ExecutionRefusedError`; log empty;
    - a strategy that returns the same `StrategyIdentity` object each read and, in `evaluate`, sets its `id` to `"zzz"` with `object.__setattr__`: every entry's `strategy == StrategyIdentity(<original>)` and entry order is the original order;
    - a strategy whose class defines `__eq__` and `__hash__` that raise `AssertionError` is read once and evaluated normally;
    - an `identity` raising `KeyboardInterrupt` → that object propagates (`is`), not an `ExecutionRefusedError`.
  - `test_snapshot_mismatch_is_refused` (N5): each of these → `ExecutionRefusedError` with `__cause__ is None` and `__suppress_context__ is True`, log empty and every `identity_reads` 0 (steps 1 and 2 precede step 4): no snapshot for `"B"`; a surplus snapshot `"C"`; `execute(AS_OF, (), {"A": snap})` (U5 with U7); `snapshots["B"]` of `as_of` `AS_OF - 1`; one snapshot object under `"A"` and `"B"`; a value `None` under `"A"`; `snapshots` as a `MappingProxyType`; a key `""`, a key `1`, and a key that is a `str`-subclass instance whose `__hash__` and `__eq__` raise `AssertionError` once armed (armed through a class flag after the dict is built, since building the dict hashes the key); `pairs` as a `list`, or a tuple holding `None`; `as_of` as `-1`, `True`, `2**53`, `1.0`. Positive: `execute(AS_OF, (), {})` gives `ExecutionReport(AS_OF, ())` (U7); two distinct snapshot objects with equal content under `"A"` and `"B"` are accepted.
  - `test_strategy_exception_is_isolated_to_its_pair` (N6, Review Focus 3): one strategy object paired with `"A"` and `"B"` that raises only for the snapshot of `"A"` (it is given that snapshot object), plus a strategy returning `NoSignal()` on `"A"`; parametrised over `ValueError(SENTINEL)`, `EvaluationTypeError(SENTINEL)`, a `RecursionError` from real unbounded recursion inside `evaluate`, an instance of a test-defined `Exception` subclass with `SENTINEL` in its args, an `ExecutionRefusedError(SENTINEL)` (a `RAISED` fault, not a refusal), and an exception whose `__str__`, `__repr__` and `__getattribute__` raise `AssertionError` (built in the test body or passed with an explicit id). The raising entry is exactly `StrategyFault(FaultCause.RAISED, qualified_type_name(type(exc)))`, and that name is spelled as the literal expected text for `ValueError` (`"builtins.ValueError"`) and `EvaluationTypeError` (`"sentaris_engine.domain.errors.EvaluationTypeError"`); every other entry equals its entry in an execution of that pair alone; `SENTINEL` is in no field and in the `repr` of no report, entry or fault.
  - `test_non_outcome_is_reported_as_fault` (N7): strategies returning `None`, a `Signal`, a `[]`, the class `NoSignal`, `NotAnOutcome(int)`, a `ValueError()` and a `KeyboardInterrupt()` (returned, not raised) give entries exactly `StrategyFault(FaultCause.RETURNED_NON_OUTCOME, qualified_type_name(type(value)))` (`"builtins.NoneType"` spelled literally for `None`; for the `NotAnOutcome` case the name of `NotAnOutcome`, not of `int`).
  - `test_non_ordinary_exception_propagates` (N8): the raising pair sorts first and a `RecordingStrategy` pair sorts after it; for `KeyboardInterrupt()`, `SystemExit(3)`, `GeneratorExit()` and a test-defined direct `BaseException` subclass: caught with `pytest.raises(BaseException)`, `info.value is exc`, `__cause__ is None`, `__context__ is None`, and the later strategy's log is empty.
  - `test_type_names_through_execute` (N9): for every case of `type_name_cases(Exception)`, a strategy raising an instance of it gives `StrategyFault(RAISED, expected)`; for every case of `type_name_cases(object)`, a strategy returning an instance (created with `object.__new__` where `__init__` would be in the way) gives `StrategyFault(RETURNED_NON_OUTCOME, expected)`; each execution returns a report and each case's log is empty.
  - `test_context_per_pair` (N10): two strategies on `"A"` and one on `"B"`, with distinct `Parameters` objects: for each log entry `context.snapshot is snapshots[instrument]`, `context.parameters is` that pair's parameters, `context.as_of == AS_OF`; both `"A"` calls see the same snapshot object; no attribute of any context (`snapshot`, `parameters`, `as_of`, and the snapshot's fields) `is` or `==` an instrument key.
  - `test_entry_is_the_same_alone_and_together` (N11): five pairs returning `Signals`, `NoSignal()`, `EvaluationFailure("f")`, raising `ValueError`, and returning `None`; each entry of the mixed report equals the single entry of executing that pair alone (with only its snapshot); a second run of the mixed execution gives an equal report.
  - `test_outcome_is_reported_as_the_very_object` (Review Focus 4): as described there.
  - `test_snapshots_dict_changed_during_run_changes_nothing` (Review Focus 1, R2, R5): as described there; the later pair's `context.snapshot is` the original object for its instrument. Second case: a strategy holding the later `Pair` sets its `instrument`, `parameters` and `strategy` to other valid values with `object.__setattr__` during its `evaluate`; the later pair is evaluated with its original strategy, parameters and snapshot, and its entry carries the original instrument.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/application/test_execution.py -q`
  Expected: collection error, `execute` cannot be imported.

- [ ] **Step 3: Implement `execute` in `src/sentaris_engine/application/execution.py` and `tests/application/execution_helpers.py`**

  As described under Interfaces, under the "No foreign code", "Descriptors", "Errors" and "One `try`" constraints. Its docstring cites section 6.7, DR-10, DR-22, DR-23, U1, U3, U5, U7, U8 and R2 by ID.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: `uv run pytest tests/application -q`. Expected: all pass.

- [ ] **Step 5: Update `CLAUDE.md` "Current state"**

  Name SE-5 next to SE-1 to SE-4 and state that SE-5 is execution over pairs in `sentaris_engine.application` (`execution`). Change nothing else in the file.

- [ ] **Step 6: Run the gate and commit**

  Run: `make check`. Expected: all steps clean; the final pytest line reports `passed` with no failures.

  ```bash
  git add src/sentaris_engine/application/execution.py tests/application CLAUDE.md
  git commit -m "feat: SE-5 execution over pairs"
  ```

**Completion condition:** AC-1 to AC-8 and AC-10 hold; the Review Focus tests pass; `make check` passes.

---

## Acceptance criteria → tests

| AC | Tests |
|---|---|
| AC-1 | `test_pairs_run_in_code_point_order` |
| AC-2 | `test_duplicate_pair_is_refused`, `test_strategy_of_wrong_contract_is_refused`, `test_identity_is_read_once_and_checked`, `test_snapshot_mismatch_is_refused` |
| AC-3 | `test_identity_is_read_once_and_checked` |
| AC-4 | `test_strategy_exception_is_isolated_to_its_pair`, `test_non_outcome_is_reported_as_fault` |
| AC-5 | `test_non_ordinary_exception_propagates` |
| AC-6 | `test_type_name_is_module_qualified_and_safe`, `test_same_name_in_two_modules_differs`, `test_type_names_through_execute` |
| AC-7 | `test_context_per_pair` |
| AC-8 | `test_entry_is_the_same_alone_and_together` (for the test strategies only; spec section 9) |
| AC-9 | `test_pair_is_validated`, `test_report_types_are_validated_final_and_frozen` |
| AC-10 | `make check`, with `tests/architecture/test_purity.py` covering the new module unchanged |
