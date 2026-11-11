# SE-2 Multi-Strategy Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate several stateless strategies for one `as_of` in one call and return one report entry per strategy, in a fixed order, where a strategy that raises or breaks the result contract is reported as its own entry and changes no other entry.

**Architecture:** One new module `application/execution.py` holds the report types and `execute_strategies`. It reads each strategy's identity once, refuses duplicates and invalid identities before anything runs, sorts by `(id, version)`, and for each strategy in turn calls `strategy.evaluate(context)` and the result check, catching `Exception` per strategy. The result check is split out of `evaluate_strategy` (`check_result`, behavior of `evaluate_strategy` unchanged) so that identity is not read again. No domain change, no new import, no new dependency.

**Tech Stack:** Python 3.12 standard library only (`dataclasses`), pytest, ruff, mypy strict, import-linter.

**Spec:** `docs/adr/0002-multi-strategy-execution.md` (the decision), `docs/superpowers/specs/2026-11-09-engine-roadmap-design.md` (slice SE-2: acceptance and tests). Rules: `docs/domain.md` DR-10, DR-14, DR-22 and section 10 "Multi-strategy execution (OD-15)". The failure-code taxonomy (OD-3), `as_of` selection (OD-5), state (OD-17 to OD-20) and the input declaration (rest of OD-13) stay open and are not decided here.

## Global Constraints

- Layers: `application → strategies | infrastructure → domain`. New production code is in `src/sentaris_engine/application/execution.py` (it imports only `sentaris_engine.application.evaluation`, `sentaris_engine.domain.evaluation` and the standard library) plus the `check_result` split in `application/evaluation.py`. If `make imports` fails, stop and ask; never widen a contract.
- **Scope is stateless strategies over contexts the caller built.** No snapshot building, no state, no registry or discovery (strategies arrive as an explicit argument, OD-13), no concurrency, no persistence, no CLI, no mapping of anything to an `EvaluationFailure` code (OD-3). The execution neither reads nor interprets a payload (DR-23, DR-25).
- Decisions are ADR-0002 as written: one execution is one `as_of`; each strategy gets its own context and the engine does not copy or change a snapshot; order is ascending `(id, version)`, strings compared by Unicode code point (Python `str` ordering); a duplicate `(id, version)` or an invalid identity refuses the whole execution before any strategy runs; identity is read once per execution; `Exception` raised by a strategy, `StrategyContractError` from the result check included, is caught for that strategy alone and reported with the exception's type name, never its message or traceback; a `BaseException` that is not an `Exception` propagates.
- Plan-level calls (my call; ADR-0002 leaves them to the plan): the contexts of one execution must all have the same `as_of` (`ValueError`), because one execution is one `as_of`; an empty input gives an empty report; the type name is `type(error).__qualname__`; the exceptions for duplicates, a differing `as_of` and a wrong context type are `ValueError`, an invalid identity is `StrategyContractError`. "Refused exactly as a duplicate" in ADR-0002 means refused before anything runs, not the same exception type. When an input has several problems the first check in the order of the behavior list below wins.
- Types check their fields by exact type at construction and raise `ValueError`, as in `domain/evaluation.py`; a subclass of an accepted type is rejected. Frozen dataclasses with `slots=True`.
- ruff line length 120; mypy strict over `src` and `tests`; annotate everything. A negative test that passes a wrong type goes through `cast(Any, value)`, never a bare `# type: ignore`. `make check` passes at the end of every task. Never weaken a check, contract or test.
- Probes live in `tests/support/probes.py` and carry no market logic.
- **Docs in the same commit** (CLAUDE.md, `docs/domain.md` sections 9 and 11): Task 2's commit carries the enforcement rows (DR-10 in section 5.3, DR-14 and DR-22 in section 5.1; section 9 only defines the statuses), the "Built" row, the revision 12 row and the `CLAUDE.md` current-state sentence.
- Branch `se-2-multi-strategy-execution` (created from `main`, already holds the ADR commit). One commit per task, each message ending with the attribution line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. No push.

## Review Focus

Input classes the ADR implies but the roadmap does not test; each has a named test in the task that owns the code.

