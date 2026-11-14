# SE-7a — Input declaration: slice report

**Branch:** `se-7a-input-declaration` (from `main` at `b6c3f31`; carries the domain section 6.9 decision and amendments `a8a8518`, `4973ee9`, the roadmap change `4560dbd`, the specification `a0c9f22` and the plan `c2a005a`, `aedfc99`). Not merged, not pushed.  
**Specification:** `docs/superpowers/specs/2026-11-13-se-7a-input-declaration-design.md` (revision 3, approved 2026-11-14).  
**Plan:** `docs/superpowers/plans/2026-11-14-se-7a-input-declaration.md` (revision 2, approved 2026-11-14).  
**Code:** `src/sentaris_engine/domain/declaration.py`, `src/sentaris_engine/domain/declaring.py`, `declare` in `src/sentaris_engine/domain/strategy.py`.  
**Tests:** `tests/domain/test_declaration.py`, `tests/domain/test_declaring.py`, new tests in `tests/domain/test_strategy.py`; a `declare` on every test strategy in `tests/domain/strategy_helpers.py`, `tests/domain/test_evaluation.py`, `tests/domain/test_strategy.py`, `tests/application/execution_helpers.py` and `tests/application/test_execution.py`.

## 1. Tasks

| Task | Implementer | Attempts | Review findings (spec / quality) | Fix rounds | Commits |
|---|---|---|---|---|---|
| T1 Input kinds, needs, declarations, `union`, `requirements` | `sonnet` | 1 | spec: compliant, 2 LOW; quality: approved, 1 LOW | 0 (LOWs deferred) | `7878b69` |
| T2 `declare` on the contracts, `NotADeclaration`, `declare_inputs`, test strategies, `CLAUDE.md` | `sonnet` | 1 | spec: compliant, 1 LOW; quality: approved, 3 LOW | 0 (LOWs deferred) | `f789b9d` |
| Whole slice | `sonnet` (fix wave) | — | `slice-reviewer`: approved with changes, 0 CRITICAL, 0 HIGH, 1 MEDIUM, 3 LOW; deferred minors triaged; no question for the user | 1 (4 findings fixed; scoped re-review: all addressed, no new problem) | `8edac2d` |

No review found a CRITICAL or HIGH issue. The only MEDIUM was a wrong citation (`U3`) in the `NotADeclaration` docstring, which was also the T2 spec reviewer's LOW.

`.superpowers/dispatch-log.jsonl` records 9 SE-7a dispatches for implementation, and the dispatch guard allowed all of them:
- 3 implementer dispatches, all on `sonnet` (T1, T2, final fix wave);
- 4 task reviews by `spec-reviewer` and `quality-reviewer`, all on `opus`;
- 1 whole-slice review and 1 scoped re-review by `slice-reviewer`, on `opus`.

Earlier sessions logged 3 `slice-reviewer` dispatches for the specification review, its re-review and the plan review.

## 2. `make check`

The orchestrator ran it on the final head `8edac2d`:

```text
All checks passed!                                    (ruff)
72 files already formatted                            (ruff format)
Success: no issues found in 72 source files           (mypy strict)
Contracts: 2 kept, 0 broken.                          (import-linter)
============================= 2357 passed in 2.25s =============================
```

