# SE-1 — Project skeleton: design

**Slice:** SE-1 (`docs/roadmap.md`, Phase A)  
**Status:** Revision 3, approved by the user together with A1–A6, H1 and H2 (2026-11-11). Revision 1 was approved in principle; revisions 2 and 3 add the application layer and tighten checks, hook and tests after two Opus reviews.  
**Domain references:** DR-08, DR-18, DR-19; domain sections 1, 2 and 6.1; domain section 8 (enforcement only with evidence)

Decisions marked **[approval]** are architectural choices this document proposed; the user approved them (section 12). Everything marked "my call" is an implementation choice the builder may keep.

## 1. Goal

An empty but fully gated Python project: package, test runner, linter, formatter check, type checker, architecture checks and `make check`, with CI and a local commit hook. Every later slice uses `make check` as its completion gate (CLAUDE.md). The architecture checks give DR-08, DR-18 and DR-19 their first automated enforcement, each with named negative tests. No production logic, no strategy, no Quasar integration.

## 2. Why this shape

The sibling project `../quasar-market-data` already runs this stack, and the user wants the same tooling, CI and commit hook here (SE-1 conversation, 2026-11-11). Where this document says "as in Quasar", the Quasar file is the reference to copy from and adapt. Quasar's code is never imported (DR-18); copying its tooling configuration is not importing it.

## 3. Scope

1. Project and package: `pyproject.toml`, `uv.lock`, `.python-version`, `src/` layout with the package `sentaris_engine` and four empty subpackages (section 5.2).
2. Tooling: pytest, ruff (lint and format check), mypy strict, import-linter.
3. Architecture checks for DR-08, DR-18, DR-19 (section 6) with named negative tests (section 8).
4. `Makefile` with `lint`, `typecheck`, `imports`, `test`, `check`.
5. CI: GitHub Actions workflow running `make check`.
6. Local commit hook: Claude Code PreToolUse hook (section 5.5), with tests.
7. `.gitignore` entries for tool caches and the virtual environment.
8. `CLAUDE.md`: section "Commands" replaced with the real commands, including how to run a single test and the targeted checks of section 5.6; "Current state" updated to say SE-1 exists.

## 4. Dependencies

None (roadmap). No gate.

## 5. Interfaces and contracts

### 5.1 Tooling (decided by the user: "as in Quasar")

| Item | Decision |
|---|---|
| Package and environment manager | `uv`, committed `uv.lock`; build backend hatchling; `src/` layout |
| Python | 3.12 in `.python-version`; `requires-python = ">=3.12"` |
| Test runner | pytest; `testpaths = ["tests"]`; `addopts` includes `--strict-markers` |
| Linter / formatter | ruff, `line-length = 120`; `ruff check` and `ruff format --check` over `src` and `tests` |
| Type checker | mypy `strict = true` over `src` and `tests` |
| Import contracts | import-linter (`lint-imports`), contracts in `pyproject.toml` |
| Runtime dependencies | none |
| Dev dependencies | `dev` dependency group: pytest, ruff, mypy, import-linter. Nothing else: TOML is read with the standard library's `tomllib`. `[build-system].requires` is limited to `hatchling` (project policy) |

`.claude/hooks/agent_dispatch_guard.py` stays outside the ruff and mypy scope (my call: workflow tooling, not engine code; changing it is out of scope).

### 5.2 Package layout and dependency direction **[approval A1–A3]**

```text
src/sentaris_engine/
    __init__.py                 docstring only; imports nothing internal
    py.typed
    domain/__init__.py          pure
    application/__init__.py     pure
    strategies/__init__.py      pure
    infrastructure/__init__.py  I/O adapters
tests/
    __init__.py                 tests are a package, as in Quasar, so test helpers import as `tests.…` under pytest and mypy strict
```

Each subpackage holds only a module docstring in SE-1. Names are code, not domain (domain section 8).