1. **Order that only looks sorted.** Ids that differ in case or are non-ASCII (`"Z"` before `"a"`, `"é"` after `"z"`), the same id with several versions, and every permutation of the input: the report and its order must be identical. Tests: Task 2 `test_report_order_does_not_depend_on_registration_order`, `test_order_is_by_code_point_then_version`.
2. **An invalid or duplicated identity next to a healthy strategy.** Nothing may run: not the healthy one before it in sorted order, not any other. Tests: Task 2 `test_duplicate_identity_is_refused_before_anything_runs`, `test_invalid_identity_is_refused_before_anything_runs`, `test_identity_is_read_once`.
3. **An exception that leaks data or cannot be printed.** The report holds the type name only; an exception whose message holds a secret, or whose `__str__` raises, must neither leak nor break the report. Tests: Task 2 `test_raised_exception_is_reported_by_type_name_only`, `test_exception_with_failing_str_is_reported`.
4. **A raise that would take the others down.** A raising strategy sorted first or last, a strategy that tries to mutate its snapshot, and a `BaseException`: the others are evaluated and unchanged, the mutation is a reported raise, and `KeyboardInterrupt` is not swallowed. Tests: Task 2 `test_raising_strategy_does_not_change_the_other_entries`, `test_mutating_strategy_is_reported_and_changes_nothing`, `test_base_exception_propagates`.
5. **Input that is consumed or changed after the call.** A generator is read once; a list the caller later changes does not alter the report; contexts reach strategies unchanged (same objects). Tests: Task 2 `test_input_may_be_a_one_shot_iterator`, `test_each_strategy_gets_its_own_context`.

---

### Task 1: Report types

**Files:**
- Create: `src/sentaris_engine/application/execution.py` (types only in this task)
- Create: `tests/application/test_execution_types.py`

**Interfaces:**
- Consumes: `sentaris_engine.domain.evaluation.Result`, `Signals`, `NoSignal`, `EvaluationFailure`.
- Produces, in `sentaris_engine.application.execution`:
  - `StrategyRaised(error_type: str)`: the strategy raised an `Exception`; `error_type` is a non-empty exact `str`. Frozen, slots.
  - `type StrategyOutcome = Signals | NoSignal | EvaluationFailure | StrategyRaised`.
  - `StrategyReport(strategy_id: str, strategy_version: str, outcome: StrategyOutcome)`: `strategy_id` and `strategy_version` non-empty exact `str`; `type(outcome)` is exactly one of the four outcome classes. Frozen, slots.
  - `ExecutionReport(entries: tuple[StrategyReport, ...])`: an exact `tuple` of exact `StrategyReport`, strictly ascending by `(strategy_id, strategy_version)` (so no duplicate). Empty is allowed. Frozen, slots.

- [ ] **Step 1: Write the failing tests** in `tests/application/test_execution_types.py`. Each validation raises `ValueError`; use `pytest.raises(ValueError, match=...)` on a stable word of the message.
  - `test_strategy_raised_requires_a_non_empty_exact_str`: `StrategyRaised("ValueError")` is valid; `""`, `1`, `None` and a `str` subclass raise.
  - `test_strategy_report_requires_exact_identity_and_outcome`: valid with each of `Signals((Signal("k", Payload.of({})),))`, `NoSignal()`, `EvaluationFailure("c")`, `StrategyRaised("E")`; empty or non-`str` or `str`-subclass `strategy_id` / `strategy_version` raise; an outcome that is `None`, a `str`, or a subclass of any of the four classes raises.
  - `test_strategy_raised_is_not_an_evaluation_failure`: `StrategyReport("a", "1", StrategyRaised("E")) != StrategyReport("a", "1", EvaluationFailure("E"))`.
  - `test_execution_report_requires_strictly_ascending_exact_entries`: `ExecutionReport(())` is valid; entries `(a/1, a/2, b/1)` valid; `(a/2, a/1)` raises; `(a/1, a/1)` raises; a `list` of entries raises; a non-`StrategyReport` member raises; a `StrategyReport` subclass member raises (define the subclass in the test module).
  - `test_report_values_are_immutable_and_comparable`: assigning a field raises `AttributeError` (via `cast(Any, ...)`); two equal reports compare equal and hash equal.

