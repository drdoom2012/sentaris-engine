# SE-2 — Payload values and canonical form: slice report

**Branch:** `se-2-payload-canonical-form` (from `main` at `d71c170`), not merged, not pushed. The branch also carries `2a85607` (slice skill: task sizing and scoped re-review package), which the user decided to merge together with SE-2.  
**Specification:** `docs/superpowers/specs/2026-11-12-se-2-payload-canonical-form-design.md` (revision 3, approved 2026-11-12 with U1; N6 row restored editorially in `1baf100`, approved by the user).  
**Plan:** `docs/superpowers/plans/2026-11-12-se-2-payload-canonical-form.md` (revision 2).  
**Code:** `src/sentaris_engine/domain/payload.py`; tests under `tests/domain/`.

## 1. Tasks

| Task | Implementer | Attempts | Review findings (spec / quality) | Fix rounds | Commits |
|---|---|---|---|---|---|
| T1 Construction, freezing, shared references, cycles | `opus` (iterative walk with in-progress/finished states is the core of U1) | 1 | spec: compliant, 4 LOW; quality: approved, 2 minor + 1 note | 0 (LOWs and the re-initialisation minor carried into T2 by ruling) | `3e6ece6` |
| T2 Canonical encoder, equality, hash, `repr` | `opus` (canonical form is a byte-exact domain contract) | 1 | spec: 1 MEDIUM, 1 LOW; quality: 1 Important, 1 minor (same finding: literal non-ASCII characters in test source) | 1 (quality re-review: both addressed) | `282c14b`, `6b44e48` |
| T3 Strict decoder, exception policy, `CLAUDE.md` | `opus` (decoder strictness and spec 5.6) | 1 | spec: compliant, 1 LOW (plan-level); quality: approved, 2 minor | 0 | `25718af` |
| Whole-slice review | — | — | `slice-reviewer`: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 5 LOW | 1 fix wave + 1 scoped re-review (all 7 items addressed, incl. one deferred minor) | `25bc2e7` |

