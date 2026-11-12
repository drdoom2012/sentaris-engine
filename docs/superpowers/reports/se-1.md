# SE-1 — Project skeleton: slice report

**Branch:** `se-1-project-skeleton` (from `main` at `70e430b`), not merged, not pushed.  
**Specification:** `docs/superpowers/specs/2026-11-11-se-1-project-skeleton-design.md` (revision 3, approved 2026-11-11 with A1–A6, H1, H2; aligned to the implemented checks after the whole-slice review).  
**Plan:** `docs/superpowers/plans/2026-11-11-se-1-project-skeleton.md`.

## 1. Tasks

| Task | Implementer | Attempts | Review findings (C / I / minor) | Fix rounds | Commits |
|---|---|---|---|---|---|
| T1 Scaffold, tooling, contracts, CI | `sonnet` | 1 | spec 0/0/3, quality 0/0/2 | 0 | `79e8d79` |
| T2 AST checker and guards | `opus` (import resolution is the core of the DR-08 claim) | 1 | spec 0/0/4, quality 0/0/3 | 0 | `c89d7b7` |
| T3 import-linter negative tests | `sonnet` | 1 | spec 0/0/4, quality 0/0/3 | 0 | `0bbad7e` |
| T4 Dependency check | `sonnet` | 1 | spec 0/1/4, quality 0/1/4 | 1 (both addressed) | `c1e5359`, `07a227a` |
| T5 Commit hook, settings check, CLAUDE.md | `sonnet` | 1 | spec 0/1/3, quality 0/1/3 | 1 (all addressed) | `e6f47ec`, `9ae665a` |
| Whole-slice review | — | — | slice-reviewer: 0 C, 2 MEDIUM, 6 LOW | 1 fix wave + 1 re-review | `a0bce5d` |

Every review ran on Opus through the review agents (`slice-reviewer`, `spec-reviewer`, `quality-reviewer`); `.superpowers/dispatch-log.jsonl` records 25 dispatches for SE-1, all allowed by the dispatch guard, implementers on `sonnet` or `opus` set explicitly.