- [ ] **Step 2: Run** `uv run pytest tests/application/test_execution_types.py -v`. Expected: collection FAIL, `ModuleNotFoundError: sentaris_engine.application.execution`.

- [ ] **Step 3: Implement the four names above** in `src/sentaris_engine/application/execution.py`, with a module docstring that cites ADR-0002, OD-15, DR-10, DR-14, DR-22 and says an exception's message and traceback are never stored. A small private `_require_text(value, name)` in this module (exact `str`, non-empty, `ValueError`), as `domain/evaluation.py` has one: it is private there, so do not import it. Outcome check: `type(outcome) not in (Signals, NoSignal, EvaluationFailure, StrategyRaised)`. Ordering check: compare each entry's `(strategy_id, strategy_version)` with the previous one with `<`.

- [ ] **Step 4: Run** `uv run pytest tests/application/test_execution_types.py -v`. Expected: PASS.

- [ ] **Step 5: Run** `make check`. Expected: lint, typecheck, imports and tests all pass.

- [ ] **Step 6: Commit**

```bash
git add src/sentaris_engine/application/execution.py tests/application/test_execution_types.py docs/superpowers/plans/2026-11-11-se-2-multi-strategy-execution.md
git commit -m "feat(application): execution report types (SE-2)"
```

---

### Task 2: `execute_strategies` and its documentation

**Files:**
- Modify: `src/sentaris_engine/application/execution.py` (add the function)
- Modify: `src/sentaris_engine/application/evaluation.py` (split out `check_result`; update the module docstring, which says how a raise is reported "is OD-15", to point to `execution.py`)
- Modify: `tests/support/probes.py` (add `RecordingProbe`, `CountingIdentityProbe`, `FailingStrError`)
- Create: `tests/application/test_execute_strategies.py`
- Modify: `docs/domain.md` (status line, section 2 "Built", rule rows DR-10, DR-14, DR-22, revision 12 row), `CLAUDE.md` ("Current state")

**Interfaces:**
- Consumes: Task 1 types; `evaluate_strategy(strategy: StatelessStrategy, context: EvaluationContext) -> Result` and `StrategyContractError` from `sentaris_engine.application.evaluation`; `EvaluationContext`, `StatelessStrategy` from `sentaris_engine.domain.evaluation`.
- Produces: `execute_strategies(entries: Iterable[tuple[StatelessStrategy, EvaluationContext]]) -> ExecutionReport` in `sentaris_engine.application.execution`; `check_result(strategy_id: str, strategy_version: str, outcome: object) -> Result` in `sentaris_engine.application.evaluation`, which returns `outcome` if `type(outcome)` is exactly `Signals`, `NoSignal` or `EvaluationFailure` and otherwise raises `StrategyContractError` with the message `evaluate_strategy` has today (built from the two arguments). `evaluate_strategy` keeps its behavior and every existing test in `tests/application/test_evaluate_strategy.py` passes unchanged; it reads `strategy.id` and `strategy.version` once into locals and passes them on.
- Probes added to `tests/support/probes.py`: `RecordingProbe(id: str, version: str, outcome: Result, seen: list[EvaluationContext])` (frozen dataclass, `seen` a required argument with no default; `evaluate` appends the context it receives to `seen` and returns `outcome`); `CountingIdentityProbe` (a plain non-frozen class whose `id` and `version` are properties that count their reads in `id_reads` / `version_reads` and return fixed text, and whose `evaluate` returns `NoSignal()`); `FailingStrError(Exception)` whose `__str__` raises `RuntimeError`.

