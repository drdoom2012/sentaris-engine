"""Negative tests for the import-linter layering contracts in pyproject.toml (DR-08).

Each case copies the real package and the real pyproject.toml into tmp_path, injects a violating module into the
copy and runs lint-imports against the copy. The repo working tree is never modified.
"""

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "sentaris_engine"
DOMAIN_CONTRACT = "domain imports no other layer"
INDEPENDENCE_CONTRACT = "application, strategies and infrastructure are independent"
CONTRACT_NAMES = (DOMAIN_CONTRACT, INDEPENDENCE_CONTRACT)
OTHER_LAYERS = ("application", "strategies", "infrastructure")


@dataclass(frozen=True)
class Case:
    probe_subpackage: str  # the subpackage of the copy that receives _probe.py
    probe_source: str
    broken_contract: str
    append_to_root_init: str = ""  # appended to the copy's root __init__.py (transitive case)


def edge_case(source: str, destination: str, broken_contract: str) -> Case:
    return Case(source, f"import {PACKAGE}.{destination}\n", broken_contract)


CASES = {
    **{
        f"domain_importing_{layer}_fails_domain_contract": edge_case("domain", layer, DOMAIN_CONTRACT)
        for layer in OTHER_LAYERS
    },
    **{
        f"{source}_importing_{destination}_fails_independence": edge_case(source, destination, INDEPENDENCE_CONTRACT)
        for source, destination in permutations(OTHER_LAYERS, 2)
    },
    "domain_reaching_infrastructure_through_the_root_package_fails_domain_contract": Case(
        "domain", f"import {PACKAGE}\n", DOMAIN_CONTRACT, append_to_root_init=f"import {PACKAGE}.infrastructure\n"
    ),
}


def find_lint_imports() -> str:
    """Locate lint-imports next to the running interpreter, falling back to PATH."""
    candidate = Path(sys.executable).parent / "lint-imports"
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("lint-imports")
    if found is None:
        pytest.fail("lint-imports executable not found next to sys.executable or on PATH")
    return found


def run_lint_imports(workdir: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(workdir / "src")}
    return subprocess.run(
        [find_lint_imports(), "--no-cache", "--config", str(workdir / "pyproject.toml")],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def make_copy(tmp_path: Path) -> Path:
    """Copy the real package and pyproject.toml; bytecode caches are skipped."""
    shutil.copytree(
        REPO_ROOT / "src" / PACKAGE,
        tmp_path / "src" / PACKAGE,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    return tmp_path


def write_probe(workdir: Path, subpackage: str, source: str) -> None:
    (workdir / "src" / PACKAGE / subpackage / "_probe.py").write_text(source, encoding="utf-8")


def test_unmodified_copy_keeps_both_contracts(tmp_path: Path) -> None:
    """Positive control: the violations below are caused by the probes, not by the copy."""
    result = run_lint_imports(make_copy(tmp_path))
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert f"{len(CONTRACT_NAMES)} kept, 0 broken" in output, output


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_layering_violation_breaks_exactly_its_contract(tmp_path: Path, case: Case) -> None:
    workdir = make_copy(tmp_path)
    write_probe(workdir, case.probe_subpackage, case.probe_source)
    if case.append_to_root_init:
        root_init = workdir / "src" / PACKAGE / "__init__.py"
        root_init.write_text(root_init.read_text(encoding="utf-8") + case.append_to_root_init, encoding="utf-8")

    result = run_lint_imports(workdir)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "1 broken" in output, output
    assert f"{case.broken_contract} BROKEN" in output, output
    for kept in CONTRACT_NAMES:
        if kept != case.broken_contract:
            assert f"{kept} KEPT" in output, output
    assert "_probe" in output, output  # the injected module appears in the reported chain


def test_removing_independence_contract_from_copied_config_makes_probe_pass(tmp_path: Path) -> None:
    """Proves the independence cases are real: the same probe passes once its contract is dropped from the copy."""
    workdir = make_copy(tmp_path)
    write_probe(workdir, "application", f"import {PACKAGE}.strategies\n")
    config = workdir / "pyproject.toml"
    original = config.read_text(encoding="utf-8")
    block = re.compile(
        r'^\[\[tool\.importlinter\.contracts\]\]\nname = "' + re.escape(INDEPENDENCE_CONTRACT) + r'"\n.*?(?=^\[|\Z)',
        re.DOTALL | re.MULTILINE,
    )
    weakened = block.sub("", original)
    assert weakened != original

    before = run_lint_imports(workdir)
    before_output = before.stdout + before.stderr
    assert before.returncode != 0, before_output
    assert f"{INDEPENDENCE_CONTRACT} BROKEN" in before_output, before_output

    config.write_text(weakened, encoding="utf-8")
    result = run_lint_imports(workdir)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "1 kept, 0 broken" in output, output
