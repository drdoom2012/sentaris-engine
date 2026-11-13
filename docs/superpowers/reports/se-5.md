# SE-5 — Execution over pairs: slice report

**Branch:** `se-5-execution` (from `main` at `e0498bd`; the specification and plan are in `639556f`), not merged, not pushed.  
**Specification:** `docs/superpowers/specs/2026-11-13-se-5-execution-over-pairs-design.md` (revision 4, approved 2026-11-13 together with its section 13).  
**Plan:** `docs/superpowers/plans/2026-11-13-se-5-execution-over-pairs.md` (revision 2, approved 2026-11-13).  
**Code:** `src/sentaris_engine/application/execution.py`. Tests are in `tests/application/test_execution_types.py` and `tests/application/test_execution.py`. Helpers are in `tests/application/execution_helpers.py`, `tests/application/type_name_cases.py` and `tests/application/type_name_other.py`.

## 1. Tasks

| Task | Implementer | Attempts | Review findings (spec / quality) | Fix rounds | Commits |
|---|---|---|---|---|---|
| T1 Value types, `qualified_type_name`, domain edits 1 and 2 | `opus` (plan: the descriptor reads and `str`-subclass handling of spec 5.5) | 1 | spec: compliant, 2 LOW; quality: approved, 2 LOW | 0 | `f07ede1` |
| T2 `execute`, `CLAUDE.md` | `opus` (plan: steps 1 to 8 of section 6.7, the narrow `try`, no foreign code) | 1 | spec: 1 MEDIUM, 2 LOW; quality: approved, 3 LOW. The MEDIUM and one LOW were the same finding: a literal U+FFFF in the N1 test. A second LOW was a gap against spec 5.3 step 4: a deleted identity slot raised `AttributeError` and was not refused | 1 (both re-reviews: all addressed, nothing new) | `16246b0`, `60f7aa9` |
| Whole-slice review | — | — | `slice-reviewer`: approved, 0 CRITICAL, 0 HIGH, 0 MEDIUM, 4 LOW; no question for the user | 1 fix wave (`sonnet`, fresh) and 1 scoped re-review: all addressed | `f3abf59` |

In T2's fix round, the findings were sent to the T2 implementer, which continued its session. The fix covered:

- the U+FFFF escape;
- the refusal of an identity with a deleted slot (ruling 1);
- `_refused` running the execution once (ruling 3);
- the call-count assertion in the N9 test.

Every review ran on Opus through a review agent. For SE-5 implementation, `.superpowers/dispatch-log.jsonl` records 11 dispatches, and the dispatch guard allowed all of them:

- 3 implementer dispatches: T1 and T2 on `opus`, the final fix wave on `sonnet`;
- 4 task reviews and 2 task re-reviews, by `spec-reviewer` and `quality-reviewer`, all on `opus`;
- 1 whole-slice review and 1 scoped re-review, by `slice-reviewer` on `opus`.

The guard does not log the T2 fix round, because that round continued an existing agent. The earlier sessions also logged three `slice-reviewer` dispatches for the specification and plan reviews.

## 2. `make check`

The orchestrator ran it on the final head `f3abf59`:

```text
All checks passed!                                  (ruff check)
52 files already formatted                          (ruff format --check)
Success: no issues found in 52 source files         (mypy strict)
Contracts: 2 kept, 0 broken.                        (import-linter)
============================= 1520 passed in 1.69s =============================
```

The orchestrator also ran `make check` after every step, and every run was clean: 1470 passed after T1, and 1520 after T2, after its fix round and after the fix wave. The orchestrator also checked these two things itself:

- the `docs/domain.md` word diff is exactly edits 1 and 2 of spec section 13;
- the N1 test file contains no literal U+FFFF after the fix: a byte grep counts 0, where it counted 3 before.

**Mutation checks reported by the implementers** (not re-run by the orchestrator):

- **T1** swapped in four naive `qualified_type_name` variants. They caused 16, 12, 6 and 12 test failures.
- **T2** made eight temporary breaking edits. Each one made at least one test fail:
  - catching `BaseException`;
  - no sort;
  - reading the identity per pair, or not copying it;
  - building the context from the caller's dict;
  - and others.