Behavior of `execute_strategies`, in this order:
1. Materialize `entries` into a `tuple` once.
2. For each pair, require `type(context) is EvaluationContext` (else `ValueError`) and read `strategy.id` and `strategy.version` **once**, requiring each to be an exact non-empty `str` (else `StrategyContractError`, message naming the attribute). Whatever reading an attribute raises propagates. This pass covers all pairs before step 3.
3. Require all contexts to have the same `as_of` (else `ValueError`) and no two strategies with the same `(id, version)` (else `ValueError` naming that identity).
4. Sort the pairs by `(id, version)` using the identity read in step 2.
5. For each pair in that order, inside one `try` that catches `Exception`: `check_result(id, version, strategy.evaluate(context))` with the id and version read in step 2; the return value becomes the entry's outcome and an `Exception` becomes `StrategyRaised(type(error).__qualname__)`. `evaluate_strategy` is not called and no attribute of a strategy other than `evaluate` is read here. Nothing is evaluated if step 1 to 3 fail.
6. Return `ExecutionReport(tuple(entries in sorted order))`.

- [ ] **Step 1: Add the probes** to `tests/support/probes.py`.

- [ ] **Step 2: Write the failing tests** in `tests/application/test_execute_strategies.py`, with a module-level hand-built context (as in `tests/application/test_evaluate_strategy.py`; one candle is enough) and probes from `tests/support/probes.py`. Assertions in exact values:
  - `test_report_order_does_not_depend_on_registration_order` (DR-10 negative test): `ScriptedProbe` with ids/versions `("b","1")`, `("a","2")`, `("a","1")`, `("c","1")`, each with a distinct outcome; for every `itertools.permutations` of the four, the report equals the one report whose entries are `a/1, a/2, b/1, c/1` with their own outcomes.
  - `test_order_is_by_code_point_then_version`: ids `"a"`, `"Z"`, `"é"`, `"z"` give the order `Z, a, z, é`; versions `"10"` and `"9"` of one id give `"10"` before `"9"`.
  - `test_each_strategy_gets_its_own_context`: four `RecordingProbe` with the ids of the permutation test, each given its own context (same `Snapshot` object, `Parameters.of({"n": i})` distinct per probe, same `as_of`), passed in an order unlike the sorted one; afterwards each probe's `seen` is exactly `[its own context]` (`seen[0] is own_context`) and every `seen[0].snapshot` is the same object as the original snapshot (a bug that pairs identities with the wrong contexts, or copies a snapshot, fails). Covers `test_each_strategy_gets_its_own_context` of the Review Focus.
  - `test_raising_strategy_does_not_change_the_other_entries` (DR-22 negative test): `H = execute_strategies([(healthy, ctx)]).entries[0]` for a `LastCloseProbe("m","1")`. Two runs beside a `RaisingProbe`: with id `"a"` (sorted before) the report has exactly two entries, `[StrategyReport("a","1",StrategyRaised("ValueError")), H]`; with id `"z"` (sorted after) exactly `[H, StrategyReport("z","1",StrategyRaised("ValueError"))]`.
  - `test_raised_exception_is_reported_by_type_name_only`: `RaisingProbe(error=ValueError("secret-token-123"))`; `"secret-token-123" not in repr(report)`; the outcome is `StrategyRaised("ValueError")`.
  - `test_exception_with_failing_str_is_reported`: `RaisingProbe(error=FailingStrError())` gives `StrategyRaised("FailingStrError")`.
  - `test_contract_breach_in_a_result_is_reported`: `BrokenProbe(returns=None)` gives `StrategyRaised("StrategyContractError")` and a healthy neighbour's entry equals its entry when run alone.
  - `test_strategy_raised_is_not_an_evaluation_failure`: a `ScriptedProbe(outcome=EvaluationFailure("c"))` stays `EvaluationFailure("c")`, and beside it a raiser's entry has outcome type `StrategyRaised`, so the two are told apart in one report (DR-14); the report has one entry per strategy.
  - `test_mutating_strategy_is_reported_and_changes_nothing`: a `MutatingProbe("a","1")` and a `LastCloseProbe("m","1")` share one `Snapshot` object (the mutator sorts first); the mutator's entry is `StrategyRaised("FrozenInstanceError")`; the healthy entry equals its entry when run alone; and afterwards the snapshot `==` a second snapshot built from the same candles.
  - `test_base_exception_propagates`: a `RaisingProbe` carrying `KeyboardInterrupt()` (through `cast(Any, ...)`) beside a `RecordingProbe` sorted after it makes `execute_strategies` raise `KeyboardInterrupt`, and the `RecordingProbe` was not run.
  - `test_duplicate_identity_is_refused_before_anything_runs`: `RecordingProbe` `("a","1")`, `("a","1")` and `("b","1")` in every order: `ValueError` matching `"a"`; every `seen` is empty. Same id with different versions is accepted.
  - `test_invalid_identity_is_refused_before_anything_runs`: one healthy `RecordingProbe("a","1")` and one invalid probe, tried once with the invalid probe first and once last in the input; the invalid probes, each in its own run, are `RecordingProbe("b","")`, `RecordingProbe(StrSubclass("z"),"1")` and `RecordingProbe("b", cast(Any, 5))` (values chosen so each sorts after `"a"`; a lazy check inside the run loop would run `"a"` first); each raises `StrategyContractError` and every `seen` is empty. A `RecordingProbe("", "1")` that sorts first is also refused.
  - `test_identity_is_read_once`: a `CountingIdentityProbe` among other strategies; after a run `id_reads == 1` and `version_reads == 1`.
  - `test_differing_as_of_is_refused`: `RecordingProbe("a","1")` with `as_of` A and `RecordingProbe("b","1")` (sorted last) with `as_of` B, in both input orders: `ValueError`, every `seen` empty.
  - `test_wrong_context_type_is_refused`: `RecordingProbe("a","1")` with a valid context and `RecordingProbe("b","1")` (sorted last) with a non-`EvaluationContext` through `cast(Any, ...)`: `ValueError`, every `seen` empty.
  - `test_first_problem_in_the_check_order_wins`: an input with an invalid identity and a differing `as_of` raises `StrategyContractError`; a duplicate identity and a differing `as_of` raises the `ValueError` for the `as_of`.
  - `test_empty_input_gives_an_empty_report`: `execute_strategies(())` equals `ExecutionReport(())`.
  - `test_input_may_be_a_one_shot_iterator`: a generator of pairs gives the same report as the tuple of the same pairs.
  - `test_list_changed_after_the_call_does_not_change_the_report`: build the report from a list, append a pair to the list afterwards, the report still has the original entries.
  - `test_each_strategy_runs_once`: every `RecordingProbe.seen` has length 1 after a run with several strategies, one of them raising.

