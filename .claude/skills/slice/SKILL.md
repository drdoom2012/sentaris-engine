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
6. **Context is reset at the two approval points.** The state of a slice lives in files (specification, plan), not in the conversation, so the orchestrator's context is cut where the next stage needs only those files. Every later turn re-reads the context, so a long planning discussion is paid for again at each step of the implementation. The orchestrator cannot clear its own context: after the approval it says so and gives the user the exact command to run (`/clear`, then `/slice SE-n <next stage>`). Before it does, everything the next stage needs is in the saved document, including rulings made and questions left open; whatever is only in the conversation is lost.

## Stage 1 — Prerequisites

Read the slice's row in `docs/roadmap.md` and the domain sections it cites. Check that the slices in "Depends on" are finished (merged, `make check` passing) and that every decision in "Gate" has been taken (it is in domain section 6, not section 7). Check that roadmap and domain document agree on what the slice contains.

If a gate decision is open or the documents disagree: **User** — report it and stop.

## Stage 2 — Slice specification

Use `superpowers:brainstorming`. The roadmap row already fixes the scope; ask the user only what the documents leave to the slice (for SE-1, the tooling). The specification is saved to `docs/superpowers/specs/YYYY-MM-DD-se-N-<topic>-design.md` and contains: goal, scope, dependencies, domain references (IDs, not restated rules), interfaces and contracts, expected behavior, acceptance criteria, negative tests (one named test per rule the slice claims to enforce), explicit exclusions, open questions.

Review: dispatch `slice-reviewer` with the specification path (this replaces the builder check; include the builder-check questions in the prompt). Fix findings; a finding that needs a domain decision goes to the user.

**User** — approve the specification. Then recommend a context reset (item 6): `/clear`, then `/slice SE-n plan`.

## Stage 3 — Plan

Use `superpowers:writing-plans`; the plan is saved to `docs/superpowers/plans/YYYY-MM-DD-se-N-<topic>.md`. Every task states: exact scope, expected files, relevant contracts, acceptance criteria, tests, verification commands, completion condition, and the implementer model (`sonnet` or `opus`) with a reason when `opus`.

Task size: every task costs at least three dispatches (implementer and two reviews), so small tasks are not split off on their own. Merge tasks that touch the same area or share tests. Split a task only when its diff would be too large to review well, or when part of it needs `opus` and the rest does not.

Review: dispatch `slice-reviewer` with the plan path and the specification path. Fix findings.

**User** — approve the plan. No implementation before that. Then recommend a context reset (item 6): `/clear`, then `/slice SE-n implementation`. The resumed session reads the approved specification and plan from disk and continues at Stage 4 or 5.

## Stage 4 — Exploration

Only when a task changes existing code and the files are not already named in the plan: dispatch `explorer` with one bounded question. Put its answer in the task brief. Skip this stage otherwise.

## Stages 5 to 9 — Implementation, reviews, verification, corrections

Use `superpowers:subagent-driven-development` in an isolated branch or worktree (`superpowers:using-git-worktrees`), with the changes listed above. One implementer at a time; no two agents write to one working tree. Per task:

1. Implementer (`general-purpose`, explicit `model`), TDD, task-level tests.
2. `spec-reviewer` and `quality-reviewer` on the task's review package, in parallel.
3. Run the task's verification commands yourself. An agent's statement that checks pass is not evidence.
4. Findings go back to the implementer; then a scoped re-review by the reviewer concerned (see "Re-review package" below). Repeat until no CRITICAL or HIGH finding is open. MEDIUM and LOW are fixed or recorded in the ledger with a reason.

Re-review package: the diff of the fix round only, the findings it answers, and the domain sections those findings cite. Not the whole task again. The reviewer checks that each finding is resolved and that the fix introduced no new problem in the lines it touched. The same applies to the re-review in Stage 10.

During implementation run targeted checks (the task's tests, the linter on changed files). Run the whole gate at task completion.

## Stage 10 — Completion

1. Run `make check` yourself and read its output.
2. Dispatch `slice-reviewer` for the complete-slice review with the whole-branch review package and the ledger's deferred findings (Superpowers' final review, on this agent).
3. One fix dispatch for its findings, one scoped re-review (re-review package as in Stages 5 to 9), `make check` again.
4. Before the Superpowers workspace is deleted, write `docs/superpowers/reports/se-N.md` from the ledger and `.superpowers/dispatch-log.jsonl`:
   - per task: implementer model, implementation attempts, review findings by severity, fix/review rounds;
   - `make check` result with the command's own summary line;
   - every acceptance criterion with the test that shows it;
   - each rule now enforced, with its named negative test, and each property that remains a convention or review-only;
   - token usage only where a subagent result reported it; no estimates;
   - known limitations and rulings made.
5. **User** — present the report for acceptance. Do not merge or push without being told to (`superpowers:finishing-a-development-branch` offers the options).