Before implementation: specification reviewed three times (revision 1, revision 2, revision 3 after the user's revision request), plan reviewed once.

## 2. `make check`

Run by the orchestrator on the final head:

```text
All checks passed!                       (ruff check)
15 files already formatted               (ruff format --check)
Success: no issues found in 15 source files   (mypy strict)
Contracts: 2 kept, 0 broken.             (import-linter)
============================= 166 passed in 1.02s ==============================
```

Exit 0. Timed run with a warm cache: about 1.3 s (AC-9 budget: 60 s).

## 3. Acceptance criteria

| AC | Evidence |
|---|---|
| AC-1 fresh clone passes | Fresh clone of the branch in a scratch directory, `uv sync && make check` → exit 0, 162 passed (head `9ae665a`); the fix wave added 4 tests, 166 on the final head |
| AC-2 each step can fail the gate | In the scratch clone, one change at a time: unused import → exit 2 at `lint`; misformatted file → exit 2 at `lint` (format check); type error → exit 2 at `typecheck`; `domain` importing `infrastructure` → exit 2 at `imports`; failing test → exit 2 at `test` |
| AC-3 every check runs on the real tree | `test_real_tree_is_clean`, `test_real_package_has_no_unknown_child`, `test_unmodified_copy_keeps_both_contracts`, `test_real_pyproject_is_clean`, `test_real_lock_is_clean`, `test_real_settings_have_both_hooks`; `make imports` |
| AC-4 negative test per claimed invariant | section 4 |
| AC-5 CI | `.github/workflows/check.yml`, identical to Quasar's; **not run on GitHub** (no push yet) |
| AC-6 commit hook | `tests/test_pre_commit_hook.py` (9 tests); the hook ran on the commits `e6f47ec`, `9ae665a`, `a0bce5d` and passed |
| AC-7 dependencies | `test_real_pyproject_is_clean`, `test_real_lock_is_clean`, `test_allowlists_are_pinned` |
| AC-8 CLAUDE.md | "Commands" section: commands, single test, targeted checks, task and slice completion, pinned lists |
| AC-9 runtime | about 1.3 s |

## 4. Rules enforced, with negative tests

| Rule | Enforced part | Negative tests |
|---|---|---|
| DR-08 | Pure code (`domain`, `application`, `strategies`, root) imports only the pinned stdlib allowlist and allowed internal names, in any syntactic position; calls none of the forbidden builtins; relative imports resolved | `tests/architecture/test_purity.py::test_violation_is_reported` (parametrised: stdlib, third-party, bypass forms, forbidden calls, relative imports, root funnel), `test_pinned_lists` |
| DR-08 | Layering between subpackages, transitive | `tests/architecture/test_import_contracts.py::test_layering_violation_breaks_exactly_its_contract` (3 domain edges, 6 sibling edges, 1 transitive through the root), `test_removing_independence_contract_from_copied_config_makes_probe_pass` |
| DR-08 | No unclassified package child | `test_unknown_child_package`, `test_unknown_child_module`, `test_unknown_compiled_child` |
| DR-18 | No import of `quasar_market_data` under `src` or `tests`; no `quasar-market-data` in `uv.lock` | `test_violation_is_reported` (DR-18 rows), `tests/architecture/test_dependencies.py::test_lock_denylisted_package_is_one_violation`, `test_lock_denylist_is_compared_after_normalisation` |
| DR-19 | Runtime dependencies within an empty allowlist; denylisted exchange libraries absent from `uv.lock`; banned exchange imports absent | `test_pyproject_violation_is_reported_once` (runtime rows), `test_lock_denylisted_package_is_one_violation`, `test_lock_denylist_covers_the_spec_names`, `test_violation_is_reported` (banned names) |
| Project policy | Dev and build dependencies within allowlists; no other declaration place (`[tool.uv]`, `[tool.hatch]` beyond wheel packages, `dynamic` dependencies, direct references, other groups, optional dependencies) | `test_pyproject_violation_is_reported_once` (policy rows), `test_allowlists_are_pinned` |
| A5 | Both hooks configured in `.claude/settings.json` | `tests/test_claude_settings.py::test_missing_dispatch_guard_is_one_violation`, `test_missing_commit_hook_is_one_violation` |

**Convention or review only** (spec section 9): DR-08 access that does not go through an import or a named builtin call (objects passed in, `__builtins__`, `sys.modules` through a passed object); `hash()`/`id()`; global `decimal` context; DR-18 "database never read"; DR-19 "no exchange credentials" and "no trading functionality" beyond dependencies; exchange libraries not on the denylist arriving transitively; purity of test strategies (SE-4); the commit hook's approximations (section 6).

## 5. Token usage

Reported by the subagent results (subagent tokens): specification reviews 72 523, 73 500; plan review 73 765. T1: implementer 43 176, reviews 40 528 + 45 154. T2: implementer 62 889, reviews 39 543 + 30 147. T3: implementer 53 386, reviews 30 792 + 21 482. T4: implementer 51 850 (60 338 after the fix round), reviews 32 308 + 29 676, re-reviews 24 927 + 19 615. T5: implementer 54 747 (59 078 after the fix round), reviews 35 341 + 29 119, re-reviews 17 120 + 17 945. Whole-slice review 87 626, fix wave 75 890, re-review 39 608. The orchestrator's own usage is not reported.

## 6. Known limitations

- The commit hook matches `git commit` as a substring of the hook JSON, checks the working tree rather than the index, does not block on timeout, takes the tree from the hook JSON's `cwd` (so `cd <other tree> && git commit` is checked in the `cwd` tree), and lets the commit through, with a message on stderr, if it cannot enter the tree. CI is the authoritative gate.
- CI has not run on GitHub.
- H2 is tested with temporary repositories; this session ran on a branch in the main checkout, not in a separate worktree, so the worktree path was not observed live.
- Deferred minor findings not fixed: `project.dynamic` not type-checked; malformed `pyproject.toml`/`uv.lock` shapes raise instead of reporting a violation (the test still fails, so the effect is fail-closed); the not-an-array and invalid-JSON branches are untested; `hatchling` build requirement is unpinned (as in Quasar); duplicate quasar rows in the AST negative cases; the hook's fallback `cd` also exits silently.

## 7. Rulings made

1. Work on branch `se-1-project-skeleton` in the main checkout rather than a separate worktree (CLAUDE.md allows a branch).
2. `BUILD_ALLOWLIST = {"hatchling"}`: `[build-system].requires` is a declaration place under spec 6.3 "fail closed" (reviewed as consistent).
3. Known-child guard counts files with importable suffixes (`importlib.machinery.all_suffixes()`), ignoring non-code files such as `.DS_Store`.
4. Hook tests start `git init` and the hook script as subprocesses (spec 8 "separate program").
5. T4: the lock-denylist tests are parametrised from a literal of the 13 spec names, with a superset assertion (fixes a plan-mandated gap).
6. T4: the dependency check is fail-closed by shape: `[tool.uv]` absent, `[tool.hatch]` only `build.targets.wheel.packages`, no `dynamic` dependencies, no direct references. Stricter than spec revision 3; the spec was aligned. **For the user to confirm** (question 1 below).
7. T5: CLAUDE.md gets the slice-completion step of spec 5.6, which the plan had left out (spec wins).
8. T5: the fallback hook tests assert that their outside directory is not inside a git work tree.
9. Whole-slice review: the `cwd` versus `cd … && git commit` limitation of H2 is documented, the hook is not changed. **For the user to confirm** (question 2 below).

## 8. Final re-review

`slice-reviewer` on the fix wave `9ae665a..a0bce5d`: all nine findings ADDRESSED, no new Critical or Important breakage; section 12 approvals unchanged, no OD settled, no DR touched. Residuals, parked (no second fix wave):

- Minor: CLAUDE.md cites "spec A4" for all pinned lists; A4 covers only the stdlib allowlist and forbidden calls (dependency lists: 6.3; banned names and known children: 5.2, 6.2, 6.3).
- Minor: the hook's new stderr line on a failed directory change has no test case.
- Spec 5.2 still says "`infrastructure` is the only place where I/O is allowed", which the corrected docstring no longer claims because the future composition root (A3) will also do I/O. It sits in an approved section, so the wording is left to the user (question 3).
