# SE-6 — Quasar REST client: slice report

**Branch:** `se-6-quasar-rest-client` (from `main` at `d5e229c`; carries the separately approved OD-27 documents `be32733` and the specification and plan `5ed9581`). Not merged, not pushed.  
**Specification:** `docs/superpowers/specs/2026-11-13-se-6-quasar-rest-client-design.md` (revision 5, approved 2026-11-13).  
**Plan:** `docs/superpowers/plans/2026-11-13-se-6-quasar-rest-client.md` (revision 2, approved 2026-11-13).  
**Code:** `src/sentaris_engine/infrastructure/quasar/` (`errors.py`, `pages.py`, `transport.py`, `body.py`, `decoding.py`, `client.py`, `__init__.py`).  
**Tests:** `tests/infrastructure/`:
- `test_body.py`, `test_decoding.py`, `test_client.py`, `test_transport.py`;
- the helpers `quasar_bodies.py`, `quasar_fakes.py`, `local_server.py` and `conftest.py`;
- the JSON bodies under `fixtures/`.

## 1. Tasks

| Task | Implementer | Attempts | Review findings (spec / quality) | Fix rounds | Commits |
|---|---|---|---|---|---|
| T1 Errors, page types, `HttpResponse`, strict JSON body | `opus` (plan: DR-11 in the JSON layer and the exact exception list of spec 5.4, U5) | 1 | spec: compliant, 2 LOW; quality: approved, 1 LOW (the same as spec LOW-1) | 0 (LOWs deferred) | `592d83c` |
| T2 Single-page decoders, contract fixtures | `opus` (plan: canonical decimals, DR-15, exclusive versus inclusive window bounds) | 1 | spec: compliant, 4 LOW; quality: approved, 3 LOW | 1 (5 LOWs fixed; both re-reviews: all addressed) | `73983cb`, `0012f4a` |
| T3 `QuasarClient`: arguments, URLs, paging, status mapping | `sonnet` | 1 | spec: compliant, 4 LOW; quality: approved, 2 LOW (one the same as spec LOW-4) | 1 (2 LOWs fixed; spec re-review: all addressed) | `838053f`, `ee9e3a5` |
| T4 Default urllib transport, `CLAUDE.md` | `sonnet` | 1 | spec: compliant, 5 LOW; quality: approved, 2 LOW | 1 (3 LOWs handled; both re-reviews: all addressed) | `ba86ef4`, `290ac57` |
| Whole slice | — | — | `slice-reviewer`: approved, 0 CRITICAL, 0 HIGH, 0 MEDIUM, 6 LOW; all deferred findings triaged "accept"; no question for the user | 0 (ruling 6) | — |

No task review found a CRITICAL, HIGH or MEDIUM issue. Each fix round was sent to the task's own implementer, which continued its session.

`.superpowers/dispatch-log.jsonl` records 18 SE-6 dispatches for implementation, and the dispatch guard allowed all of them:
- 4 implementer dispatches: T1 and T2 on `opus`, T3 and T4 on `sonnet`;
- 8 task reviews and 5 scoped re-reviews by `spec-reviewer` and `quality-reviewer`, all on `opus`;
- 1 whole-slice review by `slice-reviewer` on `opus`.

The guard does not log the three fix rounds, because they continued existing agents. The earlier sessions also logged four `slice-reviewer` dispatches, for the specification and plan reviews and their re-reviews.

## 2. `make check`

The orchestrator ran it on the final head `290ac57`:

```text
All checks passed!                                    (ruff)
Success: no issues found in 68 source files           (mypy strict)
Contracts: 2 kept, 0 broken.                          (import-linter)
============================= 2270 passed in 2.23s =============================
```

The orchestrator also ran `make check` after every task and every fix round, and every run was clean: 1574 passed after T1, 2027 after T2 and 2040 after its fix round, 2263 after T3 and its fix round, and 2270 after T4 and its fix round. `git diff main -- pyproject.toml uv.lock tests/architecture` is empty (AC-10).

