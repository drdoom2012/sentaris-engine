#!/bin/sh
# Claude Code PreToolUse hook (matcher: Bash). Local convenience only; CI is the authoritative gate.
# Reads the hook JSON from stdin. If it mentions "git commit", runs the check command in the git work
# tree named by the JSON's "cwd" (the tree being committed, e.g. a worktree) and blocks the tool call
# (exit 2, stderr is shown to Claude) when it fails. Otherwise exits 0 immediately.
# If "cwd" is missing or not inside a work tree, the script's own checkout is used instead.
# SENTARIS_CHECK_CMD overrides the check command (used by tests).
#
# Known limitations (spec 5.5), accepted because CI is authoritative:
# - The check runs on the files on disk, not on the staged content.
# - The match is a substring over the whole JSON (including the description): `git -C path commit`
#   or a commit inside a script is missed; a call that only mentions `git commit` triggers a check.
# - A hook that exceeds its timeout does not block: the commit proceeds.
# - "cwd" is the shell directory before the command runs: `cd <other tree> && git commit ...` is checked in
#   the "cwd" tree, not in <other tree>.
# - If the directory change into the tree fails, the commit proceeds unchecked (a line on stderr says so).

input=$(cat)

case "$input" in
*"git commit"*) ;;
*) exit 0 ;;
esac

cwd=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd") or "")' 2>/dev/null) || cwd=""

root=""
if [ -n "$cwd" ]; then
    root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || root=""
fi
if [ -z "$root" ]; then
    root=$(cd "$(dirname "$0")/../.." && pwd) || exit 0
fi
cd "$root" || {
    echo "pre-commit check skipped: cannot enter $root" >&2
    exit 0
}

output=$(sh -c "${SENTARIS_CHECK_CMD:-make check}" 2>&1)
status=$?
if [ "$status" -ne 0 ]; then
    echo "Pre-commit check failed (exit $status). Last 40 lines of output:" >&2
    printf '%s\n' "$output" | tail -n 40 >&2
    exit 2
fi
exit 0