Before implementation: specification reviewed twice plus one scoped re-review (revision 1 → 2 → 3 after the user's focused review), plan reviewed once plus one scoped re-review.

Every review ran on Opus through the review agents. `.superpowers/dispatch-log.jsonl` records 13 SE-2 dispatches, all `opus`, all allowed by the dispatch guard: 3 specification/plan reviews, 3 implementers, 6 task reviews, 1 whole-slice review. Six further rounds continued an existing agent through a message (spec re-review, plan re-review, T2 fix round and its re-review, final fix wave and its re-review); the dispatch guard does not log those.

## 2. `make check`

Run by the orchestrator on the final head `25bc2e7`:

```text
All checks passed!                                  (ruff check)
22 files already formatted                          (ruff format --check)
Success: no issues found in 22 source files         (mypy strict)
Contracts: 2 kept, 0 broken.                        (import-linter)
============================= 555 passed in 1.36s ==============================
```

Exit 0. Also: `PYTHONSAFEPATH=1 uv run pytest tests/domain -q` → 389 passed; the non-ASCII grep over `tests/domain/*.py` and `payload.py` prints nothing.

**Budget (spec 8.1):** `tests/domain` runs in about 0.3 s; the full suite went from 1.03 s on `main` to about 1.4 s (+0.4 s against the 5 s budget); `make check` wall time about 1.7 s.

## 3. Acceptance criteria

| AC | Evidence |
|---|---|
| AC-1 A.3 vectors, both directions | `test_vectors_encode`, `test_vectors_decode` (the eight A.3 lines, bytes checked against `docs/domain.md`) |
| AC-2 rejected values | `test_rejected_value_is_refused` (N1 values × 5 positions; bad keys × 3 positions), `test_bad_source_is_refused` |
| AC-3 Decimal text, context independence | `test_decimal_text_matches_default_str` (all five classes of spec 5.4, zero coefficients, negative zero, boundary values), `test_decimal_text_ignores_context` (five altered contexts, `capitals = 0` first), `test_decoding_ignores_context` |
| AC-4 freezing by copy | `test_source_mutation_does_not_change_payload`, `test_no_mutable_value_is_reachable`, `test_mapping_cannot_be_mutated`, `test_mapping_cannot_be_reinitialised`, `test_mapping_cannot_be_subclassed`, `test_list_becomes_tuple`, `test_frozen_value_is_reused` |
| AC-5 duplicate keys, source shapes | `test_duplicate_key_from_pairs_is_refused`, `test_bad_source_is_refused`, `test_empty_pairs_give_empty_mapping` |
| AC-6 equality and hash | `test_equality_is_by_canonical_form`, `test_hash_follows_equality`, `test_bool_is_not_integer` |
| AC-7 strict decoder | `test_non_canonical_bytes_are_refused` (every N6 input plus exponent overflow and parser-leniency neighbours, named ids), `test_exponent_out_of_range_is_refused_in_any_context`, positive companion `test_canonical_neighbours_are_accepted` |
| AC-8 round trip | `test_round_trip_generated` (seed 3, 500 payloads), `test_tag_like_keys_round_trip`, `test_extreme_decimal_round_trips` |
| AC-9 no implicit depth bound | `test_no_implicit_depth_bound` (three shapes, depth `max(10 × recursion limit, 10 000)`; construct, encode, `==`, `hash`, `repr`, decode, round trip) |
| AC-10 process independence | `test_canonical_form_is_identical_across_processes` (`PYTHONHASHSEED` 0 and 1, compared with the in-process result) |
| AC-11 string escaping, key order | `test_string_escaping`, `test_string_escaping_literal_expectations`, `test_key_order_is_by_code_point`, `test_iteration_is_in_code_point_order` |
| AC-12 scalar predicate | `test_scalar_predicate` |
| AC-13 gate, budget, purity | `make check` above; the SE-1 real-tree purity check covers `payload.py`; no list in `tests/architecture/` changed |
| AC-14 shared references and cycles | `test_shared_container_is_accepted`, `test_shared_container_is_accepted_bytes`, `test_shared_container_is_frozen_once` (part a), `test_cyclic_container_is_refused` (six cycle cases and the 30-level chain in one subprocess, 20 s timeout) |
| AC-15 exception policy | `test_module_catches_no_process_failure` (handler and binding check, with violating snippets), `test_handler_checker_accepts_the_allowed_forms`, `test_memory_error_propagates`, `test_decode_leaves_context_flags` |

## 4. Rules enforced, with negative tests

| Rule | Enforced part | Negative tests |
|---|---|---|
| Domain 6.3 / A.1 accepted values | Exact-type acceptance; integer range; finite `Decimal`; no surrogate code point in strings or keys; keys exactly `str`; source shapes; cycles rejected | `test_rejected_value_is_refused`, `test_bad_source_is_refused`, `test_cyclic_container_is_refused`, `test_scalar_predicate` |
| A.1 duplicate keys | Any repeated key from pairs rejected; no occurrence wins | `test_duplicate_key_from_pairs_is_refused` |
| A.1 freezing by copy | Nothing mutable reachable through the public interface | `test_source_mutation_does_not_change_payload`, `test_no_mutable_value_is_reachable`, `test_mapping_cannot_be_mutated`, `test_mapping_cannot_be_reinitialised`, `test_mapping_cannot_be_subclassed` |
| 6.3 / A.1 equality | Equality and hash by canonical form | `test_equality_is_by_canonical_form`, `test_hash_follows_equality` |
| A.2 canonical form | Exact bytes, escaping, key order, `Decimal` text | `test_vectors_encode`, `test_string_escaping`, `test_key_order_is_by_code_point`, `test_decimal_text_matches_default_str` |
| A.2 strict decoder | Only canonical bytes accepted; only `PayloadError` for bad data | `test_non_canonical_bytes_are_refused`, `test_exponent_out_of_range_is_refused_in_any_context` |
| DR-10 (payloads) | Construction order changes neither bytes nor iteration | `test_construction_order_does_not_change_form_or_iteration`, `test_iteration_is_in_code_point_order` |
| DR-11 (payloads) | `float` refused at every position; decoder never yields `float` | `test_rejected_value_is_refused`, `test_non_canonical_bytes_are_refused`, `test_decoder_never_yields_float` |
| DR-13 (payloads) | Same bytes under any `decimal` context and in any process | `test_decimal_text_ignores_context`, `test_decoding_ignores_context`, `test_canonical_form_is_identical_across_processes` |
| U1 (spec 5.3) | No implicit depth bound | `test_no_implicit_depth_bound` |
| Spec 5.6 | No broad or process-level handler; `MemoryError` propagates | `test_module_catches_no_process_failure`, `test_memory_error_propagates` |

**Convention or review only** (spec section 9):

- "Nothing mutable is reachable" holds through the public interface only; private attributes and `gc` can reach the internal `dict`.
- A `tuple` taken from a payload compares with Python semantics (`(True,) == (1,)`), and Python's own comparison or hashing of a deeply nested `tuple` may hit the recursion limit.
- No bound: a payload is limited only by memory; a heavily shared payload is cheap to construct, but its canonical form, equality, hash and `repr` may be exponentially large (OD-25 stays open).
- Platform independence rests on review: the encoder uses no platform- or context-dependent operation.
- N16 checks handlers and bindings statically, and `MemoryError` at one call site.
- DR-10, DR-11 and DR-13 are enforced for payloads only.

## 5. Token usage

Reported by the subagent results (subagent tokens, cumulative per agent where an agent was continued):

- Specification review 56 948; focused re-review of revision 3 42 009, 55 613 after its scoped re-review.
- Plan review 82 309, 102 452 after its scoped re-review.
- T1: implementer 95 358; spec review 58 211; quality review 41 925.
- T2: implementer 114 288, 117 678 after the fix round; spec review 61 782; quality review 42 528, 45 786 after the re-review.
- T3: implementer 103 376, 129 254 after the final fix wave; spec review 56 401; quality review 42 839.
- Whole-slice review 121 611, 137 452 after its scoped re-review.

The orchestrator's own usage is not reported.

## 6. Known limitations

- `copy.copy`, `copy.deepcopy` and `pickle` of a `FrozenMapping` fail, because `__setattr__` blocks restoring the slots. The spec does not require them, and pickling is persistence or transport (OD-11, OD-20). **For SE-3:** `dataclasses.asdict` deep-copies non-dataclass fields and would fail on a payload; if SE-3 needs copying, `__copy__` and `__deepcopy__` returning `self` are behavior-neutral for an immutable value. That is SE-3's decision.
- `_has_surrogate` scans every string character at Python speed. It is correct and linear; an `isascii()` fast path is possible.
- The parser's own duplicate-key and trailing-data checks are covered only through the final re-encoding check, which spec 5.5 makes the guarantee.
- The file-writing tool of this environment turns written backslash-u escapes into literal characters. That corrupted five escapes in the approved spec (restored in `1baf100`) and literals in two test files (fixed in `6b44e48` and during T3). The non-ASCII grep is the check; later slices should keep it.
- CI has not run on GitHub (no push).

## 7. Rulings made

1. The work ran on branch `se-2-payload-canonical-form` in the main checkout, as in SE-1.
2. T1's four LOW spec findings and the re-initialisation minor were carried into T2's dispatch instead of a separate T1 fix round. T2 edits the same files, and its two reviews verified the fixes. If this was wrong, the cost is a LOW that slips to the final review, which saw the ledger.
3. `PayloadValue` is a PEP 695 `type` statement instead of the plan's `TypeAlias` sketch, because ruff UP040 rejects the latter. The static meaning is the same. If this was wrong, nothing changes at runtime unless a later task inspects the alias object.
4. The plan's N16 handler rule (bare names only) is kept, although the spec also allows a dotted attribute. The spec leaves the fixed set to the plan, and the narrower rule is stricter. If this was wrong, a future `except decimal.InvalidOperation` is flagged and must be written as the imported name.
5. The T2 spec LOW "report misstates how é is written in `VECTORS`" was checked and left unchanged: the report was accurate, and the reviewer had seen the escape rendered as the character.
6. Deferred, not fixed: `_has_surrogate` speed; the parser's defence-in-depth checks being tested only through re-encoding; copy and pickle (section 6). The whole-slice review triaged all three as safe to defer.