The orchestrator also checked two other things itself:
- the three contract example fixtures equal the code blocks of contract 5.2, 6.5.4 and 6.7.4, compared by a script;
- `__init__.py` re-exports `urllib_transport`.

**Mutation checks reported by the implementers** (not re-run by the orchestrator):
- **T2:** 26 deliberate decoder bugs, each caught by the tests. Among them: `re.match` instead of `fullmatch`, `\d` instead of `[0-9]`, `-0` accepted, the window, `next` and `limit` bounds off by one, `isinstance` checks, and missing-value defaults.
- **T3:** 5 mutations, each caught:
  - the caller's `start` used as the cursor;
  - `safe=''`;
  - no `.port` read;
  - no R8 check;
  - no `check_instant(end)`.
- **T4:** `except Exception` around `opener.open` makes the new `UnicodeError` case fail.

The local-server tests ran in the sandbox; binding `127.0.0.1` was allowed. `test_transport.py` passes with `-W error`, so no `ResourceWarning` and no thread leak, as the implementer reported.

## 3. Acceptance criteria

| AC | Evidence |
|---|---|
| AC-1 Parameters, encoding, path, `GET` only | `test_request_urls`, `test_identifiers_are_encoded_and_echo_compared_decoded`, `test_base_url_forms`, `test_requests_go_only_to_base_url_paths`, `test_default_transport_reads_a_response` (origin form, `Accept: application/json`) |
| AC-2 Paging, separate pages | `test_single_page_read`, `test_paged_read`, `test_later_page_must_echo_cursor` |
| AC-3 Contract examples verbatim | `test_contract_examples_decode` (field by field, `format(d, "f")` equal to the body text). The OI and funding examples are also whole reads in `test_single_page_read` |
| AC-4 Every 5.4 check refuses | Every negative test of `test_body.py` and `test_decoding.py`; every test name of spec section 8 is present |
| AC-5 Exact decimals, no `float` | `test_decimal_text_is_exact`, `test_json_number_with_fraction_is_refused`, `test_json_number_with_fraction_becomes_marker`, `test_no_float_is_built_for_ignored_fields`, `test_unknown_fields_are_ignored` (fractions in ignored fields) |
| AC-6 Error classification, nothing returned on failure | `test_error_classes`, `test_error_body_shapes`, `test_error_status_is_response_error`, `test_error_status_on_later_page_returns_nothing`, `test_protocol_error_on_later_page_returns_nothing`, `test_not_ready_reason`, `test_not_ready_is_an_error_not_empty_data`, `test_injected_transport_errors_propagate`, `test_injected_transport_programming_error_propagates`, `test_transport_failure_is_transport_error` |
| AC-7 No proxy, no redirect, non-`200` as a status | `test_environment_proxy_is_ignored`, `test_redirect_is_not_followed`, `test_non_200_is_a_status` |
| AC-8 Malformed arguments refused before any request | `test_malformed_client_arguments_are_refused`, `test_malformed_read_arguments_are_refused`, `test_calls_are_not_made_before_arguments_are_checked` (each asserts `calls == []`) |
| AC-9 Unknown fields ignored at every level | `test_unknown_fields_are_ignored` |
| AC-10 `make check`, no dependency, no architecture list changed | Section 2 |

Behaviors 1 to 9 of spec section 6 are covered by the same tests, together with `test_empty_page`, `test_funding_series_null`, `test_nullable_fields` and `test_repeated_read_is_equal`. The positive boundaries are covered by `test_row_at_window_edge_is_accepted`, `test_next_inside_window_is_accepted` and `test_full_last_page_with_null_next_is_accepted`. Review Focus 1 to 6 of the plan each have the test the plan names.

## 4. Rules enforced, with negative tests