## 3. Acceptance criteria

| AC | Evidence |
|---|---|
| AC-1 Order | `test_pairs_run_in_code_point_order` (24 permutations × 2 dict insertion orders; the key set `"B"`, `"a"`, `"￿"`, `"\U00010000"`) |
| AC-2 Refusal before anything runs; empty execution | `test_duplicate_pair_is_refused`, `test_strategy_of_wrong_contract_is_refused`, `test_identity_is_read_once_and_checked`, `test_snapshot_mismatch_is_refused` (its positive case `execute(AS_OF, (), {})` gives an empty report, U7) |
| AC-3 Identity read once, before any evaluation | `test_identity_is_read_once_and_checked` |
| AC-4 Fault entries without message or value | `test_strategy_exception_is_isolated_to_its_pair`, `test_non_outcome_is_reported_as_fault` |
| AC-5 Non-ordinary exceptions propagate | `test_non_ordinary_exception_propagates` |
| AC-6 Module-qualified, safe type names | `test_type_name_is_module_qualified_and_safe`, `test_same_name_in_two_modules_differs`, `test_type_names_through_execute` |
| AC-7 Context per pair | `test_context_per_pair` |
| AC-8 Same entry alone and together | `test_entry_is_the_same_alone_and_together` (test strategies only; spec section 9) |
| AC-9 `Pair` and report types validated, final, frozen | `test_pair_is_validated`, `test_report_types_are_validated_final_and_frozen`, `test_refusal_error_is_its_own_class` |
| AC-10 `make check`, purity unchanged | Section 2. `sentaris_engine.application` is already in `PURE_SUBPACKAGES` and in the independence contract. No architecture list was widened and no dependency was added. |

Review Focus 1 to 5 from the plan:

| # | Test |
|---|---|
| 1 | `test_snapshots_dict_changed_during_run_changes_nothing`, with its second case: a `Pair` changed during the run (plan R5) |
| 2 | `test_strategy_of_wrong_contract_is_refused` (the class `RecordingStrategy` itself) |
| 3 | `test_strategy_exception_is_isolated_to_its_pair` (an exception that is hostile to inspection) |
| 4 | `test_outcome_is_reported_as_the_very_object` |
| 5 | `test_identity_is_read_once_and_checked` (two calls, two reads, equal reports) |

## 4. Rules enforced, with negative tests

| Rule | Enforced part | Negative tests |
|---|---|---|
| Domain 6.7 "Order", DR-10 | `(instrument, id, version)` code-point order, independent of the input order and the dict order | `test_pairs_run_in_code_point_order` |
| Domain 6.7 "Refused input" | Duplicate triples refused before anything runs | `test_duplicate_pair_is_refused` |
| Domain 6.7, U3 | Stateful strategies, objects of neither contract, a `__class__` that claims a contract, and both roots are all refused; no identity is read and no metaclass `__eq__` runs | `test_strategy_of_wrong_contract_is_refused` |
| Domain 6.7, 6.4 | Identity read once per strategy object, before any evaluation. A bad, mutated or slot-deleted identity is refused or not reported. A raising read is chained, and an interrupt propagates | `test_identity_is_read_once_and_checked` |
| U5, U7, U8, domain 6.7 "One `as_of`", "Snapshot" | Missing, surplus, wrong-`as_of` and shared snapshots are refused, along with malformed containers, keys and `as_of`, `from None`. No foreign `__hash__` or `__eq__` runs | `test_snapshot_mismatch_is_refused` |
| Domain 6.7 "A strategy that raises", DR-22, U1, U2, U4 | `Exception` becomes a `RAISED` fault for that pair only, with no message in any field or `repr` | `test_strategy_exception_is_isolated_to_its_pair` |
| Domain 6.7, U4 | A non-outcome becomes a `RETURNED_NON_OUTCOME` fault named by its type; the value is not kept | `test_non_outcome_is_reported_as_fault` |
| Domain 6.7, U1 | `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` and other `BaseException` subclasses propagate as the same object, unchained, and no later pair runs | `test_non_ordinary_exception_propagates` |
| U2, U9, SE-4 spec 5.6 | Type names read through `type`'s descriptors, with no metaclass or `str`-subclass code run, and the qualname used when no module is recorded | `test_type_name_is_module_qualified_and_safe`, `test_same_name_in_two_modules_differs`, `test_type_names_through_execute` |
| Domain 6.7 "Snapshot", 6.8 | Each context holds its instrument's very snapshot, the pair's parameters and the execution's `as_of`, and no instrument key | `test_context_per_pair` |
| DR-22, DR-13, domain 6.7 "Report" | An entry is the same alone and together; repeated runs are equal (test strategies) | `test_entry_is_the_same_alone_and_together` |
| DR-23 | An outcome is passed through as the very object, in its own order | `test_outcome_is_reported_as_the_very_object` |
| Domain 6.8, U6 | `Pair` refuses an invalid key and non-`Parameters`; its strategy is never touched (F8) | `test_pair_is_validated` |
| SE-5 spec 5.2 | Report types validated, final and frozen; `FaultCause` has exactly two members | `test_report_types_are_validated_final_and_frozen` |