- [ ] **Step 2b: Run** `uv run pytest tests/application/test_evaluate_strategy.py -v` before touching `evaluate_strategy`. Expected: PASS (the baseline the split must keep).

- [ ] **Step 3: Run** `uv run pytest tests/application/test_execute_strategies.py -v`. Expected: FAIL (`ImportError: cannot import name 'execute_strategies'`).

- [ ] **Step 4: Split out `check_result`** in `src/sentaris_engine/application/evaluation.py` as the Interfaces block states and make `evaluate_strategy` use it; then implement `execute_strategies` in `src/sentaris_engine/application/execution.py` as the behavior list above states. Docstring: lists what raises (`StrategyContractError` for an invalid identity, `ValueError` for a duplicate identity, a differing `as_of`, a wrong context type) and what is caught, and says a `BaseException` that is not an `Exception` propagates. One small private helper that reads and validates the identity is enough.

- [ ] **Step 5: Run** `uv run pytest tests/application -v`. Expected: PASS, including the unchanged `test_evaluate_strategy.py`.

- [ ] **Step 6: Update the documents** in the same change, following the wording form of the existing `ENFORCED, partly` row of DR-11 (evidence in backticks in parentheses, "Also covered:", "**Not checked:**"):
  - `docs/domain.md` section 5.3, DR-10: `ENFORCED, partly: the order in which strategies run and are reported is sorted by (id, version) and does not depend on registration order (tests/application/test_execute_strategies.py::test_report_order_does_not_depend_on_registration_order, ::test_order_is_by_code_point_then_version). Also covered: ` plus what the existing row or the tests already show for candle and series order and payload key order (read the current DR-10 row and name the existing tests that exist: `tests/application/test_evaluate_strategy.py::test_shuffled_candle_order_gives_the_same_result` and the payload key-order test). `**Not checked:** iteration order inside a strategy's own code.`
  - `docs/domain.md` section 5.1, DR-22: `ENFORCED, partly: an exception or a result that breaks the contract in one strategy is reported as its own entry and leaves every other entry equal to its entry when run alone (tests/application/test_execute_strategies.py::test_raising_strategy_does_not_change_the_other_entries, ::test_contract_breach_in_a_result_is_reported, ::test_mutating_strategy_is_reported_and_changes_nothing); each strategy receives its own context (::test_each_strategy_gets_its_own_context). **Not checked:** a strategy reading mutable state shared with another strategy outside its context (purity is not checked at run time, only by the import contracts); stateful strategies (SE-3).`
  - `docs/domain.md` section 5.1, DR-14: add to its evidence that a raise caught by the execution is reported as a separate outcome and never as no signal or a missing entry (`::test_strategy_raised_is_not_an_evaluation_failure`, `::test_raising_strategy_does_not_change_the_other_entries`); keep the existing evidence.
  - `docs/domain.md` section 2 "Built": append the multi-strategy execution (`execute_strategies`, `check_result`, the report types; `sentaris_engine.application.execution`; OD-15, ADR-0002, DR-10, DR-14, DR-22) and state every plan-level behavior, because what is not written is not decided: a differing `as_of` and a wrong context type are `ValueError`, a duplicate `(id, version)` is `ValueError`, an invalid identity is `StrategyContractError`, all before anything runs; an empty input gives an empty report; the type name of a raise is `__qualname__`; `Exception` is caught and a `BaseException` that is not an `Exception` propagates. Change "how a raise is reported next to other strategies is decided (OD-15, ADR-0002) and not yet built" to say it is built.
  - `docs/domain.md`: status line to "revision 12 (2026-11-11)" and a new revision 12 row in the style of rows 9 and 10 ("Slice SE-2 built: ..."); the revision 11 row stays as it is (it was true when written). No rule or decision changes in meaning.
  - `src/sentaris_engine/application/evaluation.py` module docstring: replace "is OD-15" by a pointer to `execute_strategies` in `application/execution.py`.
  - `CLAUDE.md` "Current state": add the multi-strategy execution of stateless strategies over caller-built contexts to what exists, and remove "multi-strategy execution" from what does not exist.