It also ran `make check` after each task: 2336 passed after T1 (SE-6's 2274 plus 62), 2357 after T2. `git diff b6c3f31 -- pyproject.toml uv.lock tests/architecture` is empty (AC-9). The SE-1 purity checks find domain modules by `rglob`, so they cover the new modules without changing a pinned list (quality review of T2).

## 3. Acceptance criteria

| AC | Evidence |
|---|---|
| AC-1 `InputKind`: three members, plain `Enum`, final | `test_input_kind_has_exactly_the_section_5_inputs`, `test_new_types_are_final_and_immutable_declaration` (finality of an `Enum` with members is also shown by mypy's `@final`) |
| AC-2 `InputNeed` accepts exactly 5.2 | `test_input_need_refuses_malformed_fields`, `test_input_need_accepts_boundary_durations`, `test_the_same_period_of_two_kinds_is_two_series` |
| AC-3 `Declaration` refusals, empty, canonical order | `test_declaration_refuses_malformed_needs`, `test_declaration_refuses_a_repeated_series`, `test_declaration_order_is_independent_of_need_order` (all 24 permutations) |
| AC-4 Contracts have exactly `identity`, `evaluate`, `declare`; signature; `declare` required | `test_contract_signatures_take_only_the_transition_inputs_contracts` (extended), `test_declare_signature_takes_only_the_parameters`, `test_strategy_without_declare_cannot_be_instantiated` |
| AC-5 `declare_inputs` steps 1 to 5 | `test_declare_inputs_refuses_malformed_inputs_without_calling_declare`, `test_declare_inputs_passes_only_the_parameters`, `test_declare_inputs_returns_a_declaration_as_the_very_object`, `test_declare_inputs_returns_an_evaluation_failure_as_the_very_object`, `test_declare_inputs_reports_a_non_declaration_by_type_only`, `test_declare_inputs_propagates_an_exception_unchanged`, `test_declare_inputs_does_not_read_identity`, `test_declare_inputs_serves_both_contracts` |
| AC-6 `union` | `test_union_keeps_the_longest_lookback_per_series`, `test_union_is_independent_of_declaration_order`, `test_union_refuses_malformed_input` |
| AC-7 `requirements` | `test_requirements_are_in_code_point_key_order`, `test_requirements_never_combine_two_instruments`, `test_requirements_edge_inputs`, `test_requirements_refuse_malformed_input` |
| AC-8 New types final and immutable | `test_new_types_are_final_and_immutable_declaration`, `test_new_types_are_final_and_immutable_declaring` |
| AC-9 `make check`, no architecture list widened | Section 2 |

Review Focus 1 to 5 of the plan each have the test the plan names. Every SE-4 and SE-5 test asserts what it asserted before; the only assertion edit is the planned `expected = frozenset({"identity", "evaluate", "declare"})`.

## 4. Rules enforced, with negative tests

| Rule | Enforced part | Negative test |
|---|---|---|
| Section 6.9 "Shared reading" | longest lookback per series, one need per series | `test_union_keeps_the_longest_lookback_per_series` |
| DR-10 | union, declaration and requirements independent of input order | `test_union_is_independent_of_declaration_order`, `test_declaration_order_is_independent_of_need_order`, `test_requirements_are_in_code_point_key_order` |
| Section 6.7 "Snapshot" | instruments never combined | `test_requirements_never_combine_two_instruments` |
| Section 6.9 "One lookback per series" (U3, U4) | a repeated series is malformed; empty is valid | `test_declaration_refuses_a_repeated_series`, `test_declaration_order_is_independent_of_need_order` |
| Section 6.9 "Declaration", 6.8 | `declare` takes only the parameters, contract and call side, both contracts | `test_declare_signature_takes_only_the_parameters`, `test_declare_inputs_passes_only_the_parameters`, `test_declare_inputs_serves_both_contracts` |
| Section 6.9 "Declaration failure" (U2) | a failure is returned as the very object | `test_declare_inputs_returns_an_evaluation_failure_as_the_very_object` |
| Spec 5.5 steps 4 and 5 (OD-13, OD-3 left open) | anything else reported by type only; nothing caught; identity not read | `test_declare_inputs_reports_a_non_declaration_by_type_only`, `test_declare_inputs_propagates_an_exception_unchanged`, `test_declare_inputs_does_not_read_identity` |
| Section 5 | exactly three inputs | `test_input_kind_has_exactly_the_section_5_inputs` |
| SE-3 value-type rules | shapes, exact types, final, immutable | the refusal tests of section 3 and both `test_new_types_are_final_and_immutable_*` |

**Structural:** a need has no instrument field.

**Convention, review-only:** that a strategy's `declare` depends only on its version and parameters and is pure (section 6.9, DR-08); the SE-1 purity checks cover strategy modules as they do for `evaluate`.

**Not enforced in this slice** (spec 9): narrowing and sufficiency per pair (SE-7b, SE-10); that a pair whose declaration failed is not evaluated and adds nothing to the shared reading, which is wired where `declare_inputs` is called (SE-7b).

## 5. Token usage

As reported by the subagent results (`subagent_tokens`):

| Dispatch | Tokens |
|---|---|
| T1 implementer | 65 580 |
| T1 spec review / quality review | 39 375 / 30 920 |
| T2 implementer | 96 480 |
| T2 spec review / quality review | 60 202 / 48 463 |
| Whole-slice review | 86 670 |
| Final fix wave | 43 362 |
| Scoped re-review | 17 300 |

## 6. Known limitations and rulings

- Deferred LOW findings left as they are, by the whole-slice reviewer's triage:
  - the `InputKind` subclass case in `test_new_types_are_final_and_immutable_declaration` passes even without `@final`, because an `Enum` with members refuses subclassing; mypy covers the annotation;
  - `test_requirements_refuse_malformed_input` builds cases from `pytest.param`'s public `values` and `id`;
  - `union` starts `max` from `0`, which is correct because lookbacks are at least 1;
  - `test_declare_inputs_refuses_malformed_inputs_without_calling_declare` registers a local virtual subclass with `ABCMeta.register` and does not undo it (SE-4 precedent).
- Out of scope, left: the module docstring of `tests/domain/test_strategy.py` does not cite section 6.9 or the SE-7a tests it now holds.
- Ruling by the orchestrator (implementation only): the final fix wave also took the three optional LOWs (stateful `args[0] is params`, `strategy.py` docstring, `Callable` annotation) together with the MEDIUM, because they cost one dispatch together.
- No finding touched an `OD-xx`, a `DR-xx` or domain section 6; nothing went to the user during implementation.
