"""`.claude/settings.json` must keep both PreToolUse hooks (spec 5.5, A5)."""

import json
from pathlib import Path

SETTINGS = Path(__file__).resolve().parents[1] / ".claude" / "settings.json"

REQUIRED_HOOKS = (
    ("Agent|Task", "agent_dispatch_guard.py"),
    ("Bash", "scripts/hooks/pre_commit_check.sh"),
)


def settings_violations(text: str) -> list[str]:
    """One violation per required PreToolUse hook that is missing from the settings text."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return [f"settings are not valid JSON: {error.msg}"]
    entries = data.get("hooks", {}).get("PreToolUse", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        entries = []
    violations: list[str] = []
    for matcher, command_part in REQUIRED_HOOKS:
        found = any(
            isinstance(entry, dict)
            and entry.get("matcher") == matcher
            and any(
                isinstance(hook, dict) and command_part in str(hook.get("command", ""))
                for hook in entry.get("hooks", [])
            )
            for entry in entries
        )
        if not found:
            violations.append(f"PreToolUse hook missing: matcher {matcher!r} running {command_part}")
    return violations


def settings_text(*, guard: bool = True, commit_hook: bool = True) -> str:
    entries = []
    if guard:
        entries.append(
            {
                "matcher": "Agent|Task",
                "hooks": [{"type": "command", "command": 'python3 ".claude/hooks/agent_dispatch_guard.py"'}],
            }
        )
    if commit_hook:
        entries.append(
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "scripts/hooks/pre_commit_check.sh", "timeout": 300}],
            }
        )
    return json.dumps({"hooks": {"PreToolUse": entries}})


def test_text_with_both_hooks_has_no_violations() -> None:
    assert settings_violations(settings_text()) == []


def test_missing_dispatch_guard_is_one_violation() -> None:
    assert len(settings_violations(settings_text(guard=False))) == 1


def test_missing_commit_hook_is_one_violation() -> None:
    assert len(settings_violations(settings_text(commit_hook=False))) == 1


def test_real_settings_have_both_hooks() -> None:
    assert settings_violations(SETTINGS.read_text(encoding="utf-8")) == []
