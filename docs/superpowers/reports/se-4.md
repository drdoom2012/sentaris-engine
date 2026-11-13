# SE-4 — Strategy contract and stateless evaluation: slice report

**Branch:** `se-4-strategy-contract` (from `main` at `40189df`; the specification and plan are in `644c1c3` to `9029f0b`), not merged, not pushed.  
**Specification:** `docs/superpowers/specs/2026-11-13-se-4-strategy-contract-design.md` (revision 4, approved 2026-11-13 together with its section 13; 5.4 step 4 amended under R1).  
**Plan:** `docs/superpowers/plans/2026-11-13-se-4-strategy-contract.md` (revision 3, approved 2026-11-13).  
**Code:** `src/sentaris_engine/domain/strategy.py`, `src/sentaris_engine/domain/evaluation.py`. Tests are in `tests/domain/test_strategy.py`, `tests/domain/test_evaluation.py` and the helpers in `tests/domain/strategy_helpers.py`.

## 1. Tasks

| Task | Implementer | Attempts | Review findings (spec / quality) | Fix rounds | Commits |
|---|---|---|---|---|---|
| T1 Strategy identity, contracts, `NO_STATE`, `StateTransition`, domain edits | `sonnet` | 1 | spec: 1 HIGH, 1 LOW; quality: 2 Important, 3 Minor. The HIGH and the first Important were the same: `StateTransition` checked the outcome with a tuple `not in`, which runs a metaclass `__eq__` | 1 (both re-reviews: all 4 addressed, nothing new) | `2815180`, `c1aea7b` |
| T2 Stateless evaluation, `NotAnOutcome`, `CLAUDE.md` | `opus` (no exception caught, nothing but the type of the returned value read, determinism check shown to work) | 1 | spec: compliant, 3 Minor; quality: approved, 3 Minor | 0 | `57ea4fd` |
| Whole-slice review | — | — | `slice-reviewer`: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 3 LOW. One to fix before merge (F1); two may stay (F2, F3) | 1 fix wave (`opus`, the T2 implementer continued) and 1 scoped re-review: F1 addressed | `db58456` |

The second Important finding in T1 was this: any class could pass `contract=True` and so get around the both-contracts refusal. The fix refuses `contract=True` for a class that already inherits a root, or once two roots exist, and it counts roots with `>= 2`. See ruling 1.

Every review ran on Opus through a review agent. For SE-4 implementation, `.superpowers/dispatch-log.jsonl` records 10 dispatches, and the dispatch guard allowed all of them:

- 2 implementer dispatches: T1 on `sonnet`, T2 on `opus`;
- 4 task reviews and 2 task re-reviews, by `spec-reviewer` and `quality-reviewer`, all on `opus`;
- 1 whole-slice review and 1 scoped re-review, by `slice-reviewer` on `opus`.

The T1 fix round and the final fix wave continued the existing implementers through a message. The dispatch guard does not log such continuations. The specification and plan reviews ran in earlier sessions.

## 2. `make check`

The orchestrator ran it on the final head `db58456`:

```text
All checks passed!                                  (ruff check)
45 files already formatted                          (ruff format --check)
Success: no issues found in 45 source files         (mypy strict)
Contracts: 2 kept, 0 broken.                        (import-linter)
============================= 1441 passed in 1.67s =============================
```

The orchestrator also ran `make check` after each step, and every run was clean: 1403 passed after T1, 1406 after the T1 fix, 1439 after T2 and 1441 after the fix wave.

**Mutation check (orchestrator).** I added a tuple-membership outcome check (`type(value) in (Signals, NoSignal, EvaluationFailure)`) ahead of the three `is` checks in `evaluation.py`. `test_non_outcome_with_hostile_metaclass_is_reported` then failed (1 failed, 31 passed). With the file restored, all 32 tests in `test_evaluation.py` pass.

The T2 implementer reported five further temporary breaking edits, and each one made the matching Review Focus test fail:

- `isinstance` membership;
- an `in`/`isinstance` outcome check;
- `isinstance` validation of `NotAnOutcome`;
- `try`/`except`;
- reading `identity` and calling with a keyword.

## 3. Acceptance criteria