**Convention or review only** (spec section 9):

- **Purity of a strategy**, and so DR-22 for strategies that share mutable state behind the engine's back. N11 shows independence for the test strategies only.
- **The `try` wraps only the `evaluate_stateless` call.** N6 to N8 show what is caught; that no engine code sits inside the `try` rests on review. All four reviews checked it.
- **Execution reads no payload, parameter value or state, and keeps nothing between calls** (DR-23, DR-25). The SE-1 purity checks cover the clock and I/O.
- **Reading `identity`** runs strategy code once, before any evaluation. A strategy that does more in that property is review only.
- **A class-dict hash collision with `"__module__"`** runs a planted `__eq__`. This is an accepted limitation, now cited in the `qualified_type_name` docstring.
- **Finalizers** (`__del__`) of dropped objects run when the interpreter decides.
- **An exception object the strategy stored elsewhere** is outside the engine's control.

## 5. Cost

These figures are measured, not estimated. The `usage` of every model response was read from the Claude Code transcripts in `~/.claude/projects/<project>/<session>.jsonl` and `<session>/subagents/agent-*.jsonl`, counting each response once by its message id.

Prices are those of the `claude-api` skill (cached 2026-11-03), in USD per million tokens:

| Model | Input | Output | Cache read |
|---|---|---|---|
| Opus 5.5 | 4.00 | 20.00 | 0.20 |
| Sonnet 5.5 | 2.00 | 10.00 | 0.10 |

A cache write costs 1.25 × input with a 5-minute TTL, and 2 × input with a 1-hour TTL. The amounts are list prices on the API; the cost under a subscription plan differs.

| Stage | Dispatch | Model | USD |
|---|---|---|---:|
| Specification | `slice-reviewer` spec review + re-review | Opus 5.5 | 1.22 |
| Specification | orchestrator session `c4d379c8` | Opus 5.5 | 2.94 |
| Plan | `slice-reviewer` plan review | Opus 5.5 | 1.44 |
| Plan | orchestrator session `a57a78a4` | Opus 5.5 | 2.10 |
| T1 | implementer | Opus 5.5 | 1.34 |
| T1 | spec review / quality review | Opus 5.5 | 0.40 / 0.31 |
| T2 | implementer, fix round included | Opus 5.5 | 1.98 |
| T2 | spec review / quality review | Opus 5.5 | 0.52 / 0.52 |
| T2 | spec re-review / quality re-review | Opus 5.5 | 0.18 / 0.09 |
| Whole slice | `slice-reviewer` review | Opus 5.5 | 0.77 |
| Whole slice | fix wave | **Sonnet 5.5** | **0.16** |
| Whole slice | `slice-reviewer` re-review | Opus 5.5 | 0.20 |
| Implementation | orchestrator session `be1ecb73`, up to this report | Opus 5.5 | 4.44 |
| **Total** | | | **18.62** |

By model:

| Model | USD |
|---|---:|
| Opus 5.5, subagents | 8.98 |
| Opus 5.5, orchestrator | 9.48 |
| Sonnet 5.5 | 0.16 |

The cost by stage:

| Stage | USD |
|---|---:|
| Specification | 4.16 |
| Plan | 3.54 |
| Implementation, reviews and completion | 10.92 |

