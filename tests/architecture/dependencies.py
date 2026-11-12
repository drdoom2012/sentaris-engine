"""Dependency check over pyproject.toml and uv.lock: no Quasar code (DR-18), no exchange or trading libraries (DR-19).

Direct dependencies are held to allowlists, locked packages to a denylist (SE-1 spec 6.3). Read from pyproject.toml: the
dependency arrays and the other places that can declare or re-source one (`project.dynamic`, `tool.uv`, `tool.hatch`,
`build-system.requires`); from uv.lock only the `name` fields of `[[package]]`.
"""

import re
import tomllib
from typing import Any

# Pinned by test_allowlists_are_pinned; a widening is a reviewed change of that test (SE-1 spec 6.3).
RUNTIME_ALLOWLIST: frozenset[str] = frozenset()  # DR-19
DEV_ALLOWLIST: frozenset[str] = frozenset({"pytest", "ruff", "mypy", "import-linter"})  # project policy
BUILD_ALLOWLIST: frozenset[str] = frozenset({"hatchling"})  # project policy; [build-system].requires declares packages

_LOCK_DENYLIST_NAMES = (
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
    "quasar-market-data",  # DR-18
)

_HATCH_ALLOWED_PATH = ("build", "targets", "wheel", "packages")

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalise(name: str) -> str:
    """PEP 503 normalisation of a distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


LOCK_DENYLIST: frozenset[str] = frozenset(normalise(name) for name in _LOCK_DENYLIST_NAMES)


def requirement_name(requirement: str) -> str:
    """The normalised PEP 508 name at the start of a requirement string; ValueError if there is none."""
    match = _REQUIREMENT_NAME.match(requirement)
    if match is None:
        raise ValueError(f"no package name in requirement {requirement!r}")
    return normalise(match.group(1))


def _entry_violations(entries: object, allowed: frozenset[str], where: str) -> list[str]:
    """Violations for one array of requirements: a non-string entry, an unparsable one or a name off the allowlist."""
    if not isinstance(entries, list):
        return [f"{where}: not an array of requirement strings"]
    violations: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            violations.append(f"{where}: entry {entry!r} is not a plain requirement string")
            continue
        if "@" in entry:
            violations.append(f"{where}: entry {entry!r} is a direct reference, which re-sources the package")
            continue
        try:
            name = requirement_name(entry)
        except ValueError:
            violations.append(f"{where}: entry {entry!r} has no package name")
            continue
        if name not in allowed:
            violations.append(f"{where}: package {name!r} is not on the allowlist")
    return violations


def _unexpected_hatch_path(node: object, path: tuple[str, ...]) -> tuple[str, ...] | None:
    """The first key path under [tool.hatch] other than build.targets.wheel.packages, or None."""
    if path == _HATCH_ALLOWED_PATH:
        return None
    if isinstance(node, dict) and (node or not path):
        for key, child in node.items():
            found = _unexpected_hatch_path(child, (*path, key))
            if found is not None:
                return found
        return None
    return path


def pyproject_violations(text: str) -> list[str]:
    """Violations of the direct-dependency rules in a pyproject.toml text (DR-19, SE-1 spec 6.3)."""
    data: dict[str, Any] = tomllib.loads(text)
    violations: list[str] = []

    project: dict[str, Any] = data.get("project", {})
    violations += _entry_violations(project.get("dependencies", []), RUNTIME_ALLOWLIST, "[project].dependencies")
    if "optional-dependencies" in project:
        violations.append("[project.optional-dependencies]: table is not allowed")
    for field in ("dependencies", "optional-dependencies"):
        if field in project.get("dynamic", []):
            violations.append(f"[project].dynamic: {field!r} must not be filled dynamically")

    groups: dict[str, Any] = data.get("dependency-groups", {})
    for group, entries in groups.items():
        if group == "dev":
            violations += _entry_violations(entries, DEV_ALLOWLIST, "[dependency-groups].dev")
        else:
            violations.append(f"[dependency-groups].{group}: group is not allowed")

    tool: dict[str, Any] = data.get("tool", {})
    if "uv" in tool:
        violations.append("[tool.uv]: table is not allowed (it can declare or re-source dependencies)")
    unexpected = _unexpected_hatch_path(tool.get("hatch", {}), ())
    if unexpected is not None:
        violations.append(f"[tool.hatch]: {'.'.join(unexpected)} is not allowed (hooks can declare dependencies)")

    build: dict[str, Any] = data.get("build-system", {})
    violations += _entry_violations(build.get("requires", []), BUILD_ALLOWLIST, "[build-system].requires")
    return violations


def lock_violations(text: str) -> list[str]:
    """One violation per locked package whose normalised name is on the denylist (DR-18, DR-19)."""
    data: dict[str, Any] = tomllib.loads(text)
    violations: list[str] = []
    for package in data.get("package", []):
        name = normalise(package["name"])
        if name in LOCK_DENYLIST:
            violations.append(f"uv.lock: package {name!r} is denylisted")
    return violations