| AC | Evidence |
|---|---|
| AC-1 Identity | `test_invalid_strategy_identity_is_refused`, `test_strategy_identity_accepts_any_non_empty_str` |
| AC-2 Contracts | `test_contract_signatures_take_only_the_transition_inputs_contracts`, `test_contract_signatures_take_only_the_transition_inputs_evaluation`, `test_strategy_cannot_take_both_contracts`, `test_contract_requires_evaluate_and_identity` |
| AC-3 `NO_STATE` | `test_no_state_marker` |
| AC-4 Stateless evaluation | `test_outcome_is_returned_unchanged`, `test_non_outcome_result_is_reported_as_value`, `test_not_an_outcome_is_validated`, `test_strategy_exception_propagates_unchanged`, `test_malformed_evaluation_arguments_are_refused`, `test_evaluate_is_called_positionally`, plus the Review Focus tests `test_non_outcome_with_hostile_metaclass_is_reported`, `test_non_outcome_value_is_not_touched`, `test_non_outcome_of_any_metaclass_is_reported`, `test_virtual_subclass_is_refused`, `test_indirect_subclass_is_accepted`, `test_identity_is_not_read` |
| AC-5 Determinism | `test_repeated_stateless_evaluation_is_identical`, `test_determinism_check_detects_a_varying_strategy`. These cover the included test strategies only (section 4). |
| AC-6 Independence | `test_evaluation_is_independent_of_other_strategies` |
| AC-7 `StateTransition` | `test_state_transition`, `test_state_transition_refuses_a_non_outcome`, `test_state_transition_refuses_not_an_outcome`, `test_state_transition_refuses_a_class_whose_metaclass_equals_an_outcome` |
| AC-8 Final, frozen | `test_new_types_are_final_and_frozen_strategy`, `test_new_types_are_final_and_frozen_evaluation` |
| AC-9 Gate and purity | `make check` above. The SE-1 purity checks cover both new modules, no list in `tests/architecture/` changed, and no dependency was added. |

`test_not_an_outcome_repr_runs_no_strategy_code` and `test_state_transition_repr_runs_no_state_code` were added by the fix wave (F1).

The document changes of spec section 13 (edits 1 to 6) are in `2815180`. The orchestrator, the T1 spec review and the whole-slice review each compared them with the specification character by character. Nothing else in `docs/` changed. `CLAUDE.md` changed only in "Current state" (`57ea4fd`).

## 4. Rules enforced, with negative tests

| Rule | Enforced part | Negative tests |
|---|---|---|
| Domain 6.4 | Identity is two non-empty exact `str` fields, with no other rule | `test_invalid_strategy_identity_is_refused` |
| DR-12 (contract part), DR-26, domain 6.8 | The contracts and `evaluate_stateless` take only the transition inputs: no mode flag, no instrument key | `test_contract_signatures_take_only_the_transition_inputs_contracts`, `test_contract_signatures_take_only_the_transition_inputs_evaluation` |
| Domain 6.4 | One contract per strategy, checked when the class is defined; no virtual subclass | `test_strategy_cannot_take_both_contracts`, `test_virtual_subclass_is_refused` |
| DR-23, domain 6.2 | The outcome is returned as the very object, never filtered, rebuilt or reordered | `test_outcome_is_returned_unchanged` |
| Domain 6.7 (left to execution), U3 | A non-outcome is returned as a new `NotAnOutcome` that holds only the type; a spoofed or hostile value is not accepted as an outcome and is not touched | `test_non_outcome_result_is_reported_as_value`, `test_non_outcome_with_hostile_metaclass_is_reported`, `test_non_outcome_value_is_not_touched` |
| Domain 6.7 (left to execution) | Every strategy exception propagates unchanged, `BaseException` included | `test_strategy_exception_propagates_unchanged` |
| DR-26 | Repeated evaluation is identical for the test strategies, and the check detects a varying one | `test_repeated_stateless_evaluation_is_identical`, `test_determinism_check_detects_a_varying_strategy` |
| DR-22 | One evaluation call carries nothing from another | `test_evaluation_is_independent_of_other_strategies` |
| DR-25, U1, U2 | The absent-state marker; `next_state` held as given, never copied; `repr` runs no state code | `test_no_state_marker`, `test_state_transition`, `test_state_transition_repr_runs_no_state_code` |
| SE-4 spec 5.6 | `repr` of a `NotAnOutcome` runs no strategy-controlled code | `test_not_an_outcome_repr_runs_no_strategy_code` |
| SE-4 spec 5 (final) | No new value type can be subclassed or have a field reassigned | `test_new_types_are_final_and_frozen_*` |

U3 is not enforced by SE-4; it belongs to SE-5. N4 only shows that the returned type is available to SE-5.

**Convention or review only:**