**Sonnet's work** was one dispatch, the final fix wave: 6 model calls, 3 019 output tokens, 0.16 USD. Both implementation tasks ran on Opus, as the approved plan required, and the user confirmed this before implementation.

The orchestrator is the largest single item, about half of the total. Most of it is cache reads, because every turn re-reads the whole context: 9.7 M cache-read tokens in the implementation session alone. The orchestrator figure for `be1ecb73` stops at the point this report was written and leaves out the presentation that follows.

Sessions are counted only when they have a SE-5 dispatch in the dispatch log. A SE-5 conversation without any dispatch is not counted.

## 6. Known limitations

- **A `Pair` changed and then reused (S-L2, whole-slice Minor 3).** Spec 5.3 step 1 trusts a pair's fields as validated by `Pair`. A strategy could change a `Pair` with `object.__setattr__` during one execution, and the composition root could then reuse that `Pair` in a later one. In that case the later execution fails closed during step 2 or step 7, with an `EvaluationTypeError` from `EvaluationContext` or a hashed `str` subclass, instead of being refused up front. This was left as specified (ruling 5).
- **The class-dict hash collision and finalizers**, as accepted in spec section 9 (section 4 above).
- **Surrogates in a type name** (spec section 11, question 1). The name is reported as read. Whether it must be encodable belongs to delivery (OD-11).
- **`docs/roadmap.md:3` still says "Nothing is built".** This predates SE-5, and spec section 10 forbids roadmap changes in this slice.
- CI has not run on GitHub (no push).
- **Deferred LOW items** that the whole-slice review judged safe to keep:
  - `# noqa: S102` on the `exec` the brief prescribes (`type_name_cases.py`), and `# noqa: BLE001` on the evaluation `except Exception`, which cites U1;
  - `typing.Any` in the test helpers;
  - the narrow `# type: ignore[misc]` on `raise self.outcome` in `execution_helpers.py`;
  - literal `type_name_cases.<locals>.` prefixes in expected names that do not depend on the module name.
- **The fix-wave commit `f3abf59`** carries the trailer `Co-Authored-By: Claude Opus 5.5`, as the controller's brief prescribed, although Sonnet 5.5 wrote it.

## 7. Rulings made

1. **The deleted identity slot was fixed in T2's round (Q-L2), not deferred.** Spec 5.3 step 4 and 5.4 already decide that the execution is refused with `ExecutionRefusedError` `from None`. The fix adds one narrow `try`/`except AttributeError` around the two slot reads, after the exact-type check, plus a negative test. If wrong: one extra `try`.
2. **Two T2 LOW items were fixed in the same round instead of deferred:** `_refused` now runs the execution once, and `test_type_names_through_execute` asserts the call count. If wrong: a few lines of test churn.
3. **`_refused` does not call `raises_exactly`.** It asserts `type(exc) is ExecutionRefusedError` itself and returns the object for the chaining checks. The plan constraint's intent holds: the exact class is checked and the message never is. It also avoids reading `identity` twice. Both re-reviews and the whole-slice review accepted this. If wrong: a test helper that duplicates three lines of `raises_exactly`.
4. **The final fix wave ran on `sonnet`:** comment, docstring and test changes, plus `seen` turned into a `set` (slice rule 4). If wrong: an extra fix round.
5. **Whole-slice Minor 3 was not applied** (re-checking `Pair` fields in step 1). Spec 5.3 step 1 trusts the pair's instrument, and the re-review agreed. If wrong: see the first item of section 6.
6. **"plan R1" is the citation at `qualified_type_name`**, not spec re-review R1. Plan ruling R1 is about that very function, and the re-review agreed. If wrong: one word.

The plan's own rulings R1 to R5 were approved by the user before implementation. The pre-flight scan of the plan found no conflicts.

## 8. Open questions for the user

1. **Domain section 4, "Every rule is unimplemented"** (carried over from the SE-3 and SE-4 reports). SE-2 to SE-5 now have negative tests for parts of several rules. Should that sentence change?
2. **`docs/roadmap.md:3`, "Nothing is built"**: should it be updated in a separate change?
