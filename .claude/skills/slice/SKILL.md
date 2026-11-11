---
name: slice
description: Run one roadmap slice (SE-n) of Sentaris Engine through its full lifecycle - prerequisite check, slice specification, plan, implementation, Opus reviews, make check, acceptance. Use whenever a slice from docs/roadmap.md is to be designed, planned, implemented or resumed.
argument-hint: SE-n [stage to resume]
---

# Slice lifecycle

You are the orchestrator of one slice. Superpowers supplies the method; this skill says which Superpowers skill runs at each stage and what this project changes in it. The model policy and the stop rule are in `CLAUDE.md` ("Agentic workflow") and bind every stage.

Work on one slice only. Stop at every point marked **User**. Do not start the next slice.

## What this project changes in Superpowers

1. **Reviews go to review agents.** Wherever a Superpowers skill dispatches a `general-purpose` subagent to judge work (builder check, task review, re-review, final review), fill its prompt template unchanged and dispatch it to the review agent named below instead. Never set `model` on a review agent.
2. **Two reviews per task.** Superpowers' task review returns two verdicts from one reviewer. Here the same filled `task-reviewer-prompt.md` is dispatched twice, to `spec-reviewer` and to `quality-reviewer`, in one message. A re-review goes only to the reviewer whose findings were fixed.
3. **Open decisions stop the run.** Superpowers tells the controller to rule on ambiguities and continue. Here a ruling is allowed only on matters of implementation. Anything that touches an `OD-xx`, a `DR-xx`, domain section 6, or something `docs/domain.md` does not state is not ruled on: stop and ask the user.
4. **Implementers run on `sonnet` or `opus`**, never lower. Use `opus` when the task needs design judgment, touches a domain contract in a subtle way (canonical form, availability, determinism), or after two failed fix rounds on `sonnet`.
5. **Dispatch descriptions start with the slice and task**, for example `SE-2 T3: implement canonical encoder`, so the dispatch log can be read per slice.

## Stage 1 — Prerequisites

Read the slice's row in `docs/roadmap.md` and the domain sections it cites. Check that the slices in "Depends on" are finished (merged, `make check` passing) and that every decision in "Gate" has been taken (it is in domain section 6, not section 7). Check that roadmap and domain document agree on what the slice contains.

If a gate decision is open or the documents disagree: **User** — report it and stop.

## Stage 2 — Slice specification

Use `superpowers:brainstorming`. The roadmap row already fixes the scope; ask the user only what the documents leave to the slice (for SE-1, the tooling). The specification is saved to `docs/superpowers/specs/YYYY-MM-DD-se-N-<topic>-design.md` and contains: goal, scope, dependencies, domain references (IDs, not restated rules), interfaces and contracts, expected behavior, acceptance criteria, negative tests (one named test per rule the slice claims to enforce), explicit exclusions, open questions.

Review: dispatch `slice-reviewer` with the specification path (this replaces the builder check; include the builder-check questions in the prompt). Fix findings; a finding that needs a domain decision goes to the user.

**User** — approve the specification.

## Stage 3 — Plan

Use `superpowers:writing-plans`; the plan is saved to `docs/superpowers/plans/YYYY-MM-DD-se-N-<topic>.md`. Every task states: exact scope, expected files, relevant contracts, acceptance criteria, tests, verification commands, completion condition, and the implementer model (`sonnet` or `opus`) with a reason when `opus`.

Review: dispatch `slice-reviewer` with the plan path and the specification path. Fix findings.

**User** — approve the plan. No implementation before that.

## Stage 4 — Exploration

Only when a task changes existing code and the files are not already named in the plan: dispatch `explorer` with one bounded question. Put its answer in the task brief. Skip this stage otherwise.

## Stages 5 to 9 — Implementation, reviews, verification, corrections

Use `superpowers:subagent-driven-development` in an isolated branch or worktree (`superpowers:using-git-worktrees`), with the changes listed above. One implementer at a time; no two agents write to one working tree. Per task:

1. Implementer (`general-purpose`, explicit `model`), TDD, task-level tests.
2. `spec-reviewer` and `quality-reviewer` on the task's review package, in parallel.
3. Run the task's verification commands yourself. An agent's statement that checks pass is not evidence.
4. Findings go back to the implementer; then a scoped re-review by the reviewer concerned. Repeat until no CRITICAL or HIGH finding is open. MEDIUM and LOW are fixed or recorded in the ledger with a reason.

During implementation run targeted checks (the task's tests, the linter on changed files). Run the whole gate at task completion.

## Stage 10 — Completion

1. Run `make check` yourself and read its output.
2. Dispatch `slice-reviewer` for the complete-slice review with the whole-branch review package and the ledger's deferred findings (Superpowers' final review, on this agent).
3. One fix dispatch for its findings, one scoped re-review, `make check` again.
4. Before the Superpowers workspace is deleted, write `docs/superpowers/reports/se-N.md` from the ledger and `.superpowers/dispatch-log.jsonl`:
   - per task: implementer model, implementation attempts, review findings by severity, fix/review rounds;
   - `make check` result with the command's own summary line;
   - every acceptance criterion with the test that shows it;
   - each rule now enforced, with its named negative test, and each property that remains a convention or review-only;
   - token usage only where a subagent result reported it; no estimates;
   - known limitations and rulings made.
5. **User** — present the report for acceptance. Do not merge or push without being told to (`superpowers:finishing-a-development-branch` offers the options).
