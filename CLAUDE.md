# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

SE-1 (project skeleton and architecture checks), SE-2 and SE-3 exist. SE-1 is the Python package, tooling and `make check`; SE-2 is the payload type and canonical form (`sentaris_engine.domain.payload`); SE-3 is the evaluation types in `sentaris_engine.domain` (time, instrument key, parameters, signal, result, rows, snapshot, context). There is no other engine logic yet. The domain document remains the single source of truth and wins over the roadmap (see below); besides the skeleton the repository holds the workflow documents under `docs/superpowers` and the CI workflow (an earlier implementation was deliberately removed; do not restore it from git history):

- `docs/domain.md` is the specification and the **single source of truth** for engine-wide business rules.
- `docs/roadmap.md` splits the implementation into slices (`SE-n`) with their dependencies and decision gates. If the two disagree, the domain document wins.

Read the relevant sections of both before planning or writing anything.

## Commands

- `uv sync` installs the locked dependencies.
- `make check` is the completion gate for every slice. It runs, in order: `make lint` (`ruff check` and `ruff format --check` over `src` and `tests`), `make typecheck` (`mypy`), `make imports` (`lint-imports`, layering contracts) and `make test` (`pytest`, which also holds the AST purity checks and the dependency check).
- One test: `uv run pytest tests/path/test_file.py::test_name`.
- The pinned lists of the architecture checks (stdlib allowlist, forbidden calls, banned names, known children, dependency allowlists) live in `tests/architecture/`; widening one is a reviewed change of those tests (SE-1 spec A4).
- Targeted checks while implementing: `uv run ruff check <files>`, `uv run mypy <files>`, and the task's own tests. Run `make check` at task completion and before each commit.
- A Claude Code `PreToolUse` hook (`scripts/hooks/pre_commit_check.sh`, wired in `.claude/settings.json`) runs `make check` in the committing work tree before `git commit`. It is a local convenience; CI (`.github/workflows/check.yml`) is the authoritative gate.
- At slice completion the orchestrator runs `make check` itself; CI runs on the pushed branch only after the user says to push.

## Agentic workflow

Slices are built with Superpowers; `/slice SE-n` (`.claude/skills/slice/SKILL.md`) is the lifecycle and says what this project changes in the Superpowers skills. These rules bind every stage and take precedence over any skill:

| Role | Agent | Model |
|---|---|---|
| Orchestrator (the main session) | | `opus` (project setting) |
| Exploration | `explorer` | `haiku` |
| Implementation, routine | `general-purpose` | `sonnet`, set explicitly |
| Implementation, complex | `general-purpose` | `opus`, set explicitly |
| Task review: specification | `spec-reviewer` | `opus` |
| Task review: code quality | `quality-reviewer` | `opus` |
| Slice specification, plan and whole-slice review | `slice-reviewer` | `opus` |

- **Every AI review runs on Opus, through one of the three review agents.** This includes reviews a Superpowers skill dispatches (builder check, task review, re-review, final review): use its prompt template with the review agent, not `general-purpose`. If a review cannot be run on Opus, stop and say so.
- **Stop rule.** Superpowers' "rule on it and continue" applies to implementation matters only. Anything touching an `OD-xx`, a `DR-xx`, domain section 6 or something the domain document does not state stops the work and goes to the user.
- Reviewers and the explorer are read-only and never the agent that implemented the work. An agent's claim that something passes is not evidence: the orchestrator runs the check.
- Work on a branch or worktree, never on `main`. No push or merge without being told to.

`.claude/hooks/agent_dispatch_guard.py` enforces the models of the agents above and logs every dispatch to `.superpowers/dispatch-log.jsonl`. It cannot tell that a review was sent to `general-purpose` under a description that does not look like a review; that part is procedural.

## What the engine is

A Python application for deterministic analysis of cryptocurrency market data. It hosts independent strategies; given market data as it was available at one moment (`as_of`), each strategy returns signals, "no signal", or an evaluation failure.

```text
Quasar Market Data REST API → Snapshot builder → Strategies (pure) → Result (+ next_state)
```

- **Snapshot builder** applies the availability rules once and produces one immutable snapshot per primary instrument. Strategies never fetch data.
- **Strategies** are pure transitions: no I/O, no clock, no randomness, no mode flag. Live scanning and historical replay are the same pipeline with a different `as_of`.
- **Execution** runs an explicit list of (strategy, instrument) pairs for one `as_of`, sequentially, in a defined order, and reports one entry per pair.
- **State** of a stateful strategy is opaque to the engine, which only loads, passes and persists it.
- Market data semantics belong to the Quasar contract in the sibling repository: `../quasar-market-data/docs/contracts/api-v1.md`. Check it before relying on any field's timestamp semantics.

## Rules for working here

These come from `docs/domain.md` (mainly sections 2, 7 and 8) and override convenience.

- **Never settle an open decision by implementation.** Section 7 lists the open decisions (`OD-xx`). Anything not written in the domain document is undecided. A gap, or a review finding that touches an open decision, goes to the user and into section 7; it is not filled with a reasonable default.
- **Respect decision gates.** Phase A (SE-1 to SE-6) can start now. Every later slice waits for the decisions in its Gate column; do not plan or build it before the user has taken them.
- **Nothing from "Open" or "Not on the path" without an explicit request**: persistence, a REST endpoint, notifications, backtest evaluation, cross-instrument context.
- **Excluded by design**: trading, order execution, exchange credentials, any exchange access that bypasses Quasar. Quasar is reached only through its REST API; its code is never imported and its database never read (DR-18, DR-19).
- **Cite, do not restate.** Code comments, plans and other documents refer to rules by ID (`DR-xx`, `OD-xx`). IDs are stable: never reused or renumbered.
- **Established rules (section 4) and decided design (section 6) are not changed without explicit approval.** The domain document describes behavior, not code: module names, signatures and test names stay out of it.
- **A rule is "enforced" only with evidence**: an automated check runs and a named negative test fails on a violation. A slice is finished when `make check` passes and every rule it claims to enforce has such a test.
- **Fail closed.** Missing, stale or inconsistent data is an evaluation failure with a machine-readable code, never "no signal", `None` or a swallowed exception. Data is never filled, interpolated or defaulted, and validation is never weakened to make a test pass (DR-14 to DR-17).
- **Availability is never assumed** (DR-06). Until OD-6 and OD-7 are decided, no evaluation over real Quasar data may produce a signal, and no replay may be described as reproducing a live evaluation (domain section 5, "Consequence for trust").
- **Every new data input gets a test with data stamped after `as_of` that must be ignored** (DR-07).

## Implementation constraints that are easy to get wrong

- Time is integer UTC milliseconds everywhere; no `datetime`, timezone or float time types (section 6.1).
- Prices and volumes are `Decimal` or Quasar's exact text; never round-tripped through `float` (DR-11).
- Results carry no wall-clock timestamps or generated ids, and never depend on the iteration order of unordered data; sort explicitly (DR-09, DR-10).
- Signal payloads and their canonical byte form are specified normatively in Appendix A, with test vectors. Types are matched exactly (a subclass, an `Enum` or a `float` is rejected), equality is by canonical form, not Python equality, and the encoding is defined by the appendix, not by a JSON library.
- The engine defines no signal kind and never reads payloads, parameters or strategy state (DR-23, DR-25).
- The instrument key is an opaque non-empty string that travels beside the evaluation context; a strategy never receives it (section 6.8).
- An exception from a strategy is caught for that pair only and reported with the exception's type name, never its message (section 6.7).
