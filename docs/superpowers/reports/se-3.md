# SE-3 — Evaluation types: slice report

**Branch:** `se-3-evaluation-types` (from `main`; the specification and plan are in `bd53961`), not merged, not pushed.  
**Specification:** `docs/superpowers/specs/2026-11-12-se-3-evaluation-types-design.md` (revision 5, approved 2026-11-12 together with its section 13).  
**Plan:** `docs/superpowers/plans/2026-11-12-se-3-evaluation-types.md` (revision 3, approved 2026-11-12).  
**Code:** `src/sentaris_engine/domain/{errors,timing,instrument,parameters,signal,result,rows,snapshot,context}.py`, `has_surrogate` made public in `payload.py`. Tests are under `tests/domain/`.

## 1. Tasks

| Task | Implementer | Attempts | Review findings (spec / quality) | Fix rounds | Commits |
|---|---|---|---|---|---|
| T1 Time, instrument key, `Parameters`, document edits | `opus` (canonical equality, exception discipline over pair sources, domain document edits) | 1 | spec: compliant, 5 LOW; quality: approved, 2 LOW | 0 | `513b94d` |
| T2 `Signal` and `Result` | `sonnet` | 1 | spec: compliant, 2 LOW; quality: approved, 4 LOW | 0 | `6247d1e` |
| T3 Rows | `sonnet` | 1 | spec: 1 MEDIUM, 4 LOW; quality: 2 MEDIUM, 1 LOW (one MEDIUM was the same in both reviews: a `# type: ignore` that only made up for a loose test annotation) | 1 (both re-reviews: all 4 addressed; 1 new LOW) | `b03f5d6`, `87b566e` |
| T4 `Snapshot`, `EvaluationContext`, `CLAUDE.md` | `opus` (availability boundary, ordering contract, nested-container discipline) | 1 | spec: compliant, 3 LOW; quality: approved, 2 LOW | 0 | `925f5e1` |
| Whole-slice review | — | — | `slice-reviewer`: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 5 LOW (one of them needs a user decision) | 1 fix wave (`sonnet`) and 1 scoped re-review: all 4 items addressed | `f3181b5` |

All reviews ran on Opus through the review agents. For SE-3, `.superpowers/dispatch-log.jsonl` records 20 dispatches, all allowed by the dispatch guard:

- before implementation: 3 `slice-reviewer` dispatches (two specification reviews, one plan review);
- 5 implementer dispatches: T1 and T4 on `opus`; T2, T3 and the final fix wave on `sonnet`;
- 8 task reviews and 2 task re-reviews (`spec-reviewer`, `quality-reviewer`, all `opus`);
- 1 whole-slice review and 1 scoped re-review (`slice-reviewer`, `opus`).

The T3 fix round continued the existing implementer through a message. The dispatch guard does not log such continuations.

## 2. `make check`

The orchestrator ran it on the final head `f3181b5`:

```text
All checks passed!                                  (ruff check)
40 files already formatted                          (ruff format --check)
Success: no issues found in 40 source files         (mypy strict)
Contracts: 2 kept, 0 broken.                        (import-linter)
============================= 1345 passed in 1.64s =============================
```

The orchestrator also ran `make check` after every task: 672, 756, 1139 (T3 before and after its fix) and 1335 passed. Each run was clean.

**Mutation check (orchestrator):** I disabled the three `as_of` comparisons in `snapshot.py`. `test_row_after_as_of_is_refused` and `test_candle_boundary_at_max_time` then failed. With the file restored, all 44 tests in `test_snapshot.py` pass. The T3 implementer reported a similar check: removing `is_finite()` makes 33 tests fail.

## 3. Acceptance criteria

