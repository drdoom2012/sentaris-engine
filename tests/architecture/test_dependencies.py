"""Negative and positive tests for the dependency check over pyproject.toml and uv.lock (DR-18, DR-19)."""

from pathlib import Path

import pytest

from tests.architecture.dependencies import (
    BUILD_ALLOWLIST,
    DEV_ALLOWLIST,
    LOCK_DENYLIST,
    RUNTIME_ALLOWLIST,
    lock_violations,
    normalise,
    pyproject_violations,
    requirement_name,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DEV = '"pytest", "ruff", "mypy", "import-linter"'


def pyproject_text(
    runtime: str = "",
    dev: str = DEFAULT_DEV,
    build: str = '"hatchling"',
    groups: str = "",
    extra: str = "",
    project: str = "",
) -> str:
    """A minimal valid pyproject text; each part can be overridden.

    `project` adds lines to [project]; `groups` adds lines to [dependency-groups]; `extra` is appended as further tables.
    """
    return (
        "[project]\n"
        'name = "sentaris-engine"\n'
        'version = "0.1.0"\n'
        f"dependencies = [{runtime}]\n"
        f"{project}\n"
        "\n"
        "[dependency-groups]\n"
        f"dev = [{dev}]\n"
        f"{groups}\n"
        "\n"
        "[build-system]\n"
        f"requires = [{build}]\n"
        'build-backend = "hatchling.build"\n'
        f"\n{extra}\n"
    )


def lock_text(*names: str) -> str:
    return "version = 1\n" + "".join(f'\n[[package]]\nname = "{name}"\nversion = "1.0"\n' for name in names)


# Each text must give exactly one violation.
PYPROJECT_NEGATIVE = {
    "runtime_httpx": pyproject_text(runtime='"httpx"'),
    "runtime_ccxt_with_extra": pyproject_text(runtime='"ccxt[async]>=4"'),
    "dev_black": pyproject_text(dev=f'{DEFAULT_DEV}, "black"'),
    "build_setuptools": pyproject_text(build='"hatchling", "setuptools"'),
    "optional_dependencies": pyproject_text(extra='[project.optional-dependencies]\nx = ["a"]'),
    "other_dependency_group": pyproject_text(groups='lint = ["ruff"]'),
    "uv_dev_dependencies": pyproject_text(extra='[tool.uv]\ndev-dependencies = ["ruff"]'),
    "uv_extra_build_dependencies": pyproject_text(extra='[tool.uv]\nextra-build-dependencies = { x = ["y"] }'),
    "uv_sources": pyproject_text(extra='[tool.uv.sources]\npytest = { git = "https://x" }'),
    "dynamic_dependencies": pyproject_text(project='dynamic = ["dependencies"]'),
    "dynamic_optional_dependencies": pyproject_text(project='dynamic = ["optional-dependencies"]'),
    "hatch_metadata_hook": pyproject_text(extra="[tool.hatch.metadata.hooks.custom]"),
    "hatch_build_hook_dependencies": pyproject_text(extra='[tool.hatch.build.hooks.custom]\ndependencies = ["x"]'),
    "direct_reference": pyproject_text(dev='"pytest @ git+https://x"'),
    "non_string_dev_entry": pyproject_text(dev='{include-group = "dev"}'),
}


@pytest.mark.parametrize("case", sorted(PYPROJECT_NEGATIVE))
def test_pyproject_violation_is_reported_once(case: str) -> None:
    violations = pyproject_violations(PYPROJECT_NEGATIVE[case])
    assert len(violations) == 1, violations


def test_violation_names_the_offending_package() -> None:
    (violation,) = pyproject_violations(pyproject_text(runtime='"httpx"'))
    assert "httpx" in violation


def test_pyproject_minimal_valid_text_is_clean() -> None:
    assert pyproject_violations(pyproject_text()) == []


def test_pyproject_dev_names_are_normalised_and_specifiers_ignored() -> None:
    dev = '"PyTest >= 9 ; python_version >= \'3.12\'", "import_linter", "Ruff", "mypy"'
    assert pyproject_violations(pyproject_text(dev=dev)) == []


# Spec 6.3: "at least" these names; the literal is independent of LOCK_DENYLIST so that removing a name fails a test.
SPEC_DENYLIST = (
    "ccxt",
    "python-binance",
    "binance-connector",
    "binance-futures-connector",
    "pybit",
    "python-okx",
    "kucoin-python",
    "krakenex",
    "coinbase-advanced-py",
    "cryptofeed",
    "freqtrade",
    "hummingbot",
    "quasar-market-data",
)


def test_lock_denylist_covers_the_spec_names() -> None:
    assert {normalise(name) for name in SPEC_DENYLIST} <= LOCK_DENYLIST


@pytest.mark.parametrize("name", SPEC_DENYLIST)
def test_lock_denylisted_package_is_one_violation(name: str) -> None:
    violations = lock_violations(lock_text("sentaris-engine", name))
    assert len(violations) == 1, violations
    assert name in violations[0]


@pytest.mark.parametrize("name", ["Python_Binance", "quasar.market.data"])
def test_lock_denylist_is_compared_after_normalisation(name: str) -> None:
    assert len(lock_violations(lock_text(name))) == 1


def test_lock_clean_packages_give_no_violation() -> None:
    assert lock_violations(lock_text("sentaris-engine", "pytest", "grimp")) == []


def test_normalise_follows_pep_503() -> None:
    assert normalise("Python_Binance") == "python-binance"
    assert normalise("quasar.market.data") == "quasar-market-data"
    assert normalise("a-_.b") == "a-b"


def test_requirement_name_reduces_a_requirement_to_its_name() -> None:
    assert requirement_name("ccxt[async]>=4") == "ccxt"
    assert requirement_name("  PyTest >= 9 ; python_version >= '3.12'") == "pytest"
    assert requirement_name("import_linter") == "import-linter"


@pytest.mark.parametrize("bad", ["", "   ", ">=1", "[extra]"])
def test_requirement_name_rejects_a_string_without_a_name(bad: str) -> None:
    with pytest.raises(ValueError):
        requirement_name(bad)


def test_real_pyproject_is_clean() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert pyproject_violations(text) == []


def test_real_lock_is_clean() -> None:
    text = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert lock_violations(text) == []


def test_allowlists_are_pinned() -> None:
    # A widening is a reviewed change of this test (SE-1 spec 6.3).
    assert RUNTIME_ALLOWLIST == frozenset()
    assert DEV_ALLOWLIST == frozenset({"pytest", "ruff", "mypy", "import-linter"})
    assert BUILD_ALLOWLIST == frozenset({"hatchling"})