- [ ] **Step 7: Run** `make check`. Expected: lint, typecheck, imports and tests all pass; report the numbers of the pytest summary.

- [ ] **Step 8: Commit**

```bash
git add src/sentaris_engine/application/execution.py src/sentaris_engine/application/evaluation.py tests/application/test_execute_strategies.py tests/support/probes.py docs/domain.md CLAUDE.md
git commit -m "feat(application): execute several stateless strategies for one as_of (SE-2)"
```

---

## Self-review: roadmap SE-2 against the plan

| Roadmap SE-2 | Named test |
|---|---|
| Acceptance: registration order does not change output | `test_report_order_does_not_depend_on_registration_order` |
| Acceptance: one strategy failing or raising leaves the others' results identical | `test_raising_strategy_does_not_change_the_other_entries`, `test_contract_breach_in_a_result_is_reported`, `test_mutating_strategy_is_reported_and_changes_nothing`, `test_strategy_raised_is_not_an_evaluation_failure` |
| Tests: permuted strategy order | `test_report_order_does_not_depend_on_registration_order`, `test_order_is_by_code_point_then_version` |
| Tests: a raising probe beside a healthy one, compared with the healthy one alone | `test_raising_strategy_does_not_change_the_other_entries` |
| Observable: one execution reports a result for each strategy, including the failed one | the two-entry assertions in the same test; `test_each_strategy_runs_once` |
| ADR-0002 order, duplicates, identity read once, no message, `BaseException` | `test_order_is_by_code_point_then_version`, `test_duplicate_identity_is_refused_before_anything_runs`, `test_identity_is_read_once`, `test_raised_exception_is_reported_by_type_name_only`, `test_base_exception_propagates` |
