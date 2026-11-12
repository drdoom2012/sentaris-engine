"""Tests for the local PreToolUse commit hook script (spec 5.5, H1, H2).

The real `make check` is never run here (it would recurse). The tests start `git init` and the hook
script as subprocesses, which is the "separate program" exception of spec 8.
"""

import json
import os
import shlex
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "hooks" / "pre_commit_check.sh"
BLOCKING_EXIT_CODE = 2
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")


def payload(command: str, cwd: Path | None = None) -> str:
    """Shape of the PreToolUse JSON that Claude Code pipes to a hook for the Bash tool."""
    data: dict[str, object] = {
        "session_id": "abc123",
        "transcript_path": "/home/user/.claude/projects/x/transcript.jsonl",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "test", "timeout": 120000},
        "tool_use_id": "toolu_01ABC123",
    }
    if cwd is not None:
        data["cwd"] = str(cwd)
    return json.dumps(data)


def clean_env() -> dict[str, str]:
    """The environment for every subprocess here: inherited git location variables are removed."""
    return {key: value for key, value in os.environ.items() if key not in GIT_ENV_VARS}


def run_hook(stdin: str, check_cmd: str, run_cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the hook script; `run_cwd` is the working directory of the hook process itself."""
    env = clean_env()
    env["SENTARIS_CHECK_CMD"] = check_cmd
    return subprocess.run([str(SCRIPT)], input=stdin, capture_output=True, text=True, env=env, cwd=run_cwd, check=False)


def check_pwd_into(marker: Path) -> str:
    return f"pwd > {shlex.quote(str(marker))}"


def outside_dir(tmp_path: Path) -> Path:
    """A directory in `tmp_path` that is not inside any git work tree."""
    path = tmp_path / "outside"
    path.mkdir()
    probe = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, env=clean_env(), check=False
    )
    assert probe.returncode != 0, "precondition: the outside directory must not be in a git work tree"
    return path


def test_non_commit_command_exits_zero_without_running_check(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    result = run_hook(payload("ls -la"), f"touch {shlex.quote(str(marker))}; false")
    assert result.returncode == 0
    assert not marker.exists()


def test_commit_with_passing_check_exits_zero() -> None:
    result = run_hook(payload('git commit -m "feat: x"'), "true")
    assert result.returncode == 0


def test_commit_with_failing_check_blocks_and_reports_stdout() -> None:
    result = run_hook(payload('git commit -m "feat: x"'), "echo boom; false")
    assert result.returncode == BLOCKING_EXIT_CODE
    assert "boom" in result.stderr


def test_commit_with_failing_check_blocks_and_reports_stderr() -> None:
    result = run_hook(payload('git commit -m "feat: x"'), "echo boom >&2; false")
    assert result.returncode == BLOCKING_EXIT_CODE
    assert "boom" in result.stderr


def test_failing_check_output_is_truncated_to_last_40_lines() -> None:
    result = run_hook(payload("git commit -m x"), "seq 1 500; false")
    assert result.returncode == BLOCKING_EXIT_CODE
    assert "500" in result.stderr.splitlines()
    assert "461" in result.stderr.splitlines()
    assert "460" not in result.stderr.splitlines()


def test_check_runs_in_the_work_tree_of_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo with space"
    sub = repo / "sub"
    sub.mkdir(parents=True)
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "--quiet", str(repo)], env=clean_env(), check=True)
    marker = tmp_path / "pwd.txt"
    result = run_hook(payload("git commit -m x", cwd=sub), check_pwd_into(marker), run_cwd=outside_dir(tmp_path))
    assert result.returncode == 0
    assert Path(marker.read_text().strip()).resolve() == repo.resolve()


def test_cwd_outside_a_work_tree_falls_back_to_the_scripts_checkout(tmp_path: Path) -> None:
    outside = outside_dir(tmp_path)
    marker = tmp_path / "pwd.txt"
    result = run_hook(payload("git commit -m x", cwd=outside), check_pwd_into(marker), run_cwd=outside)
    assert result.returncode == 0
    assert Path(marker.read_text().strip()).resolve() == REPO_ROOT


def test_missing_cwd_falls_back_to_the_scripts_checkout(tmp_path: Path) -> None:
    marker = tmp_path / "pwd.txt"
    result = run_hook(payload("git commit -m x"), check_pwd_into(marker), run_cwd=outside_dir(tmp_path))
    assert result.returncode == 0
    assert Path(marker.read_text().strip()).resolve() == REPO_ROOT


def test_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)