**Where later code goes is not decided here.** Indicatively: payloads and evaluation types in `domain`; execution over pairs in `application`; real strategies in `strategies`; the Quasar client in `infrastructure`. Each slice decides placement in its own specification, within the layering below. (The roadmap's SE-7a row says "pure domain code"; that is satisfied by `domain` or `application`, both pure.)

Dependency direction (arrows mean "may import"):

```text
application ──┐
strategies  ──┼──> domain
infrastructure┘
```

- `domain` imports no other subpackage.
- `application`, `strategies` and `infrastructure` may import `domain` and are **independent of each other**: none imports another.
- The root `sentaris_engine/__init__.py` imports no internal module, and no module imports the root package (`import sentaris_engine`, or `from sentaris_engine import x` where `x` is not one of the allowed subpackages). This closes the root as a funnel between layers.
- **Pure** code is `domain`, `application`, `strategies` and the root `__init__.py`. Pure code is under the checks of section 6.1. `infrastructure` is the only subpackage in SE-1 where I/O is allowed. The composition root (A3) will be the second non-pure package; the slice that creates it classifies it in the known-child guard.
- import-linter expresses this as two contracts: a `forbidden` contract (source `sentaris_engine.domain`; forbidden `sentaris_engine.application`, `sentaris_engine.strategies`, `sentaris_engine.infrastructure`) and an `independence` contract over `application`, `strategies`, `infrastructure`.

What this means for later slices, stated so it is visible now:

- Execution (SE-5) receives strategies as values from the composition root (domain section 6.4), so `application` never needs to import `strategies`.
- When a use case needs data from I/O (snapshot building, SE-7b), `application` defines what it needs, using `domain` types or a protocol of its own, and the composition root passes in an `infrastructure` object. Neither imports the other.
- The composition root (SE-13, SE-16) is the only code that will import all four. It is **not** created in SE-1. The slice that creates it adds it to the known-child guard (section 5.2) and to the layering, as a reviewed change.

**Known-child guard.** A test lists every direct child of `src/sentaris_engine`, module or package, and fails on a name it does not know. Known in SE-1: `domain`, `application`, `strategies`, `infrastructure`; ignored: `__init__.py`, the `__pycache__` directory and every file whose suffix is not one of `importlib.machinery.all_suffixes()` (so `py.typed` and stray files such as `.DS_Store` are ignored, while a `.py`, `.pyc` or extension-module child is not). A slice that adds a child must classify it as pure or not and place it in the layering, so new code (for example a top-level `clock.py`) cannot escape the checks silently.

### 5.3 Make targets

As in Quasar: `test` = `uv run pytest`; `lint` = ruff check and format check over `src tests`; `typecheck` = `uv run mypy`; `imports` = `uv run lint-imports`; `check: lint typecheck imports test`.

### 5.4 CI

`.github/workflows/check.yml` as in Quasar: triggers on `pull_request` and on `push` to `main`; `permissions: contents: read`; `timeout-minutes: 10`; `UV_LOCKED: "1"`; `actions/checkout` and `astral-sh/setup-uv` pinned by commit SHA (the SHAs and versions Quasar pins), `persist-credentials: false`; Python from `.python-version`; one step, `make check`. **CI is the authoritative gate.** Nothing else in this document weakens or replaces it.

### 5.5 Commit hook **[approval H1, H2]**

Approved requirement (revision 1): a Claude Code PreToolUse hook that runs `make check` before `git commit`, as in Quasar. Its cost and reliability, reviewed:

- **Cost.** The hook runs only when the PreToolUse JSON contains `git commit`; every other Bash call returns at once. It also fires for subagents' Bash calls. Per task of the slice workflow there are about two or more full runs: the implementer's commit (hook), the orchestrator's own gate run (slice skill, stage 5–9 step 3), and the hook again on every fix commit after review. With AC-9's budget of 60 seconds that is about two to four minutes of checks per task.
- **Reliability.**
  - *Wrong tree (as in Quasar).* Quasar's script runs the check in the checkout the hook script lives in (`${CLAUDE_PROJECT_DIR}`, the directory the session started in). The slice workflow commits in a worktree, so the check would run on the main checkout, not on what is being committed: it passes or fails regardless of the commit. Before SE-1 is merged the main checkout has no hook at all.
  - *Working tree, not index.* The check runs on the files on disk, not on the staged content; unstaged changes affect the result.
  - *Substring match.* The match is over the whole stdin JSON, including the tool call's `description`, so it is approximate both ways: `git -C path commit` or a commit inside a script is missed; a command or description that only mentions `git commit` triggers a check.
  - *Timeout.* A hook that exceeds its timeout (300 seconds) does not block: the commit proceeds.
  - *Directory of the check (H2).* The check runs in the tree of the hook JSON's `cwd`, the shell directory before the command runs. A `cd <other tree>` before the commit in the same command is therefore checked in the `cwd` tree, not in `<other tree>`. Known limitation, no behavior change.
  - *Failed directory change.* If `cd` into the resolved tree fails, the script exits 0 and the commit proceeds unchecked; it prints one line to stderr (`pre-commit check skipped: cannot enter <root>`) so this is visible. Known limitation.
  
  These are acceptable only because CI is the authoritative gate and the hook is a local convenience. The wrong-tree problem makes the Quasar behavior useless in a worktree, so this revision proposes one change for approval (H2).

**Proposed change H2: check the tree being committed.** The script reads `cwd` from the hook JSON, resolves it with `git -C <cwd> rev-parse --show-toplevel`, and runs the check there. If `cwd` is missing or not inside a git work tree, it falls back to the script's own checkout, as in Quasar. The other approximations stay and are documented.

Contract, as in Quasar (`scripts/hooks/pre_commit_check.sh`, `tests/test_pre_commit_hook.py`), adapted:

- The script reads the PreToolUse JSON from stdin; without `git commit` in it, it exits 0 at once; otherwise it runs the check in the tree of H2 (or, if H2 is not approved, the script's own checkout) and, on failure, exits 2 with the last 40 lines of output on stderr. `SENTARIS_CHECK_CMD` overrides the command, so tests never run the real `make check`.
- Hook test cases (Quasar's, plus H2): a non-commit command exits 0 without running the check; a commit with a passing check exits 0; a commit with a failing check exits 2 and shows the output tail on stderr; with H2, the check runs in the `cwd`'s work-tree root (a temporary git repository in `tmp_path`), and falls back when `cwd` is outside a work tree.
- Committed with the executable bit set.
- `.claude/settings.json`: the hook is **appended** as a second entry of the existing `PreToolUse` array, matcher `Bash`, command `"${CLAUDE_PROJECT_DIR}"/scripts/hooks/pre_commit_check.sh`, timeout 300. The existing `Agent|Task` entry for `agent_dispatch_guard.py`, `model`, `enabledPlugins` and `permissions` stay byte-for-byte unchanged in meaning; the two hooks have different matchers and do not interact.
- **[approval A5]** A test reads `.claude/settings.json` and asserts that both entries are present (the dispatch guard and the commit hook), so a later edit that overwrites one fails `make check`. This ties the engine gate to the agent configuration: a deliberate later workflow change must update the test too.
- The settings entry is added only once `make check` passes on the branch, so it does not block the slice's own earlier commits; the plan orders this.

Alternatives considered for H1 and not recommended: (a) a reduced hook (lint and type check only), which saves about half the time per commit but lets a commit with failing tests through locally; (b) skipping the check when only `docs/` is staged, which saves seconds on documentation commits but adds another approximation. Both are on offer if the user prefers them.

### 5.6 Development workflow

- **During implementation:** targeted checks only: the task's tests (`uv run pytest path::test`), `uv run ruff check <files>`, `uv run mypy <files>`.
- **At task completion and before each commit:** `make check` (the commit hook enforces it locally).
- **At slice completion:** `make check` run by the orchestrator, and CI on the pushed branch when the user says to push.

These go into `CLAUDE.md` "Commands" (section 3, item 8).

## 6. Architecture checks

Two mechanisms with separate responsibilities. Both run in `make check`: import-linter through `make imports`, the AST checker as pytest tests.

| Mechanism | Responsible for | Not responsible for |
|---|---|---|
| **AST checker** (a test helper under `tests/`, not engine code) | Pure code: allowlist of standard-library imports, ban of third-party imports, forbidden builtin calls, resolution of relative imports. All of `src` and `tests`: ban of Quasar and exchange-library imports. | Transitive imports between internal subpackages; anything that does not appear as an import statement or a direct builtin call. |
| **import-linter** | Layering between the internal subpackages (section 5.2), transitively. | External packages. Pure code can import no external package at all (AST checker), so import-linter needs no external contract. This also removes revision 1's open question about absent external packages. |
| **Dependency check** (pytest over `pyproject.toml` and `uv.lock`) | Direct dependencies by allowlist; locked packages by denylist (section 6.3). | Code that is not a declared dependency. |

### 6.1 Purity of pure code (DR-08)

Pure code is defined in section 5.2.

- **Checker input.** The checker takes a module's qualified name, whether the module is a package (an `__init__.py`), and its source. Source that does not parse is a violation, not a crash.
- **Name resolution.** Every import is resolved to absolute names first. A relative import is resolved against the module's package: the module's own name if it is a package, its parent otherwise; a relative import that goes above `sentaris_engine` is a violation. `from sentaris_engine import x` (absolute or relative) is checked as `sentaris_engine.x`; `import sentaris_engine` as the root package. Aliases (`import time as t`), several names in one statement (`import a, b`) and dotted forms (`import os.path`, `from os import path`) are checked name by name by their resolved top-level module.
- **Allowed internal imports.** A module of `domain` may import `sentaris_engine.domain` and below. A module of `application` or `strategies` may import its own subpackage and `sentaris_engine.domain`. The root `__init__.py` may import no internal module. The root package itself, `infrastructure` and any other subpackage are rejected.
- **Allowed standard library (top-level names):** `__future__`, `abc`, `collections`, `dataclasses`, `decimal`, `enum`, `functools`, `itertools`, `math`, `operator`, `re`, `types`, `typing`. Everything else is rejected, including every third-party package and, among others: `time`, `datetime`, `zoneinfo`, `calendar` (clock; `datetime` also by domain section 6.1), `random`, `secrets`, `uuid` (randomness and generated ids), `os`, `sys`, `io`, `pathlib`, `socket`, `ssl`, `http`, `urllib`, `subprocess`, `sqlite3`, `logging`, `asyncio`, `threading`, `multiprocessing` (I/O, environment, concurrency), `importlib`, `builtins` (dynamic import and builtin lookup).
- **Where imports are checked [approval A6].** Every import statement anywhere in the module: top level, inside functions and class bodies, inside `try` or `if`, and inside `if TYPE_CHECKING:`. The last is stricter than necessary (such imports do not run), but it keeps the checker simple and binds every later slice: a pure module cannot name an infrastructure type even for annotations.
- **Forbidden builtin calls:** `open`, `input`, `print`, `breakpoint`, `__import__`, `eval`, `exec`, `compile`, `globals`, `vars`, called by name.
- **Pinned lists [approval A4].** The standard library is controlled by an allowlist, not a denylist, and a test asserts that the allowlist and the forbidden-call list are exactly those above. A later slice whose pure code needs another standard-library module widens the allowlist by changing this SE-1 test, which shows up in review. Widening is never done to make a test pass (DR-17 in spirit).

### 6.2 No Quasar code (DR-18)

The AST checker rejects any import whose resolved top-level name is `quasar_market_data`, in every module under `src` and `tests`. The dependency check rejects the distribution `quasar-market-data` in `uv.lock` (section 6.3), which covers a transitive arrival through a third-party package.

"Its database never read" is not checked in SE-1. A ban on database drivers would pre-empt the engine's own persistence decision (OD-20). Pure code is barred from `sqlite3` and from file I/O by section 6.1.

### 6.3 No trading or exchange dependency (DR-19; domain sections 1 and 2)

DR-19 excludes trading functionality and credentials; domain sections 1 and 2 add that the engine never contacts an exchange and that exchange access bypassing Quasar is excluded. Together they ground the ban on exchange client libraries.

- **Direct dependencies: allowlists (DR-19 for runtime; project policy for dev).** `[project].dependencies` must be a subset of a runtime allowlist (empty in SE-1), and `[dependency-groups].dev` a subset of a dev allowlist (in SE-1: `pytest`, `ruff`, `mypy`, `import-linter`). Both allowlists are constants in one test module. Introducing a dependency is one reviewable change: the `pyproject.toml` entry, the regenerated `uv.lock` and the allowlist line, together.
- **Fail closed on other declaration places.** The check rejects every other place a dependency can be declared or re-sourced: dependency tables other than `[project].dependencies` and `[dependency-groups].dev` (`[project.optional-dependencies]`, any other dependency group); any `[tool.uv]` table (this includes `dev-dependencies`); `[tool.hatch]` beyond `build.targets.wheel.packages`; `[project].dynamic` naming `dependencies` or `optional-dependencies`; requirement strings with a direct reference (`@`); entries that are not plain requirement strings (for example `{include-group = ...}`); and `[build-system].requires` entries outside `hatchling`. A later slice that needs any of these changes the check as a reviewed change.
- **Locked packages: denylist.** No package in `uv.lock` (runtime, dev and transitive) has a name on a denylist kept in the same module: at least `ccxt`, `python-binance`, `binance-connector`, `binance-futures-connector`, `pybit`, `python-okx`, `kucoin-python`, `krakenex`, `coinbase-advanced-py`, `cryptofeed`, `freqtrade`, `hummingbot`, `quasar-market-data`. Names are compared after PEP 503 normalisation.
- **Imports: ban.** The AST checker rejects the top-level names `ccxt`, `binance`, `pybit`, `okx`, `kucoin`, `krakenex`, `coinbase`, `cryptofeed`, `freqtrade`, `hummingbot` anywhere under `src` and `tests`.
- Parsing uses `tomllib`. From `uv.lock` it reads only the `name` fields of `[[package]]`, so a change of lockfile format beyond those fields does not break the check (my call). From `pyproject.toml` it reads the dependency arrays and the places listed above (`project.dynamic`, `tool.uv`, `tool.hatch`, `build-system.requires`). Requirement strings are reduced to their normalised name before comparison.

## 7. Acceptance criteria

| # | Criterion | How it is shown |
|---|---|---|
| AC-1 | `make check` passes on a fresh clone after `uv sync`, running lint, format check, mypy strict, import-linter and pytest | `make check` output |
| AC-2 | `make check` fails when any one of its steps fails | shown once during the slice per step (a lint error, a type error, a broken contract, a failing test) and recorded with the exit codes in the slice report; not a permanent test (my call) |
| AC-3 | Every check of section 6 runs on the real tree inside `make check` and passes | positive controls and `make imports` |
| AC-4 | Every invariant claimed in section 9 as enforced has a named negative test that fails on a violation | section 8 |
| AC-5 | CI runs `make check` with `UV_LOCKED=1` on pull requests and pushes to `main` | workflow file; a run on GitHub only after the user says to push |
| AC-6 | The commit hook blocks a `git commit` when the check fails and does nothing for other commands; `.claude/settings.json` holds both hooks | hook tests; settings test |
| AC-7 | No runtime dependency; dev dependencies only those of section 5.1; no denylisted package in `uv.lock` | dependency check |
| AC-8 | `CLAUDE.md` lists the real commands, how to run one test, and the workflow of section 5.6 | document |
| AC-9 | `make check` completes in under 60 seconds on the developer's machine with a warm `uv` cache (my call for the figure) | timed run, recorded in the slice report |

## 8. Negative tests

**Efficiency and isolation rules:**

- The AST checker is a pure function (qualified name and source in, violations out). Its cases are **in-process, parametrized unit tests** with synthetic sources; no file is written and no subprocess started.
- One test runs the AST checker over the real `src` and `tests` trees (positive control).
- Subprocesses are used only where the thing under test is a separate program: import-linter (its graph must be built from a copy of the package that the test process has not imported) and the hook shell script; the hook tests also start the separate program `git`, as the hook script does. Nothing else starts a subprocess.
- Each import-linter case copies `src/sentaris_engine` and `pyproject.toml` into `tmp_path`, adds one violating module and runs `lint-imports --no-cache` with `cwd` set to the copy and `PYTHONPATH=<copy>/src`, so the graph is built from the copy and not from the editable install of the real tree (as in Quasar's `test_import_contracts_negative.py`). A negative case asserts a non-zero exit, that the expected contract is reported broken and that the probe module appears in the output; the positive control asserts exit 0. The working tree is never modified and nothing is written outside `tmp_path`.
- Dependency-check cases parse synthetic `pyproject.toml` and `uv.lock` texts in-process.
- Hook tests run the shell script with `SENTARIS_CHECK_CMD` set to a trivial command; the real `make check` is never run by a test.
- No test uses the network, the clock or randomness.

**Cases** ("each" = one parametrized case per item). Test names are the builder's; the cases are fixed.

| Invariant | Mechanism | Case that must be rejected |
|---|---|---|
| DR-08 stdlib allowlist | AST | each pure subpackage, and the root module, imports `time`; domain imports each of `datetime`, `random`, `uuid`, `os`, `socket`, `importlib`, `builtins` |
| DR-08 third-party ban | AST | a pure module imports a name outside the allowlist that is not standard library |
| DR-08 bypass forms | AST | `import time as t`; `import re, time`; `import os.path`; `from os import path`; an import inside a function body; inside a class body; inside `try`; inside `if TYPE_CHECKING:` |
| DR-08 forbidden calls | AST | each forbidden builtin of section 6.1 called by name |
| DR-08 relative imports | AST | `from .. import infrastructure` in a domain module and in `domain/__init__.py` (package); `from ..strategies import x` in application; `from sentaris_engine import infrastructure` in domain; a relative import above `sentaris_engine`; unparseable source |
| DR-08 root funnel | AST | `import sentaris_engine` in domain; the root `__init__.py` importing `infrastructure` (relative and absolute) |
| DR-08 layering | import-linter | domain imports each of `application`, `strategies`, `infrastructure`; each directed pair among `application`, `strategies`, `infrastructure` |
| DR-08 layering, transitive | import-linter | domain imports the root package, whose `__init__.py` imports `infrastructure` (no direct forbidden edge from domain) |
| DR-08 guard | unit | an unknown child package of `sentaris_engine`; an unknown top-level module (`clock.py`); a pinned list that differs from section 6.1 |
| DR-18 | AST | a module under `src`, and one under `tests`, imports `quasar_market_data` (absolute and `from quasar_market_data.x import y`) |
| DR-18 | dependency | `uv.lock` containing `quasar-market-data` |
| DR-19 | dependency | a runtime dependency not in the runtime allowlist; a requirement string with a version and extras (`ccxt[async]>=4`) reduced to its name |
| Project policy | dependency | a dev dependency not in the dev allowlist; a dependency in `[project.optional-dependencies]`; in another dependency group; in `[tool.uv].dev-dependencies` or any `[tool.uv]` table; `[tool.hatch]` beyond `build.targets.wheel.packages`; `dependencies` or `optional-dependencies` in `[project].dynamic`; a direct reference (`@`); an `{include-group = ...}` entry; a `[build-system].requires` entry other than `hatchling` |
| DR-19 | dependency | `uv.lock` containing each denylisted package, one of them spelled with different case and separators |
| DR-19 | AST | each banned top-level name, under `src` and under `tests` |
| settings integrity (A5) | unit | a `settings.json` text missing the dispatch-guard entry; one missing the commit-hook entry |
| commit hook | hook test | the cases listed in section 5.5 |

**Positive cases** next to them: `from ..domain import x` in a strategy module and in an application module, `from sentaris_engine.domain import x`, `from . import sibling` inside domain, `from . import x` in `domain/__init__.py`, and the unmodified tree, all pass.

**Proof that the negative cases are real.** As in Quasar, one import-linter test removes the `independence` contract from the copied `pyproject.toml` and shows that a sibling-edge case then exits 0. For the AST checker, the pinned-list test plays this role.

The import-linter subprocess count is therefore 13 (3 domain edges, 6 sibling edges, 1 transitive, 1 positive control, 2 for the weakening proof: one run before and one after weakening). If AC-9 cannot be met, the plan may merge the sibling-edge cases into fewer subprocess runs, but only if each directed edge is still asserted separately (for example by checking which edges lint-imports reports for one copy holding several violations).

## 9. Enforced guarantees and known limitations

Static checks prove properties of the **source text**, not of the running program. This slice does not claim runtime purity.

**Enforced** (an automated check runs in `make check` and a named negative test fails on a violation):

- DR-08: pure code imports nothing but what section 6.1 allows, in the syntactic positions listed there (tested representatively per position, section 8); calls none of the listed builtins by name; the internal subpackages and the root import each other only as section 5.2 allows, including through the root package (import-linter, transitive).
- DR-18: no module under `src` or `tests` imports `quasar_market_data`; `uv.lock` holds no `quasar-market-data`.
- DR-19: runtime dependencies are within their allowlist; `uv.lock` holds no denylisted package; no module under `src` or `tests` imports a banned exchange-library name.
- Project policy: dev dependencies are within their allowlist, build requirements are limited to `hatchling`, and no dependency is declared or re-sourced anywhere else (the cases of section 6.3).
- If A5 is approved: the commit hook and the dispatch guard are both configured in `.claude/settings.json`.

**Known limitations** (convention or review only):

- An allowed module can still reach the outside world or nondeterminism without a forbidden import or call: an I/O object or clock function passed in as an argument, attribute access through `__builtins__`, `object.__subclasses__()`, `getattr` on an allowed module, or attribute access to a module that other code has already imported (for example reaching `sentaris_engine.infrastructure` as an attribute of a package object, or through `sys.modules` obtained from an object passed in). `functools`, `types`, `collections` and `operator` are not I/O, but they are not a sandbox.
- Process-dependent values: `hash()` of strings (`PYTHONHASHSEED`), `id()`, and the iteration order of sets built from them. Not banned, since that would rule out ordinary `__hash__` methods, which the domain document does not do; DR-10 is enforced by later slices' tests.
- Global `decimal` context: `decimal.getcontext()` is mutable per thread state, so a pure module can depend on settings it did not choose. The numeric policy is open (OD-9); SE-1 only notes it.
- Exchange libraries not on the denylist, when they arrive transitively; an exchange reached by plain HTTP from `infrastructure` (the Quasar client of SE-6 is the only intended HTTP use, and it is reviewed there).
- DR-18 "database never read"; DR-19 "no exchange credentials" and "no trading functionality" beyond dependencies.
- The commit hook's approximations (section 5.5): working tree rather than index, substring match, no block on timeout, and, without H2, the wrong tree in a worktree. With H2, `cwd` is the shell directory before the command runs, so a `cd <other tree>` before the commit in the same command is checked in the `cwd` tree, not in `<other tree>`; and if the directory change into the resolved tree fails, the commit proceeds unchecked (the script prints one line to stderr). CI is authoritative.
- Purity of test strategies under `tests` (they do not exist yet; SE-4 decides whether the purity check covers them).

## 10. Exclusions

- No production logic, no domain types, no strategy, no Quasar client, no HTTP library (SE-2 and later).
- No composition root (SE-13, SE-16).
- No README, no packaging metadata beyond what the tools need, no release or Docker setup.
- No change to `docs/domain.md` or `docs/roadmap.md`.
- No change to `.claude/hooks/agent_dispatch_guard.py`, the agents, the slice skill or the Superpowers plugin setting. `.claude/settings.json` changes only by the appended hook entry. Every AI review keeps running on Opus through the review agents.
- No dependency beyond section 5.1.
- No push, no merge without the user's instruction.

## 11. Open questions

None that block planning, once section 12 is answered. No domain question is open for this slice.

## 12. Decisions approved by the user (2026-11-11)

| ID | Proposal | Why it needs approval |
|---|---|---|
| A1 | An `application` subpackage exists from SE-1, and `application` is **pure**: under the same checks as `domain` and `strategies`. Use cases that need data get an infrastructure object passed in from the composition root. | DR-08 names "domain code and strategies". Treating application code as pure extends the check beyond the rule's literal wording. It is stricter and can be relaxed later only by an explicit decision. |
| A2 | `application`, `strategies` and `infrastructure` are mutually independent; each may import only `domain`. In particular `infrastructure` does not import `application`. | Fixes where future "ports" live (in `application` or `domain`, implemented structurally by `infrastructure`). Loosening it later is a reviewed change. |
| A3 | The composition root is not created in SE-1. The slice that needs it (SE-13 or SE-16) creates it as the one non-pure package allowed to import all four. | Places wiring outside all four layers and defers its design. |
| A4 | The standard library available to pure code is a pinned allowlist (section 6.1). Later slices widen it by changing the SE-1 test, visibly in review. | It is process policy for every later slice, not only an SE-1 detail. The alternative, a denylist, is cheaper to live with but misses any module nobody thought to list. |
| A5 | `make check` includes a test that `.claude/settings.json` holds both the dispatch guard and the commit hook. | It ties the engine's gate to agent configuration; a deliberate workflow change then also needs a test change. Without it, an overwritten hook goes unnoticed. |
| A6 | Imports inside `if TYPE_CHECKING:` are checked like any other import. | It binds every later slice: pure code cannot name a non-allowed type even in annotations. The alternative is to skip those blocks, which makes the checker more complex and opens a small hole. |
| H1 | The commit hook keeps running the full `make check` before every `git commit`, as approved in revision 1. Real cost: about two or more full runs per task (section 5.5), bounded by AC-9's 60-second budget. Alternatives (a reduced hook; a docs-only skip) are described in section 5.5 and not recommended. | The user asked that any change to the hook be presented, not made silently. This item is "no change to what the hook runs". |
| H2 | The hook runs the check in the git work tree of the commit's `cwd` instead of the session's starting checkout, falling back to the latter. | Behavior change against "as in Quasar". Without it the hook checks the wrong tree in every slice worktree, so it gives no protection where commits happen. |