| AC | Evidence |
|---|---|
| AC-1 Time ranges | `test_invalid_instant_is_refused`, `test_invalid_duration_is_refused`, `test_valid_time_is_returned` |
| AC-2 Instrument key | `test_invalid_instrument_key_is_refused`, `test_instrument_key_is_opaque` |
| AC-3 `Parameters` | `test_invalid_parameters_are_refused`, `test_parameters_equality_is_canonical`, `test_parameters_hold_values` |
| AC-4 `Signal` and outcomes | `test_signals_outcome_requires_signals`, `test_signals_keep_order_and_duplicates`, `test_failure_requires_code`, `test_outcomes_are_distinct`, `test_invalid_signal_is_refused`, `test_signal_equality_is_canonical`, `test_replace_revalidates` (`test_result.py`) |
| AC-5 Rows | `test_invalid_row_field_is_refused`, `test_decimal_nan_kinds_are_refused`, `test_funding_rate_is_signed_but_never_negative_zero`, `test_nullable_fields`, `test_rows_compare_by_fields`, `test_replace_revalidates` (`test_rows.py`) |
| AC-6 Snapshot | `test_invalid_snapshot_shape_is_refused` (N11), `test_unordered_or_duplicate_series_is_refused` (N7), `test_row_after_as_of_is_refused` and `test_candle_boundary_at_max_time` (N8), `test_snapshot_mappings_iterate_in_key_order` (N13), `test_absent_and_empty_inputs`, `test_snapshot_replace_is_refused` |
| AC-7 Context | `test_invalid_context_field_is_refused` (N12), `test_context_as_of_must_match_snapshot` (N9), `test_context_identity` |
| AC-8 Immutable, final | `test_types_are_immutable_{parameters,result,rows,snapshot}` (N10), `test_types_cannot_be_subclassed_{parameters,result,rows,snapshot}` (N14) |
| AC-9 Gate and purity | `make check` above. The SE-1 purity checks cover the new modules, and no list in `tests/architecture/` changed. |
| AC-10 Only `EvaluationTypeError` | `test_malformed_input_raises_only_evaluation_type_error_{parameters,parameters_value,result,rows,snapshot}` (N15). The `MAX_TIME_MS` boundary is covered by `test_candle_boundary_at_max_time`. |

The document changes of spec section 13 (edits 1 to 9) are in `513b94d`. Three reviews compared them with the specification character by character: the T1 spec review, the T1 quality review and the whole-slice review. They found nothing else changed in `docs/`.

## 4. Rules enforced, with negative tests

| Rule | Enforced part | Negative tests |
|---|---|---|
| Domain 6.1, U4, U6 | Exact `int`; instants in `0 … 2^53−1`; durations in `1 … 2^53−1` | `test_invalid_instant_is_refused`, `test_invalid_duration_is_refused` |
| Domain 6.8 | The instrument key is a non-empty exact `str`, with no other rule | `test_invalid_instrument_key_is_refused` |
| Domain 6.5, U5 | Parameter shape: a flat scalar mapping; equality by canonical form | `test_invalid_parameters_are_refused`, `test_parameters_equality_is_canonical` |
| DR-14, domain 6.2 | Three distinct outcomes; no empty `Signals`; no failure without a code | `test_signals_outcome_requires_signals`, `test_failure_requires_code`, `test_outcomes_are_distinct` |
| Domain 6.3, U3 | Signal kind and payload shape | `test_invalid_signal_is_refused` |
| DR-11 (rows) | Exact finite `Decimal`, never `float` | `test_invalid_row_field_is_refused`, `test_decimal_nan_kinds_are_refused` |
| DR-10 | Series strictly ascending, never sorted; snapshot mappings iterate in key order | `test_unordered_or_duplicate_series_is_refused`, `test_snapshot_mappings_iterate_in_key_order` |
| DR-01 (closed part), DR-02, DR-04 (settled part), U1 | Nothing in a snapshot is stamped after `as_of` | `test_row_after_as_of_is_refused`, `test_candle_boundary_at_max_time` |
| SE-3 spec 5 (final) | No SE-3 type can be subclassed | `test_types_cannot_be_subclassed_*` |
| SE-3 spec 5 (errors) | Malformed input raises only `EvaluationTypeError`, over the listed cases | `test_malformed_input_raises_only_evaluation_type_error_*` |

**Convention or review only** (spec section 9):

