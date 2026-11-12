"""AST purity checker and package guards (DR-08, DR-18, DR-19)."""

from pathlib import Path

import pytest

from tests.architecture.purity import (
    BANNED_EVERYWHERE,
    FORBIDDEN_CALLS,
    KNOWN_CHILDREN,
    PURE_STDLIB,
    find_violations,
    module_name,
    unknown_children,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = REPO_ROOT / "src"
PACKAGE_DIR = SRC / "sentaris_engine"
TESTS_DIR = REPO_ROOT / "tests"

D = "sentaris_engine.domain.x"
A = "sentaris_engine.application.x"
S = "sentaris_engine.strategies.x"
R = "sentaris_engine"
I = "sentaris_engine.infrastructure.x"
T = "tests.test_x"
DOMAIN_PKG = "sentaris_engine.domain"


def v(module: str, source: str, is_package: bool = False) -> list[str]:
    return find_violations(module, is_package=is_package, source=source)


NOT_PURE = "not allowed in pure code"  # message of a non-allowlisted import in pure code
INTERNAL = "not allowed here"  # message of an internal import outside the module's layering
ABOVE_TOP = "relative import goes above the top-level package"
BANNED = "is banned"

# (module, source, is_package, substring of the one violation message that must be reported)
NEGATIVE: list[tuple[str, str, bool, str]] = [
    # DR-08 stdlib allowlist
    (D, "import time", False, f"import of time {NOT_PURE}"),
    (A, "import time", False, f"import of time {NOT_PURE}"),
    (S, "import time", False, f"import of time {NOT_PURE}"),
    (R, "import time", True, f"import of time {NOT_PURE}"),
    *[
        (D, f"import {name}", False, f"import of {name} {NOT_PURE}")
        for name in ("datetime", "random", "uuid", "os", "socket", "importlib", "builtins")
    ],
    # DR-08 third-party ban
    (D, "import attrs", False, f"import of attrs {NOT_PURE}"),
    # DR-08 bypass forms
    (D, "import time as t", False, f"import of time {NOT_PURE}"),
    (D, "import re, time", False, f"import of time {NOT_PURE}"),
    (D, "import os.path", False, f"import of os.path {NOT_PURE}"),
    (D, "from os import path", False, f"import of os {NOT_PURE}"),
    (D, "def f():\n    import time", False, f"import of time {NOT_PURE}"),
    (D, "class C:\n    import time", False, f"import of time {NOT_PURE}"),
    (D, "try:\n    import time\nexcept ImportError:\n    pass", False, f"import of time {NOT_PURE}"),
    (D, "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import time", False, f"import of time {NOT_PURE}"),
    # DR-08 forbidden calls
    *[(D, f"{name}()", False, f"call of {name}() {NOT_PURE}") for name in sorted(FORBIDDEN_CALLS)],
    # DR-08 relative imports
    (D, "from .. import infrastructure", False, f"internal import of sentaris_engine.infrastructure {INTERNAL}"),
    (
        DOMAIN_PKG,
        "from .. import infrastructure",
        True,
        f"internal import of sentaris_engine.infrastructure {INTERNAL}",
    ),
    (A, "from .. import infrastructure", False, f"internal import of sentaris_engine.infrastructure {INTERNAL}"),
    (A, "from ..strategies import x", False, f"internal import of sentaris_engine.strategies.x {INTERNAL}"),
    (S, "from ..application import x", False, f"internal import of sentaris_engine.application.x {INTERNAL}"),
    (
        D,
        "from sentaris_engine import infrastructure",
        False,
        f"internal import of sentaris_engine.infrastructure {INTERNAL}",
    ),
    (D, "from sentaris_engine.domainx import a", False, f"internal import of sentaris_engine.domainx.a {INTERNAL}"),
    (D, "from .... import x", False, ABOVE_TOP),
    (T, "from .. import a", False, ABOVE_TOP),
    (D, "def (", False, "source does not parse"),
    # DR-08 root funnel
    (D, "import sentaris_engine", False, f"internal import of sentaris_engine {INTERNAL}"),
    (R, "from . import infrastructure", True, f"internal import of sentaris_engine.infrastructure {INTERNAL}"),
    (R, "import sentaris_engine.infrastructure", True, f"internal import of sentaris_engine.infrastructure {INTERNAL}"),
    # DR-18
    (I, "import quasar_market_data", False, f"import of quasar_market_data {BANNED}"),
    (I, "from quasar_market_data.api import x", False, f"import of quasar_market_data.api {BANNED}"),
    (T, "import quasar_market_data", False, f"import of quasar_market_data {BANNED}"),
    (T, "from quasar_market_data.api import x", False, f"import of quasar_market_data.api {BANNED}"),
    # DR-19 (and DR-18 for quasar_market_data)
    *[
        (module, f"import {name}", False, f"import of {name} {BANNED}")
        for module in (I, T)
        for name in sorted(BANNED_EVERYWHERE)
    ],
]


@pytest.mark.parametrize(("module", "source", "is_package", "expected"), NEGATIVE)
def test_violation_is_reported(module: str, source: str, is_package: bool, expected: str) -> None:
    violations = v(module, source, is_package)
    assert len(violations) == 1, violations
    assert expected in violations[0], violations


POSITIVE: list[tuple[str, str, bool]] = [
    (S, "from ..domain import x", False),
    (A, "from ..domain import x", False),
    (S, "from sentaris_engine.domain import x", False),
    (S, "import sentaris_engine.domain.y", False),
    (D, "from . import sibling", False),
    (DOMAIN_PKG, "from . import x", True),
    (D, "from __future__ import annotations", False),
    (D, "from collections.abc import Mapping", False),
    (I, "import time", False),
    (I, "import subprocess", False),
    (T, "import time", False),
    (T, "import subprocess", False),
    (T, 'x = "import quasar_market_data"', False),
]


@pytest.mark.parametrize(("module", "source", "is_package"), POSITIVE)
def test_allowed_source_is_clean(module: str, source: str, is_package: bool) -> None:
    assert v(module, source, is_package) == []


def test_pinned_lists() -> None:
    assert PURE_STDLIB == frozenset(
        {
            "__future__",
            "abc",
            "collections",
            "dataclasses",
            "decimal",
            "enum",
            "functools",
            "itertools",
            "math",
            "operator",
            "re",
            "types",
            "typing",
        }
    )
    assert FORBIDDEN_CALLS == frozenset(
        {"open", "input", "print", "breakpoint", "__import__", "eval", "exec", "compile", "globals", "vars"}
    )
    assert BANNED_EVERYWHERE == frozenset(
        {
            "quasar_market_data",
            "ccxt",
            "binance",
            "pybit",
            "okx",
            "kucoin",
            "krakenex",
            "coinbase",
            "cryptofeed",
            "freqtrade",
            "hummingbot",
        }
    )
    assert KNOWN_CHILDREN == frozenset({"domain", "application", "strategies", "infrastructure"})


def _known_package(root: Path) -> Path:
    for name in sorted(KNOWN_CHILDREN):
        (root / name).mkdir()
    return root


def test_unknown_child_package(tmp_path: Path) -> None:
    (_known_package(tmp_path) / "extra").mkdir()
    assert unknown_children(tmp_path) == ["extra"]


def test_unknown_child_module(tmp_path: Path) -> None:
    (_known_package(tmp_path) / "clock.py").write_text("")
    assert unknown_children(tmp_path) == ["clock.py"]


def test_non_code_children_ignored(tmp_path: Path) -> None:
    root = _known_package(tmp_path)
    for name in ("__init__.py", "py.typed", ".DS_Store"):
        (root / name).write_text("")
    (root / "__pycache__").mkdir()
    assert unknown_children(root) == []


def test_unknown_compiled_child(tmp_path: Path) -> None:
    (_known_package(tmp_path) / "clock.pyc").write_bytes(b"")
    assert unknown_children(tmp_path) == ["clock.pyc"]


@pytest.mark.parametrize(
    ("path", "root", "expected"),
    [
        (SRC / "sentaris_engine" / "domain" / "x.py", SRC, ("sentaris_engine.domain.x", False)),
        (SRC / "sentaris_engine" / "__init__.py", SRC, ("sentaris_engine", True)),
        (TESTS_DIR / "architecture" / "test_purity.py", REPO_ROOT, ("tests.architecture.test_purity", False)),
    ],
)
def test_module_name(path: Path, root: Path, expected: tuple[str, bool]) -> None:
    assert module_name(path, root) == expected


def test_real_tree_is_clean() -> None:
    files = [(path, SRC) for path in sorted(PACKAGE_DIR.rglob("*.py"))]
    files += [(path, REPO_ROOT) for path in sorted(TESTS_DIR.rglob("*.py"))]
    assert files
    violations: list[str] = []
    for path, root in files:
        name, is_package = module_name(path, root)
        source = path.read_text(encoding="utf-8")
        violations += [f"{path.relative_to(REPO_ROOT)}: {item}" for item in v(name, source, is_package)]
    assert violations == [], "\n".join(violations)


def test_real_package_has_no_unknown_child() -> None:
    assert unknown_children(PACKAGE_DIR) == []
