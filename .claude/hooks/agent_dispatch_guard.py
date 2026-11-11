#!/usr/bin/env python3
"""PreToolUse guard for subagent dispatches (the Agent tool).

Enforces the model policy of CLAUDE.md ("Agentic workflow") and appends one
line per dispatch to a git-ignored local log.

What it enforces:
  * a review agent or the explorer never runs on a model other than its own;
  * a general-purpose dispatch names its model explicitly: sonnet or opus;
  * a dispatch whose description looks like a review does not go to an
    agent that is not a review agent.

What it does not enforce: that a review is dispatched to a review agent when
its description does not look like a review. That part is procedural; the
log makes it auditable.

Exit code 2 blocks the dispatch and shows stderr to the dispatching model.
Any internal error also blocks: the guard fails closed.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

REVIEW_AGENTS = ("spec-reviewer", "quality-reviewer", "slice-reviewer")
FIXED_MODEL = {**{name: "opus" for name in REVIEW_AGENTS}, "explorer": "haiku"}
GENERAL_AGENTS = ("general-purpose", "claude")
GENERAL_MODELS = ("sonnet", "opus")

REVIEW_WORD = re.compile(r"\b(re-?)?review(er|s)?\b", re.IGNORECASE)
FIX_WORD = re.compile(r"\b(fix|fixes|fixing|address|apply|resolve)\b", re.IGNORECASE)
SLICE_ID = re.compile(r"\bSE-\d+[a-z]?\b", re.IGNORECASE)


LEADING_REVIEW = re.compile(
    r"^\s*(SE-\d+[a-z]?)?\s*(T(ask)?\s*\d+)?\s*[:\-]?\s*(re-?)?review", re.IGNORECASE
)


def looks_like_review(description: str) -> bool:
    """A description that leads with "review"/"re-review" is a review, whatever
    follows ("Re-review Task 2 fix round 1"). Otherwise the word counts unless the
    dispatch is about fixing ("fix review findings")."""
    if LEADING_REVIEW.match(description):
        return True
    return bool(REVIEW_WORD.search(description)) and not FIX_WORD.search(description)


def decide(tool_input: dict) -> tuple[str | None, str | None]:
    """Return (effective model or None if unknown, denial reason or None)."""
    agent = tool_input.get("subagent_type") or "general-purpose"
    model = tool_input.get("model")
    description = tool_input.get("description") or ""

    if agent in FIXED_MODEL:
        required = FIXED_MODEL[agent]
        if model not in (None, required):
            return model, (
                f"Agent '{agent}' runs on '{required}' only; this dispatch asked for "
                f"'{model}'. Omit `model` or set it to '{required}'."
            )
        return required, None

    if looks_like_review(description):
        return model, (
            f"This dispatch looks like a review ('{description}') but targets "
            f"'{agent}'. Every AI review runs on Opus through a review agent: "
            f"{', '.join(REVIEW_AGENTS)}. Fill the same prompt and dispatch it to "
            "the matching review agent. If this is not a review, reword the description."
        )

    if agent in GENERAL_AGENTS:
        if model not in GENERAL_MODELS:
            return model, (
                f"A '{agent}' dispatch must name its model explicitly: 'sonnet' "
                f"(routine implementation) or 'opus' (complex implementation); got "
                f"'{model}'. Exploration goes to the 'explorer' agent."
            )
        return model, None

    return model, None


def log(project_dir: str, payload: dict, tool_input: dict, model: str | None, reason: str | None) -> None:
    try:
        description = tool_input.get("description") or ""
        match = SLICE_ID.search(description)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session": payload.get("session_id"),
            "slice": match.group(0).upper() if match else None,
            "agent": tool_input.get("subagent_type") or "general-purpose",
            "model": model,
            "description": description,
            "decision": "deny" if reason else "allow",
        }
        directory = os.path.join(project_dir, ".superpowers")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "dispatch-log.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass  # logging never blocks or fails a dispatch


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") not in ("Agent", "Task"):
            return 0
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            raise TypeError("tool_input is not an object")
        model, reason = decide(tool_input)
    except Exception as error:  # fail closed
        print(f"agent_dispatch_guard: cannot check this dispatch ({type(error).__name__}).", file=sys.stderr)
        return 2

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    log(project_dir, payload, tool_input, model, reason)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