- **Availability.** N8 checks a necessary condition only. DR-01's publication part, DR-03, DR-04's publication part, and DR-05 to DR-07 and DR-20 belong to the builder slices.
- **Section 6.5, the failure part.** The conversion of a parameter refusal into a per-pair evaluation failure is SE-5b's.
- **One instrument per snapshot** (domain 6.6). The type cannot check it.
- **Private reachability.** Mutable state can still be reached through private attributes, through `gc`, or by calling `__init__` again on a dataclass instance. Only `Parameters` refuses a second `__init__`.
- **No escaping built-in exception.** That no input outside the listed N15 cases lets a built-in exception escape rests on the explicit checks and on review. Mapping keys get no N15 sweep: N11 covers them, and `check_duration` runs before any key is used.
- **DR-15.** The types fill nothing. That callers fill nothing is a matter for later slices.

## 5. Token usage

Subagent tokens as reported by the subagent results in this session (cumulative where an agent was continued):

| Task | Implementer | Spec review | Quality review |
|---|---|---|---|
| T1 | 105 672 | 61 398 | 56 078 |
| T2 | 76 100 | 46 305 | 39 968 |
| T3 | 87 340; 92 360 after the fix round | 47 188; re-review 18 793 | 42 850; re-review 16 004 |
| T4 | 108 632 | 62 116 | 45 499 |

Whole slice: the review used 100 345 tokens, the fix wave 56 652 and its re-review 28 110.

The specification and plan reviews ran in earlier sessions, whose results are not available here. The orchestrator's own usage is not reported.

## 6. Known limitations

- On CPython 3.12, assigning a non-field attribute to a frozen slots dataclass raises `TypeError` instead of `FrozenInstanceError`. The orchestrator checked this. So the immutability tests for a non-field name accept `AttributeError` or `TypeError` and then assert that the attribute is absent. Field assignment and deletion are asserted exactly.
- `UNEXPECTED_VALUES` holds one shared generator instance. Every constructor rejects it by type before iterating, so no case depends on test order today.
- `copy.copy`, `copy.deepcopy` and `pickle` of a `Parameters` fail for the same reason as `FrozenMapping` in SE-2 (the `__setattr__` guard). Nothing requires them.
- `Parameters` reads with an unhashable key, such as `p[[1]]`, raise `TypeError`. That is a read path; spec 5 "Errors" covers construction only.
- CI has not run on GitHub (no push).
- These LOW items stay deferred; the whole-slice review triaged each as safe:
  - two avoidable `# type: ignore[arg-type]` in T2's tests;
  - a `None` parameter that a T2 case never uses;
  - T2's N15 valid cases sit in a separate test;
  - the extra test helpers (`UNEXPECTED_IDS`, `ROW_BUILDERS`, `build_with`, `snapshot_with`);
  - `test_candle_boundary_at_max_time` compares with the object passed in rather than a newly built candle.

## 7. Rulings made

1. Task 1's functions in the shared rules test file carry the suffix `_parameters`, which also covers the time and key validators. The plan's Global Constraints require a group suffix, and the T1 text omitted one. If wrong, this costs a rename.
2. The `Snapshot` check order is accepted: `candles` is validated fully before `open_interest`, where the plan's Step 3 checks both `dict` types first. Spec 5 "Errors" requires only that every malformed input raises `EvaluationTypeError` before any unsafe operation, and that holds. If wrong, this costs a reorder in `snapshot.py`; the error class is unaffected.
3. N15 gets a value position for `Parameters` (`Parameters({"a": v})`) that skips the valid scalars `1` and `"1"`. This extends the plan's pinned skip list for test coverage only, as three reviewers recommended. If wrong, this costs one test to remove.

Also: the work ran on branch `se-3-evaluation-types` in the main checkout, as in SE-1 and SE-2. The lessons from the T2 review (positive twins in the same test, no compensating type ignores, slice-qualified citations) were carried into the T3 and T4 dispatches.

## 8. Open questions for the user

1. **U4/U6 in domain 6.1.** Answered at acceptance: the user had both ranges recorded in domain section 6.1, amended 2026-11-13.
2. **Domain section 4, "Every rule is unimplemented".** After SE-2 and SE-3, parts of DR-01, DR-02, DR-04, DR-10, DR-11 and DR-14 have negative tests. Should that sentence change? And should enforcement evidence be recorded in the domain document, or only in the slice reports?

Question 2 is still open; it does not block the code. The report was accepted by the user on 2026-11-13.