| Rule | Enforced part | Negative tests |
|---|---|---|
| DR-11 at the client boundary | No `float` is built while decoding, in read and ignored fields alike; every decimal field read must be in exact canonical text | `test_no_float_is_built_for_ignored_fields`, `test_json_number_with_fraction_is_refused`, `test_non_canonical_decimal_is_refused`, `test_nan_and_infinity_are_refused` |
| DR-15 at the client boundary | No default for a missing or `null` field | `test_missing_row_field_is_refused`, `test_null_in_non_nullable_field_is_refused`, `test_missing_next_is_refused`, `test_missing_series_is_refused`, `test_nullable_fields` (key deleted) |
| Spec 5.5, contract section 2 | An error answer is never data, on any page | `test_error_status_on_later_page_returns_nothing`, `test_not_ready_is_an_error_not_empty_data` |
| Spec 5.6 | The default transport reaches only the configured base URL | `test_redirect_is_not_followed`, `test_environment_proxy_is_ignored`, `test_requests_go_only_to_base_url_paths` |
| Spec 5.4 (U5), 5.6 (U4) | Exactly the listed exceptions are translated; programming errors propagate | `test_parse_failures_are_protocol_errors`, `test_hook_programming_error_propagates`, `test_injected_transport_programming_error_propagates`, `test_default_transport_programming_error_propagates` |
| Spec 5.4 body, echoes, series, rows, `next` | Every check of 5.4 | The negative tests listed in spec section 8, all present |

**Supported, not enforced** (spec section 9):
- **DR-14:** the client gives later slices an error, never an empty answer.
- **DR-24:** `test_wrong_time_semantics_is_refused` refuses a response whose stated time semantics differ from the SE-3 rows.
- **DR-18, DR-19:** stay enforced by the unchanged SE-1 architecture tests.
- **DR-17:** not claimed.
- **DR-07:** does not apply here (spec section 8).

**Convention or review only:**
- The decoders parse only through `decode_ok_body` → `parse_json`. That `test_no_float_is_built_for_ignored_fields` walks `parse_json` rather than the decoder rests on this (ruling 1).
- No retry, sleep, clock or environment read. This is shown by review and by grep, not by a negative test.

## 5. Token usage

Each figure below is the `subagent_tokens` value of a subagent's completion notification, as reported. The orchestrator's own usage was not reported and is not estimated. For an agent that continued through a fix round, the second figure is the value reported after that round.

| Dispatch | Model | Reported tokens |
|---|---|---:|
| T1 implementer | Opus 5.5 | 93 379 |
| T1 spec review / quality review | Opus 5.5 | 59 951 / 44 151 |
| T2 implementer (after fix round) | Opus 5.5 | 161 808 (169 093) |
| T2 spec review / quality review | Opus 5.5 | 104 855 / 69 048 |
| T2 spec re-review / quality re-review | Opus 5.5 | 22 587 / 19 997 |
| T3 implementer (after fix round) | Sonnet 5.5 | 97 639 (101 842) |
| T3 spec review / quality review | Opus 5.5 | 59 603 / 36 648 |
| T3 spec re-review | Opus 5.5 | 17 408 |
| T4 implementer (after fix round) | Sonnet 5.5 | 80 285 (88 949) |
| T4 spec review / quality review | Opus 5.5 | 39 094 / 34 904 |
| T4 spec re-review / quality re-review | Opus 5.5 | 17 110 / 19 473 |
| Whole-slice review | Opus 5.5 | 150 182 |
| LOW-1 test after acceptance: implementer / quality re-review | Sonnet 5.5 / Opus 5.5 | 40 008 / 14 274 |

## 6. Known limitations

- **The oversized-integer refusal depends on the process.** Outside the tests it follows Python's integer-string digit limit (`PYTHONINTMAXSTRDIGITS`, `-X int_max_str_digits`), as spec 5.4 states. The tests pin 4300 and restore the previous value.
- **`base_url` (R7, whole-slice LOW-2).**
  - R7 admits characters that RFC 3986 does not allow: `\`, `"`, `<`, `>`, `^`, `` ` ``, `{`, `|`, `}` and a malformed `%XX`. It also admits an empty port (`http://h:`) and a host such as `http://a..b`.
  - All of spec 5.1's prohibitions are enforced, and urllib cannot be misrouted.
  - An unusable host fails at request time with an exception that is not a `QuasarClientError`, for example `UnicodeError` (spec 5.6: such errors propagate). SE-13 must treat a bad base URL as a configuration error.