- **Purity of a strategy itself** (DR-08, DR-26). It is checked statically only for `sentaris_engine.strategies` (SE-1). N7 shows determinism only for the three included test strategies. In two of the three N7 cases the strategy returns the same object on every call, so only `ContextSignalStrategy` exercises equality by value (F3).
- **DR-12 inside a concrete strategy.** Nothing detects an extra defaulted parameter or a mode branch.
- **The engine never reads a payload** (DR-23). Nothing reads one between the call and the return, but only review shows this.
- **No `try` in `evaluation.py`, and nothing kept between calls.** Both rest on review; no static check covers them. N5 shows propagation by behavior.
- **One contract after definition** (F2). The refusal runs only when a class is defined. Reassigning `__bases__`, calling `ABCMeta.__new__` directly or reassigning `_ContractMeta._roots` gets around it.
- **A strategy that raises `EvaluationTypeError`** looks like an argument refusal (spec section 9). SE-5 handles this.
- **Private reachability and re-calling `__init__`**, as in SE-3 (`NoState._instance`, `_ContractMeta._roots`).

## 5. Token usage

Subagent tokens as reported by the subagent results in this session (cumulative where an agent was continued):

| Task | Implementer | Spec review | Quality review |
|---|---|---|---|
| T1 | 71 681; 77 767 after the fix round | 54 316; re-review 23 758 | 37 333; re-review 20 410 |
| T2 | 89 880; 93 552 after the final fix wave | 58 369 | 42 767 |

Whole slice: the review used 74 667 tokens and its scoped re-review 16 524. The fix wave is included in the T2 implementer figure. The orchestrator's own usage is not reported.

## 6. Known limitations

- **F2.** One-contract uniqueness is checked only when a class is defined (section 4). Note for SE-5: when execution tells the two contracts apart, it should check that exactly one root is in the real MRO, and not rely on the definition-time refusal alone.
- `NO_STATE` is defined within one process only. Pickling and restoring it across processes is untested and belongs to SE-14/OD-20 (spec 5.3).
- The plan's `# type: ignore[override]` on the positional-only `evaluate` in `test_evaluate_is_called_positionally` was left out, because mypy reports nothing there and an unused ignore fails strict mypy (ruling 4).
- CI has not run on GitHub (no push).
- The whole-slice review judged these LOW items safe, and they stay deferred:
  - `check_deterministic` compares with `!=`, so a strategy that deterministically returns a non-outcome would be reported as varying (`NotAnOutcome` compares by identity, R2). With an empty `contexts` it raises `IndexError` instead of `AssertionError`.
  - `ABCMeta.register` in `test_virtual_subclass_is_refused` stays registered for the rest of the test process.
  - Parametrised exception and strategy instances are created at module level and mutated by the tests. This matters only if a test is rerun in the same process.
  - `test_outcome_is_returned_unchanged` evaluates the `Signals` case a second time instead of reusing the first result.

## 7. Rulings made

1. **The `contract=True` bypass (T1).** The plan's keyword is kept. The metaclass refuses `contract=True` for a class that already inherits a root, or once two roots exist, and it counts roots with `>= 2`. This follows spec 5.2 ("a class that derives from both is refused"). If wrong, one metaclass guard needs rework.
2. **T1 test split.** The refusal cases of `test_state_transition` are in the parametrised sibling `test_state_transition_refuses_a_non_outcome`. Every case from the brief is present, and every named test exists. If wrong, this costs a rename.
3. **Two T1 minors folded into the fix round:** the N1 filter now drops only the exact `str` `"1"`, and a property-identity twin was added for `StatefulStrategy`. If wrong, nothing is lost.
4. **The `# type: ignore[override]` omitted (T2).** The Global Constraints call for ignores only on misuse that mypy flags, and an unused ignore fails strict mypy. If wrong, this costs one comment.
5. **F2 recorded, not fixed.** It needs deliberate meta-level circumvention, the same class as the private-attribute reachability in spec section 9. It is recorded here as a known limitation and a note for SE-5, with no code change and no spec edit. If wrong, SE-5 adds the check.
6. **F3 and the five deferred minors stay**, following the whole-slice review's triage. If wrong, these are small test edits.

The plan's own rulings R1 to R3 were approved by the user before implementation.

## 8. Open questions for the user

1. **Domain section 4, "Every rule is unimplemented"** (carried over from SE-3, question 2). SE-2 to SE-4 have negative tests for parts of several DRs. Should that sentence change? And should enforcement evidence be recorded in the domain document, or only in the slice reports?
2. **For SE-5** (spec section 11, questions 3 and 4, not decided here): which `BaseException` subclasses count as "ordinary", and whether a reported type name is bare or module-qualified.