- **Cause types are those of CPython 3.12.** `test_transport_failure_is_transport_error` and the `UnicodeError` case assert exact types. `.python-version` pins 3.12, while `requires-python` is `>=3.12`, so a Python upgrade may need these tests revisited.
- **The closed-port case can flake.** `_closed_port_url` binds a port, closes it and connects later, so another process could take the port in that gap. A bound socket that does not listen would hold the port, but on macOS it times out instead of refusing, which changes the cause type. The helper's comment records this (ruling 5).
- **Times are checked against `check_instant`**, not Quasar's narrower valid range (spec section 9).
- **The client checks single responses.** It cannot detect that a later page reflects a changed database; this is why pages are returned separately (U2, OD-24).
- **Deferred LOW items**, all judged "accept" by the whole-slice review:
  - Docstrings in `body.py`, `errors.py` and `transport.py` paraphrase rules next to their IDs.
  - `test_nullable_fields` no longer asserts the page type.
  - The R8 cases live in `test_transport_result_must_be_an_http_response`.
  - The request lines in `test_requests_go_only_to_base_url_paths` are checked by prefix and suffix only.
  - The extra test helpers: `conftest.py`, the `release` fixture, `respond`, and `decode_as` in `quasar_bodies.py`.
  - `Decimal(82709)` is used instead of `Decimal("82709")` (ruff FURB157); the text is checked with `format`.
  - The instant predicate is written three times (R4 and R5 sanction this).
  - Two tests import a submodule as a package attribute, and `JSON_UTF8` is defined twice.
- **Stale statements in the documents (whole-slice LOW-6).**
  - The plan's constraint "`docs/domain.md` and `docs/roadmap.md` do not change" is true of the SE-6 commits, but not of the branch as a whole, which also carries `be32733` (OD-27).
  - `docs/roadmap.md:3` still says "Nothing is built".
- CI has not run on GitHub (no push).
- **The commit trailers of T3 and T4** say `Co-Authored-By: Claude Opus 5.5`, as the controller's briefs prescribed, although Sonnet 5.5 wrote those commits.

## 7. Rulings made

1. **The parse-level float walk covers spec 8.** `test_no_float_is_built_for_ignored_fields` walks `parse_json`, not the decoder, because the decoders have no other parse path. The whole-slice review checked this. If wrong: a decoder could build a `float` outside `parse_json` without a test failing.
2. **T1's `git add` of the spec and plan was a no-op** (pre-flight scan): both were already committed in `5ed9581`. If wrong: nothing.
3. **T2's LOW findings were fixed in a fix round** instead of deferred: one fixture contradicted contract 6.7.1, and there were the `type: ignore` lines, `assert_never`, the Infinity cases and the parametrisation. If wrong: one extra pair of dispatches.
4. **R7 was not tightened** (T3 findings, whole-slice LOW-2). R7 is part of the user-approved plan, and spec 5.1's prohibitions are all enforced. If wrong: an odd `base_url` is accepted and fails at request time (section 6).
5. **The closed-port race in T4 was not fixed.** The alternative changes the asserted cause type on macOS. If wrong: an occasional flaky run of one test case.
6. **There was no whole-slice fix wave.** The reviewer rated all six LOW findings optional or needing no change, and they are recorded here. After accepting the report, the user asked for LOW-1 to be added: `420e438` runs `test_hook_programming_error_propagates` over `error_fields` too. A mutation to `except Exception` fails exactly the four new cases. `quality-reviewer` approved it, and `make check` gave 2274 passed.

The plan's own rulings R1 to R9 were approved by the user before implementation. The pre-flight scan of the plan found no conflicts between tasks.

## 8. Open questions for the user

1. **Domain section 4, "Every rule is unimplemented"** (carried over from earlier reports). SE-2 to SE-6 now have negative tests for parts of several rules. Should that sentence change?
2. **`docs/roadmap.md:3`, "Nothing is built":** should it be updated in a separate change?
3. ~~Whole-slice LOW-1~~: answered. The test was added (ruling 6).
